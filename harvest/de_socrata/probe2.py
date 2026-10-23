#!/usr/bin/env python3
"""Second Socrata probe: totals, date range, distinct types, null-violation rows."""
import json
import urllib.request

BASE = "https://data.delaware.gov/resource/384s-wygj.json"
UA = "KyronHarvest/1.0 (public data; kyron example)"


def get(qs):
    from urllib.parse import quote
    req = urllib.request.Request(BASE + "?" + quote(qs, "=$&,*+'()!~:[]/,"),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


print("count(*):", get("$select=count(*)"))
print("date range:", get("$select=min(insp_date),max(insp_date)"))
print("types:", get("$select=insp_type,count(*)&$group=insp_type"))
print("null violation rows:", get("$select=count(*)&$where=violation is null"))
print("null geocode rows:", get("$select=count(*)&$where=geocoded_column is null"))
print("null insp_date rows:", get("$select=count(*)&$where=insp_date is null"))
# sample a null-violation row
print("null-violation sample:", json.dumps(get("$limit=1&$where=violation is null"), indent=1))
# attempt $where date filter + count for a window
print("window count 2024-10-22..2026-10-22:",
      get("$select=count(*)&$where=insp_date>=%272024-10-22%27"))
