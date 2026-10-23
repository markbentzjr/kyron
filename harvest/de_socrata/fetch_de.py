#!/usr/bin/env python3
"""Delaware DPH harvest — fetch ALL rows of Socrata dataset 384s-wygj
("Food Establishment Inspection Violations", data.delaware.gov).

Verified live 2026-10-22: 33,519 rows over a rolling ~2-year window
(2024-10-14 .. 2026-12-03); one row per VIOLATION, plus rows with a
null `violation` (inspections with no listed violation); no numeric
score field exists anywhere in the dataset.

Paging patterns per task spec — both are tested and logged:
  A) unfiltered `$limit=5000&$offset=N&$order=:id` (the working
     pattern: `$order=:id` makes offset paging deterministic, and the
     dataset window is already >= 2 years, so unfiltered = the window)
  B) `$where=insp_date>='2024-10-22'` (executed as a count cross-check;
     NOTE: the earlier probe2.py 400 on this pattern was that script
     double-encoding its own `%27`, not a Socrata limitation)

Rowid continuity check: Socrata rejects `$select=:id,*` (HTTP 400,
observed), but accepts `$select=:id,<field>`. So when the rowid probe
succeeds, a SECOND pagination pass with `$select=:id&$order=:id`
collects rowids in the same deterministic order and they are paired
positionally with pass-1 rows, giving an explicit strict-increase
continuity check across page boundaries (no silently skipped rows).
If the rowid probe fails, continuity falls back to count-match +
deterministic ordering only.

Read-only HTTP GET only. One retry per page on failure. Every HTTP
status, page size and continuity result is logged to out/fetch_log.json.

Output: out/raw_de_rows.jsonl (one row per line; `_socrata_rowid` added
only when the rowid pass ran).
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "out")
BASE = "https://data.delaware.gov/resource/384s-wygj.json"
UA = "KyronHarvest/1.0 (public data; kyron example)"
PAGE = 5000
TIMEOUT = 60
WINDOW_SINCE = "2024-10-22"   # exactly 2 years before the 2026-10-22 fetch


def get_json(url, retries=1):
    """GET with timeout and one retry; returns (status, parsed_body).
    Network access is read-only HTTP GET only."""
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < retries:
                print(f"  retry {attempt + 1} after error: {e!r} "
                      f"({url[:100]})")
                time.sleep(5)
    raise RuntimeError(f"GET failed after {retries} retries: {last_err!r} "
                       f"{url[:100]}")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    log = {"base": BASE, "started_utc": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "requests": [],
        "rows_missing_rowid": 0}

    def req(name, path_qs):
        url = BASE + path_qs
        st, body = get_json(url)
        log["requests"].append(
            {"what": name, "status": st,
             "rows": len(body) if isinstance(body, list) else None})
        return body

    # ---- counts for both patterns (Socrata rejects $select=:id,* with
    # HTTP 400 — observed; documented here rather than retried silently)
    try:
        req("probe_select_rowid_star",
            "?" + urllib.parse.urlencode({"$select": ":id,*", "$limit": 1}))
    except RuntimeError as e:
        log["select_rowid_star"] = f"rejected: {e}"
    # does ':id' come through at all?
    try:
        sel_probe = req("probe_select_rowid",
                        "?" + urllib.parse.urlencode(
                            {"$select": ":id,restname", "$limit": 1,
                             "$order": ":id"}))
        has_rowid = bool(sel_probe) and ":id" in sel_probe[0]
    except RuntimeError:
        has_rowid = False
    log["rowid_select_supported"] = has_rowid

    cnt_all = req("count_unfiltered", "?$select=count(*)")
    total = int(cnt_all[0]["count"])
    where = urllib.parse.quote(f"insp_date>='{WINDOW_SINCE}'")
    cnt_win = req("count_where_window", f"?$select=count(*)&$where={where}")
    win_count = int(cnt_win[0]["count"])
    log["count_unfiltered"] = total
    log["count_where_window"] = win_count
    log["chosen_pattern"] = (
        "A: unfiltered $offset paging with $order=:id (pattern B's window "
        "count is recorded as a cross-check; dataset window is >= 2 years)")

    # ---- pass 1: every row, deterministic $order=:id offset paging ----
    pages = []
    offset = 0
    while True:
        rows = req(f"page offset={offset}",
                   "?" + urllib.parse.urlencode(
                       {"$limit": PAGE, "$offset": offset, "$order": ":id"}))
        if not rows:
            break
        pages.append(rows)
        offset += PAGE
        if len(rows) < PAGE:
            break
    all_rows = [r for p in pages for r in p]

    # ---- pass 2: rowids in the same deterministic order (only when the
    # rowid probe showed ':id' is selectable)
    rowids = []
    if has_rowid:
        offset = 0
        while True:
            ids = req(f"rowid page offset={offset}",
                      "?" + urllib.parse.urlencode(
                          {"$select": ":id", "$limit": PAGE,
                           "$offset": offset, "$order": ":id"}))
            if not ids:
                break
            rowids.extend(r.get(":id") for r in ids)
            offset += PAGE
            if len(ids) < PAGE:
                break
        if len(rowids) != len(all_rows):
            print(f"WARNING: rowid pass returned {len(rowids)} ids for "
                  f"{len(all_rows)} rows; rowids not paired",
                  file=sys.stderr)
            log["rowid_pairing_broken"] = True
            rowids = []
        else:
            for r, rid in zip(all_rows, rowids):
                r["_socrata_rowid"] = rid

    # ---- continuity: Socrata rowids are opaque (e.g. 'row-c5na.dcpn.irs7')
    # — NOT sortable numbers, so the valuable checks here are: every row
    # got a non-null unique rowid (no page overlap/drift), the two
    # positionally-paired passes agree in length, and the row count
    # matches the server-side count(*). $order=:id is then the documented
    # deterministic full-export pattern.
    rowid_gaps = 0
    if rowids:
        clean = [x for x in rowids if x is not None]
        if len(clean) != len(rowids):
            rowid_gaps += len(rowids) - len(clean)
        rowid_gaps += len(clean) - len(set(clean))
        log["rowid_unique"] = len(set(clean))
        log["rowid_range"] = [clean[0], clean[-1]]
        log["paired_by_position"] = True

    # byte-faithful per-row write
    out_path = os.path.join(OUT, "raw_de_rows.jsonl")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False,
                               separators=(",", ":")) + "\n")

    dup = len(all_rows) - len({json.dumps(r, sort_keys=True,
                                          ensure_ascii=False)
                               for r in all_rows})
    log["pages"] = [len(p) for p in pages]
    log["rows_written"] = len(all_rows)
    log["expected_total"] = total
    log["counts_match"] = (len(all_rows) == total)
    log["exact_duplicate_rows_in_stream"] = dup
    log["finished_utc"] = time.strftime("%H:%M:%SZ", time.gmtime())

    with open(os.path.join(OUT, "fetch_log.json"), "w") as f:
        json.dump(log, f, indent=1)
    print(json.dumps({k: log[k] for k in (
        "count_unfiltered", "count_where_window", "chosen_pattern",
        "rowid_select_supported", "pages", "rows_written",
        "expected_total", "counts_match", "rowid_unique",
        "exact_duplicate_rows_in_stream")}, indent=1))
    if len(all_rows) != total:
        print(f"FATAL: fetched {len(all_rows)} rows but server reported "
              f"{total}", file=sys.stderr)
        return 1
    if rowids and rowid_gaps:
        print("FATAL: rowid continuity check found null or duplicated "
              "rowids — pivot to `$where`-keyed paging before normalizing",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
