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
PUB_NONCE = "e3fc94ab8e"  # publication id from the public ratings page
PUB_ID = "1"


def fetch_all():
    data = {
        "action": "wpda_datatables", "wpnonce": PUB_NONCE, "pubid": PUB_ID,
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
        headers={"User-Agent": "KyronHealthApp/2.0",
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
