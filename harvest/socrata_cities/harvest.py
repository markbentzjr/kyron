#!/usr/bin/env python3
"""Socrata city/county harvest: fetch -> normalize -> validate.

Usage:  python harvest.py nyc|chicago|kingco [--limit-rows N]
Output: out/<key>/{places.json, fetch_log.json, validate_report.json,
        manifest.json}  (out/ is gitignored; regenerate any time)
Then:   python ../../tools/packs/build_pack_socrata.py <key>

Read-only HTTP GET; deterministic `$order=:id` offset paging; one retry
per page; row count cross-checked against `$select=count(*)`.
"""
import argparse, json, os, sys, time, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sources import SOURCES  # noqa: E402

UA = "KyronHarvest/1.0 (public data; github.com/markbentzjr/kyron)"
PAGE = 50000


def get(url):
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if attempt:
                raise RuntimeError(f"GET failed: {e!r} {url[:120]}")
            time.sleep(5)


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


def validate(places, cfg):
    errs = []
    ids = set()
    for p in places:
        if p["id"] in ids:
            errs.append(f"duplicate id {p['id']}")
        ids.add(p["id"])
        if not p["n"]:
            errs.append(f"{p['id']}: empty name")
        if (p["lat"] is None) != (p["gs"] != "ACCEPTED"):
            errs.append(f"{p['id']}: geo/provenance mismatch")
        for i in p["insp"]:
            if cfg["model"] == "PASS_FAIL" and i["s"] != -1:
                errs.append(f"{p['id']}: PASS_FAIL inspection has a score")
            if i["s"] != -1 and not (0 <= i["s"] <= 300):
                errs.append(f"{p['id']}: score out of range {i['s']}")
            if not i["d"]:
                errs.append(f"{p['id']}: inspection without date")
    return {"places": len(places),
            "inspections": sum(len(p["insp"]) for p in places),
            "violations": sum(len(i["v"]) for p in places for i in p["insp"]),
            "with_coords": sum(p["lat"] is not None for p in places),
            "errors": errs[:50], "error_count": len(errs)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=sorted(SOURCES))
    ap.add_argument("--limit-rows", type=int, default=0)
    a = ap.parse_args()
    cfg = SOURCES[a.source]
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", a.source)
    os.makedirs(out, exist_ok=True)
    rows, flog = fetch(cfg, a.limit_rows)
    if not a.limit_rows and flog["fetched"] != flog["expected"]:
        print(f"WARN count mismatch {flog}", file=sys.stderr)
    places = cfg["normalize"](rows, cfg)
    rep = validate(places, cfg)
    for name, obj in (("places.json", places), ("fetch_log.json", flog),
                      ("validate_report.json", rep),
                      ("manifest.json", {"generated_at": datetime.now(timezone.utc).isoformat(),
                                         "source": a.source, "dataset": cfg["dataset"]})):
        with open(os.path.join(out, name), "w") as f:
            json.dump(obj, f, ensure_ascii=False)
    print(json.dumps({k: v for k, v in rep.items() if k != "errors"}))
    return 1 if rep["error_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
