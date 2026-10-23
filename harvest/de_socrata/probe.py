#!/usr/bin/env python3
"""One-off Socrata probe for DE dataset 384s-wygj (not a pipeline step).

Checks the dataset shape: sample rows, total row count via X-Total-Count
header, and whether $offset paging orders deterministically with $order=:id.
Read-only HTTP GET only.
"""
import json
import urllib.request

BASE = "https://data.delaware.gov/resource/384s-wygj.json"
UA = "KyronHarvest/1.0 (public data; kyron example)"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        return r.status, dict(r.headers), body


st, hdrs, body = get(BASE + "?$limit=2")
print("sample status:", st)
print(json.dumps(json.loads(body)[:2], indent=1))
print("X-Total-Count:", hdrs.get("X-Total-Count"))

# offset paging sanity: rows 5000-5002 with stable :id order
st2, _, body2 = get(BASE + "?$limit=3&$offset=5000&$order=:id")
print("offset-page status:", st2)
rows = json.loads(body2)
print("offset sample ids:", [r.get(":id") or r.get(":id".replace(":", "@")) for r in rows][:3])
print(json.dumps(rows[0], indent=1))
