"""Stage 2: submit address batch files to the US Census batch geocoder.

Free, no key. Endpoint: POST multipart to
  https://geocoding.geo.census.gov/geocoder/locations/addressbatch
with fields addressFile=<csv>, benchmark=Public_AR_Current.
Input CSV rows: id,street,city,state,zip (no header).

Checkpointing: each batch's result CSV is stored under out/results/ and a
batch is never resubmitted once its result file exists and parses. Reruns
are therefore resume-safe and idempotent.

Usage:
  python3 census_batch.py build-pilot      # 1,000 stratified + ground truth
  python3 census_batch.py build-production # all remaining, <=5,000/file
  python3 census_batch.py run <name...>    # submit named batches
  python3 census_batch.py run-all          # submit every built batch lacking results
"""
import csv
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
BATCHES = os.path.join(OUT, "batches")
RESULTS = os.path.join(OUT, "results")
URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BENCHMARK = "Public_AR_Current"
MAX_PER_FILE = 5000


def load_addresses():
    return json.load(open(os.path.join(OUT, "addresses.json")))


def load_seed_places():
    seed = os.path.join(HERE, "..", "..", "src", "main", "assets", "places_seed.json")
    return json.load(open(seed))


def write_batch(name, rows, street_field="street"):
    os.makedirs(BATCHES, exist_ok=True)
    path = os.path.join(BATCHES, name + ".csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        for a in rows:
            w.writerow([a["address_id"], a[street_field], a["city"], "AL", a["zip"]])
    print(f"batch {name}: {len(rows)} rows -> {path}")
    return path


def build_pilot():
    addrs = [a for a in load_addresses() if a["submittable"]]
    # Ground truth: every address belonging to a place that already carries
    # coordinates (harvested earlier) — Census results get distance-checked
    # against those stored coordinates during adjudication.
    place_map = json.load(open(os.path.join(OUT, "place_address.json")))
    truth_ids = set()
    for p in load_seed_places():
        if p.get("lat") is not None:
            truth_ids.add(place_map[p["id"]])
    truth = [a for a in addrs if a["address_id"] in truth_ids]
    # Stratified systematic sample across counties.
    by_county = sorted(addrs, key=lambda a: (a["county"], a["address_id"]))
    step = max(1, len(by_county) // 1000)
    sample = by_county[::step][:1000]
    seen = {a["address_id"] for a in sample}
    pilot = sample + [a for a in truth if a["address_id"] not in seen]
    write_batch("pilot1000", pilot)
    json.dump([a["address_id"] for a in pilot],
              open(os.path.join(OUT, "pilot_ids.json"), "w"))
    print(f"pilot rows: {len(pilot)} (incl. {len(truth)} ground-truth addresses)")


REPAIRABLE = ("NEEDS_REVIEW", "NO_MATCH")


def build_repair(round_no):
    """Resubmit still-unresolved addresses with a variant street form.

    Round 1: full-word suffixes ("STREET" for "ST"). Round 2: suffix removed.
    Ties are NOT resubmitted: a refined identical key cannot break a tie
    honestly (draft 3.5); they stay in the residual queue.
    """
    adjudicated = json.load(open(os.path.join(OUT, "adjudicated.json")))
    addrs = {a["address_id"]: a for a in load_addresses()}
    todo = []
    for aid, adj in adjudicated.items():
        a = addrs.get(aid)
        if a and a["submittable"] and adj["status"] in REPAIRABLE:
            todo.append(a)
    todo.sort(key=lambda a: a["address_id"])
    if round_no == 1:
        todo = [dict(a, street=a["street_expanded"]) for a in todo]
    elif round_no == 2:
        from geocode_common import SUFFIX_CANON
        fixed = []
        for a in todo:
            a = dict(a)
            toks = a["street"].split(" ")
            if toks and toks[-1] in SUFFIX_CANON:
                toks.pop()
            a["street"] = " ".join(toks)
            fixed.append(a)
        todo = fixed
    for i in range(0, len(todo), MAX_PER_FILE):
        write_batch(f"repair{round_no}_{i // MAX_PER_FILE + 1:02d}", todo[i:i + MAX_PER_FILE])


def build_production(exclude_ids):
    addrs = [a for a in load_addresses()
             if a["submittable"] and a["address_id"] not in exclude_ids]
    addrs.sort(key=lambda a: a["address_id"])
    for i in range(0, len(addrs), MAX_PER_FILE):
        write_batch(f"prod{i // MAX_PER_FILE + 1:02d}", addrs[i:i + MAX_PER_FILE])


def result_ok(name):
    path = os.path.join(RESULTS, name + ".csv")
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            rows = list(csv.reader(f))
        return len(rows) > 0
    except Exception:
        return False


def submit(name):
    if result_ok(name):
        print(f"batch {name}: result exists, skipping (checkpoint)")
        return True
    os.makedirs(RESULTS, exist_ok=True)
    in_path = os.path.join(BATCHES, name + ".csv")
    out_path = os.path.join(RESULTS, name + ".csv")
    n_rows = sum(1 for _ in open(in_path))
    timeout = max(600, n_rows)  # generous: ~ up to 1s/address worst case
    for attempt in range(1, 4):
        t0 = time.time()
        print(f"batch {name}: submitting {n_rows} rows (attempt {attempt}) ...", flush=True)
        r = subprocess.run(
            ["curl", "-s", "-m", str(timeout), "-w", "\nHTTP:%{http_code}",
             "-F", f"addressFile=@{in_path}",
             "-F", f"benchmark={BENCHMARK}",
             URL],
            capture_output=True, text=True)
        body = r.stdout
        code = body.rsplit("HTTP:", 1)[-1].strip() if "HTTP:" in body else "?"
        payload = body.rsplit("\nHTTP:", 1)[0] if "HTTP:" in body else body
        if code == "200" and payload.strip() and "Match" in payload or "No_Match" in payload:
            with open(out_path, "w") as f:
                f.write(payload)
            rows = list(csv.reader(open(out_path)))
            print(f"batch {name}: OK {len(rows)} result rows in {time.time()-t0:.0f}s")
            return True
        print(f"batch {name}: HTTP {code}, body head: {payload[:200]!r}; retrying")
        time.sleep(15 * attempt)
    print(f"batch {name}: FAILED after retries")
    return False


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "build-pilot":
        build_pilot()
    elif cmd == "build-production":
        pilot_ids = set()
        p = os.path.join(OUT, "pilot_ids.json")
        if os.path.exists(p):
            pilot_ids = set(json.load(open(p)))
        build_production(pilot_ids)
    elif cmd == "build-repair":
        build_repair(int(sys.argv[2]))
    elif cmd == "run":
        ok = all(submit(n) for n in sys.argv[2:])
        sys.exit(0 if ok else 1)
    elif cmd == "run-all":
        names = sorted(fn[:-4] for fn in os.listdir(BATCHES) if fn.endswith(".csv"))
        ok = True
        for n in names:
            ok = submit(n) and ok
        sys.exit(0 if ok else 1)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
