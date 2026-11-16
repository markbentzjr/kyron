#!/usr/bin/env python3
"""Socrata city/county harvest: fetch -> normalize -> validate.

Usage:  python harvest.py nyc|chicago|kingco [--limit-rows N]
Output: out/<key>/{places.json, fetch_log.json, validate_report.json,
        manifest.json}  (out/ is gitignored; regenerate any time)
Then:   python ../../tools/packs/build_pack_socrata.py <key>

Read-only HTTP GET; deterministic `$order=:id` offset paging; one retry
per page; row count cross-checked against `$select=count(*)`.
"""
import argparse, json, os, sys, urllib.parse
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402
from sources import SOURCES  # noqa: E402

PAGE = 50000


def get(url):
    return common.fetch_json(url)


def fetch(cfg, limit_rows=0):
    base = f"https://{cfg['domain']}/resource/{cfg['dataset']}.json"
    where = None
    if cfg["window_days"]:
        since = (date.today() - timedelta(days=cfg["window_days"])).isoformat()
        where = f"{cfg['date_field']}>='{since}'"
    q = {"$select": "count(*)"}
    if where:
        q["$where"] = where
    expected = int(get(base + "?" + urllib.parse.urlencode(q))[0]["count"])
    rows, off, log = [], 0, []
    while True:
        q = {"$limit": PAGE, "$offset": off, "$order": ":id"}
        if where:
            q["$where"] = where
        page = get(base + "?" + urllib.parse.urlencode(q))
        log.append({"offset": off, "rows": len(page)})
        rows.extend(page)
        print(f"  {cfg['dataset']}: {len(rows):,}/{expected:,}")
        if len(page) < PAGE or (limit_rows and len(rows) >= limit_rows):
            break
        off += PAGE
    if limit_rows:
        rows = rows[:limit_rows]
    return rows, {"base": base, "where": where, "expected": expected,
                  "fetched": len(rows), "pages": log}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("--limit-rows", type=int, default=0)
    a = ap.parse_args()
    cfg = SOURCES[a.source]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", a.source)
    rows, flog = fetch(cfg, a.limit_rows)
    if not a.limit_rows and flog["fetched"] != flog["expected"]:
        print(f"WARN count mismatch {flog}", file=sys.stderr)
    places = cfg["normalize"](rows, cfg)
    rep = common.validate_places(places,
                                 forbid_scores=cfg["model"] == "PASS_FAIL")
    common.emit(
        out,
        places=places, fetch_log=flog, validate_report=rep,
        manifest={"generated_at": datetime.now(timezone.utc).isoformat(),
                  "source": a.source, "dataset": cfg["dataset"]})
    print(json.dumps({k: v for k, v in rep.items() if k != "errors"}))
    return 1 if rep["error_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
