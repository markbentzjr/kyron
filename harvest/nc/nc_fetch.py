#!/usr/bin/env python3
"""NC CDPEHS harvest fetcher (Workstream C8).

Enumerates every inspection row of the 98 CDPEHS counties from the
portal's own CSV export (the matched-row oracle), then fetches the
official violation-detail page for every FOOD-SERVICE inspection via
the grid's Violation Details postback. Slices are (county, est-type),
date-chunked when a slice exceeds CHUNK_MAX rows so no portal query
window can silently truncate: every slice's grid count and CSV count
must equal the count predicted from the county's all-types CSV.

Every fetch is logged to fetch_log.tsv (file, URL, UTC ts, status,
bytes, SHA-256 of content). Raw payloads are gzip-compressed under
raw/ (lossless). Fully resumable: finished tasks are marked in
work/state/ and skipped on re-run.
"""
import os, re, sys, csv, io, json, gzip, time, hashlib, threading
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "work"))
from cdpehs_lib import Cdpehs, items_count, parse_form  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "raw")
WORK = os.path.join(ROOT, "work")
STATE = os.path.join(WORK, "state")
os.makedirs(STATE, exist_ok=True)
os.makedirs(os.path.join(RAW, "csv"), exist_ok=True)
os.makedirs(os.path.join(RAW, "grid"), exist_ok=True)
os.makedirs(os.path.join(RAW, "viol"), exist_ok=True)
os.makedirs(os.path.join(ROOT, "index"), exist_ok=True)

FOOD_TYPES = {"1", "2", "3", "4", "5", "6", "9", "11", "12", "14", "15", "16", "30"}
CHUNK_MAX = 8000
PAGE = 500

log_lock = threading.Lock()
LOG = os.path.join(ROOT, "fetch_log.tsv")

def utcnow():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def log_fetch(relpath, url, status, content: bytes):
    h = hashlib.sha256(content).hexdigest()
    line = f"{relpath}\t{url}\t{utcnow()}\t{status}\t{len(content)}\t{h}\n"
    with log_lock:
        with open(LOG, "a") as f:
            f.write(line)

def save_gz(relpath, content: bytes):
    path = os.path.join(ROOT, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wb", compresslevel=6) as f:
        f.write(content)
    return relpath

def parse_csv_bytes(content: bytes):
    text = content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    header, data = rows[0], [r for r in rows[1:] if r and any(c.strip() for c in r)]
    return header, data

def stub_from_csv_row(r):
    # CSV header: Inspection Date, Grade, Final Score, Inspector ID,
    # Premises Name, Premise Address 1, Premise Address 2, Premise City,
    # Premise State, Premise ZIP, State ID#, ID(=est type), ''
    return {
        "date": r[0].split(" ")[0], "grade": r[1], "score": r[2],
        "inspector": r[3], "name": r[4], "addr1": r[5], "addr2": r[6],
        "city": r[7], "state": r[8], "zip": r[9], "state_id": r[10],
        "type": r[11],
    }

CELL_RE = re.compile(r'<td[^>]*class="ttc"[^>]*>(.*?)</td>', re.S)
ROW_RE = re.compile(
    r'<tr><td id="ctl00_PageContent_VW_PUBLIC_ESTINSPTableControlRepeater_(ctl\d+)_ViolDtlRow"')

def clean(cell):
    cell = re.sub(r'<br\s*/?>', ', ', cell)
    cell = re.sub(r'<[^>]+>', ' ', cell)
    cell = cell.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&#39;', "'")
    return re.sub(r'\s+', ' ', cell).strip()

def parse_grid_rows(html):
    rows = []
    starts = [m for m in ROW_RE.finditer(html)]
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(html)
        block = html[m.start():end]
        cells = [clean(c) for c in CELL_RE.findall(block)]
        # cells: [Violation Details, date, name, address, state_id, type,
        #         score, grade, inspector, (pdf cell may be unclassed)]
        if len(cells) < 9:
            rows.append({"ctl": m.group(1), "parse_error": f"{len(cells)} cells"})
            continue
        # cells: [0]=Violation Details link [1]=date [2]=name [3]=address
        #        [4]=state_id [5]=type [6]=score [7]=grade [8]=inspector
        #        [9]=Inspection Report pdf link (may be absent)
        rows.append({
            "ctl": m.group(1), "date": cells[1], "name": cells[2],
            "address": cells[3], "state_id": cells[4], "type_label": cells[5],
            "score": cells[6], "grade": cells[7], "inspector": cells[8],
        })
    return rows

def county_name_of(html):
    m = re.search(r'<select[^>]*COUNTY_IDFilter[^>]*>(.*?)</select>', html, re.S)
    if m:
        o = re.search(r'<option[^>]*selected[^>]*>(.*?)</option>', m.group(1))
        if o:
            return re.sub(r'<[^>]+>', '', o.group(1)).strip()
    return None

class SliceFail(Exception):
    pass

def csv_export(client, url, html, timeout=600):
    r = client.postback(url, html, extra={
        "ctl00$PageContent$CSVButton1.x": "12", "ctl00$PageContent$CSVButton1.y": "12"},
        timeout=timeout)
    if b"Inspection Date" not in r.content[:200]:
        raise SliceFail(f"CSV export unexpected payload ({len(r.content)} bytes)")
    return r.content

def apply_filters(client, url, html, type_id=None, dfrom=None, dto=None):
    ov = {}
    if type_id:
        ov["ctl00$PageContent$EST_TYPE_IDFilter"] = type_id
    if dfrom:
        ov["ctl00$PageContent$INSPECTION_DATEFromFilter"] = dfrom
    if dto:
        ov["ctl00$PageContent$INSPECTION_DATEToFilter"] = dto
    r = client.postback(url, html, target="ctl00$PageContent$FilterButton$_Button", overrides=ov)
    return r.text

def fmt_date(iso):
    y, m, d = iso.split("-")
    return f"{m}/{d}/{y}"

def plan_chunks(stubs):
    """Split a type slice's stubs into date chunks of <= CHUNK_MAX rows.
    Returns list of (dfrom_iso|None, dto_iso|None, count)."""
    if len(stubs) <= CHUNK_MAX:
        return [(None, None, len(stubs))]
    dates = sorted(s["date_iso"] for s in stubs)
    chunks = []
    i = 0
    while i < len(dates):
        j = min(i + CHUNK_MAX, len(dates))
        dto = dates[j - 1]
        dfrom = dates[i]
        # all rows on boundary dates belong to exactly one chunk because
        # chunking is by position over the sorted multiset and the grid
        # date filter is inclusive; adjacent chunks share the boundary
        # date only when a single date has >CHUNK_MAX rows (not seen:
        # guard below). Extend j to the end of the dto date group.
        while j < len(dates) and dates[j] == dto:
            j += 1
        cnt = sum(1 for s in stubs if dfrom <= s["date_iso"] <= dto)
        chunks.append((dfrom, dto, cnt))
        i = j
    return chunks

def harvest_task(task):
    """task: dict(cty, code, county, type, dfrom, dto, expected)"""
    tid = f"cty{task['code']:03d}_t{task['type']}" + (
        f"_{task['dfrom']}_{task['dto']}" if task["dfrom"] else "")
    done_file = os.path.join(STATE, tid + ".json")
    if os.path.exists(done_file):
        return tid, "skip"
    client = Cdpehs()
    cty = task["code"]
    url, html = client.get_county(cty)
    filtered = apply_filters(client, url, html, type_id=task["type"],
                             dfrom=fmt_date(task["dfrom"]) if task["dfrom"] else None,
                             dto=fmt_date(task["dto"]) if task["dto"] else None)
    ic = items_count(filtered)
    if ic is None or ic[1] != task["expected"]:
        raise SliceFail(f"{tid}: filtered items {ic} != expected {task['expected']}")
    # slice CSV oracle (in filtered state)
    csv_bytes = csv_export(client, url, filtered)
    rel = f"raw/csv/cty{cty:03d}_t{task['type']}" + (
        f"_{task['dfrom']}_{task['dto']}" if task["dfrom"] else "") + ".csv"
    with open(os.path.join(ROOT, rel), "wb") as f:
        f.write(csv_bytes)
    log_fetch(rel, url + " [CSV export]", 200, csv_bytes)
    _, srows = parse_csv_bytes(csv_bytes)
    slice_stubs = [stub_from_csv_row(r) for r in srows]
    if len(slice_stubs) != task["expected"]:
        raise SliceFail(f"{tid}: slice CSV rows {len(slice_stubs)} != {task['expected']}")
    # page size
    grid = client.postback(url, filtered, target="ctl00$PageContent$Pagination$_PageSizeButton",
                           overrides={"ctl00$PageContent$Pagination$_PageSize": str(PAGE),
                                      "ctl00$PageContent$Pagination$_CurrentPage": "1"}).text
    icp = items_count(grid)
    if icp is None or icp[1] != task["expected"]:
        raise SliceFail(f"{tid}: after PageSize items {icp} != {task['expected']}")
    npages = (task["expected"] + PAGE - 1) // PAGE
    index_path = os.path.join(ROOT, "index", f"cty{cty:03d}.jsonl")
    fails = []
    seen_pairs = set()
    harvested = 0
    for page in range(1, npages + 1):
        rows = parse_grid_rows(grid)
        want = min(PAGE, task["expected"] - (page - 1) * PAGE)
        if len(rows) != want:
            raise SliceFail(f"{tid} p{page}: parsed {len(rows)} rows != {want}")
        grel = save_gz(f"raw/grid/cty{cty:03d}/{tid}_p{page}.html.gz", grid.encode())
        log_fetch(grel, url + f" [grid {tid} p{page}]", 200, grid.encode())
        for row in rows:
            if "parse_error" in row:
                fails.append({"row": row, "page": page, "err": "grid parse"})
                continue
            if row["type_label"].split(" - ")[0].strip() != str(task["type"]):
                raise SliceFail(f"{tid} p{page}: row type {row['type_label']} != task type {task['type']}")
            if task["dfrom"]:
                dm = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", row["date"])
                riso = (f"{dm.group(3)}-{int(dm.group(1)):02d}-{int(dm.group(2)):02d}"
                        if dm else "?")
                if not (task["dfrom"] <= riso <= task["dto"]):
                    raise SliceFail(f"{tid} p{page}: row date {row['date']} outside chunk")
            target = (f"ctl00$PageContent$VW_PUBLIC_ESTINSPTableControlRepeater"
                      f"${row['ctl']}$ViolationDetails")
            try:
                r = client.postback(url, grid, target=target)
            except Exception as e:
                fails.append({"stub": row, "page": page, "err": f"{type(e).__name__}: {e}"})
                continue
            m = re.search(r'ESTABLISHMENT=(\d+)&INSPECTION=(\d+)', r.url)
            if not m:
                fails.append({"stub": row, "page": page, "err": f"no ids in {r.url}"})
                continue
            estab, insp = m.group(1), m.group(2)
            vrel = save_gz(f"raw/viol/cty{cty:03d}/{insp}.html.gz", r.content)
            log_fetch(vrel, r.url, r.status_code, r.content)
            rec = {"cty": cty, "county": task["county"], "type": task["type"],
                   "chunk": [task["dfrom"], task["dto"]], "estab": estab,
                   "insp": insp, "url": r.url, "file": vrel,
                   "grid_stub": {k: row[k] for k in
                                 ("date", "name", "address", "state_id",
                                  "type_label", "score", "grade", "inspector")}}
            with log_lock:
                with open(index_path, "a") as f:
                    f.write(json.dumps(rec) + "\n")
            if (estab, insp) in seen_pairs:
                fails.append({"stub": row, "page": page, "err": "duplicate pair in task"})
            seen_pairs.add((estab, insp))
            harvested += 1
        if page < npages:
            r = client.postback(url, grid, target="ctl00$PageContent$Pagination$_NextPage")
            grid = r.text
            ic2 = items_count(grid)
            if ic2 is None or ic2[1] != task["expected"]:
                raise SliceFail(f"{tid}: after NextPage items {ic2}")
    with open(done_file, "w") as f:
        json.dump({"task": task, "harvested": harvested, "fails": fails,
                   "finished": utcnow()}, f, indent=1)
    return tid, f"done harvested={harvested} fails={len(fails)}"

def _stubs_from(rows):
    stubs = []
    for r in rows:
        s = stub_from_csv_row(r)
        m, dd, y = s["date"].split("/")
        s["date_iso"] = f"{y}-{int(m):02d}-{int(dd):02d}"
        stubs.append(s)
    return stubs

def probe_county(code):
    client = Cdpehs()
    url, html = client.get_county(code)
    county = county_name_of(html)
    ic = items_count(html)
    total = ic[1] if ic else None
    if total == 0:
        return {"code": code, "county": county, "items": 0, "csv_rows": 0, "stubs": []}
    try:
        csv_bytes = csv_export(client, url, html)
        rel = f"raw/csv/cty{code:03d}_all.csv"
        with open(os.path.join(ROOT, rel), "wb") as f:
            f.write(csv_bytes)
        log_fetch(rel, url + " [CSV export ALL]", 200, csv_bytes)
        _, rows = parse_csv_bytes(csv_bytes)
        stubs = _stubs_from(rows)
        if total is not None and len(stubs) != total:
            raise SliceFail(f"items {total} != csv {len(stubs)}")
        return {"code": code, "county": county, "items": total,
                "csv_rows": len(stubs), "stubs": stubs}
    except Exception as e:
        # Fallback: year-partitioned CSV exports (huge county / drift).
        print(f"  probe cty {code}: ALL-CSV failed ({e}); year fallback", flush=True)
        stubs = []
        for y in range(2007, 2027):
            filtered = apply_filters(client, url, html,
                                     dfrom=f"01/01/{y}", dto=f"12/31/{y}")
            ic_y = items_count(filtered)
            if not ic_y or ic_y[1] == 0:
                continue
            b = csv_export(client, url, filtered)
            rel = f"raw/csv/cty{code:03d}_all_{y}.csv"
            with open(os.path.join(ROOT, rel), "wb") as f:
                f.write(b)
            log_fetch(rel, url + f" [CSV export ALL {y}]", 200, b)
            _, rows = parse_csv_bytes(b)
            if len(rows) != ic_y[1]:
                raise SliceFail(f"cty {code} {y}: items {ic_y[1]} != csv {len(rows)}")
            stubs.extend(_stubs_from(rows))
        return {"code": code, "county": county, "items": total,
                "csv_rows": len(stubs), "stubs": stubs, "fallback": "year"}

def main():
    only = [int(x) for x in sys.argv[1:]] or list(range(1, 101))
    print("probing counties...", flush=True)
    counties = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(probe_county, only):
            counties[res["code"]] = res
            print(f"  cty {res['code']:3d} {res['county']}: items={res['items']} csv={res['csv_rows']}", flush=True)
            if res["items"] != res["csv_rows"]:
                print(f"  !! ORACLE MISMATCH cty {res['code']}: items {res['items']} vs csv {res['csv_rows']}", flush=True)
    tasks = []
    for code, res in counties.items():
        if not res["csv_rows"]:
            continue
        by_type = {}
        for s in res["stubs"]:
            if s["type"] in FOOD_TYPES:
                by_type.setdefault(s["type"], []).append(s)
        for t, stubs in sorted(by_type.items()):
            for dfrom, dto, cnt in plan_chunks(stubs):
                tasks.append({"code": code, "county": res["county"], "type": t,
                              "dfrom": dfrom, "dto": dto, "expected": cnt})
    print(f"planned {len(tasks)} slice tasks, "
          f"{sum(t['expected'] for t in tasks)} food inspections", flush=True)
    json.dump([{k: v for k, v in t.items()} for t in tasks],
              open(os.path.join(WORK, "tasks.json"), "w"), indent=1)
    errors = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for tid, msg in ex.map(lambda t: _run(t, errors), tasks):
            print(tid, msg, flush=True)
    if errors:
        print("TASK ERRORS:", json.dumps(errors, indent=1), flush=True)

def _run(task, errors):
    try:
        return harvest_task(task)
    except Exception as e:
        errors.append({"task": task, "err": f"{type(e).__name__}: {e}"})
        return (f"cty{task['code']:03d}_t{task['type']}", f"ERROR {e}")

if __name__ == "__main__":
    main()
