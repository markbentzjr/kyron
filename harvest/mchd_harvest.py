"""Harvest Mobile County (MCHD) restaurant ratings into mchd_rows.json.

Mobile County is one of Alabama's two independent county health departments
and is NOT part of the ADPH feed. Its ratings page
(https://mchd.org/restaurant-ratings-mobile/) is a WordPress "WP Data Access"
table backed by a public admin-ajax endpoint (action=wpda_datatables) that
returns DataTables server-side JSON: one row per establishment with up to
four dated inspection scores ("3/14/2025, Score: 99 -- Smoke Free: No ...").

The wpnonce value is the table's public publication id, embedded in the
ratings page itself.
"""
import urllib.request, urllib.parse, json

COLUMNS = ["EST_NAME", "EST_ADDRESS", "EST_CSZ", "INS_ONE", "INS_TWO", "INS_THREE", "INS_FOUR"]
ENDPOINT = "https://mchd.org/wp-admin/admin-ajax.php"
PUB_NONCE = "e3fc94ab8e"  # fallback; refreshed from the public ratings page below


def _live_nonce():
    """The publication nonce rotates; read the current one from the page."""
    import re
    try:
        req = urllib.request.Request("https://mchd.org/restaurant-ratings-mobile/",
                                     headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        m = re.search(r'geosearch_options,\s*"([0-9a-f]{10})"', html)
        return m.group(1) if m else PUB_NONCE
    except Exception:  # noqa: BLE001
        return PUB_NONCE
PUB_ID = "1"


def fetch_all():
    data = {
        "action": "wpda_datatables", "wpnonce": _live_nonce(), "pubid": PUB_ID, "pub_id": PUB_ID,
        "filter_field_name": "", "filter_field_value": "", "nl2br": "",
        "draw": "1", "start": "0", "length": "5000",
        "search[value]": "", "search[regex]": "false",
        "order[0][column]": "0", "order[0][dir]": "asc",
    }
    for i, c in enumerate(COLUMNS):
        data[f"columns[{i}][data]"] = str(i)
        data[f"columns[{i}][name]"] = c
        data[f"columns[{i}][searchable]"] = "true"
        data[f"columns[{i}][orderable]"] = "true"
        data[f"columns[{i}][search][value]"] = ""
        data[f"columns[{i}][search][regex]"] = "false"
    req = urllib.request.Request(
        ENDPOINT,
        data=urllib.parse.urlencode(data).encode(),
        headers={"User-Agent": "Mozilla/5.0",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    body = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")
    obj = json.loads(body)
    print(f"recordsTotal: {obj['recordsTotal']}, rows: {len(obj['data'])}")
    return obj["data"]


if __name__ == "__main__":
    rows = fetch_all()
    json.dump(rows, open("mchd_rows.json", "w"))
    print("saved mchd_rows.json")
