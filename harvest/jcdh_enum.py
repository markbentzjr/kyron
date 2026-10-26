import requests, json, os, time, string
from bs4 import BeautifulSoup

URL = "https://www.jcdh.org/SitePages/Programs-Services/Scores-Lists/Food/FoodServScores.aspx"
UA = {"User-Agent": "KyronHealthApp/2.0 (Jefferson County catalog harvest)"}
OUT = os.path.expanduser(os.environ.get('KYRON_BUILD','~/kyron-build'))+'/harvest/jcdh_enum.json'
DONE = os.path.expanduser(os.environ.get('KYRON_BUILD','~/kyron-build'))+'/harvest/jcdh_enum_done.json'
CAP = 52

places = {}
done = set()
if os.path.exists(OUT):
    places = {p['permit']: p for p in json.load(open(OUT))}
if os.path.exists(DONE):
    done = set(json.load(open(DONE)))
print(f"resume: {len(places)} places, {len(done)} prefixes done", flush=True)

s = requests.Session(); s.headers.update(UA)

def search(keyword):
    for attempt in range(4):
        try:
            r = s.get(URL, timeout=60)
            d = BeautifulSoup(r.text, 'html.parser')
            hv = lambda n: (d.find('input', {'name': n}) or {}).get('value', '')
            data = {'__VIEWSTATE': hv('__VIEWSTATE'), '__VIEWSTATEGENERATOR': hv('__VIEWSTATEGENERATOR'),
             '__EVENTVALIDATION': hv('__EVENTVALIDATION'),
             'ctl00$MainContent$txtBKeyword': keyword, 'ctl00$MainContent$btnSearch': 'Search'}
            r2 = s.post(URL, data=data, timeout=110)
            d2 = BeautifulSoup(r2.text, 'html.parser')
            gv = d2.find('table', {'id': 'MainContent_gvFoodScores'})
            if gv is None:
                raise ValueError("no grid")
            rows = []
            for tr in gv.find_all('tr'):
                cells = [c.get_text(' ', strip=True) for c in tr.find_all('td')]
                if len(cells) < 4:
                    continue
                a = tr.find('a', href=lambda h: h and 'FoodServScoreDetails' in h)
                rows.append({"permit": cells[0], "score": cells[1], "blob": cells[2],
                             "date": cells[3], "detail_path": a.get('href') if a else None})
            return rows
        except Exception as e:
            print(f"  {keyword} attempt {attempt+1}: {type(e).__name__} {str(e)[:90]}", flush=True)
            time.sleep(5 * (attempt + 1))
    return None

queue = [a + b for a in string.ascii_lowercase for b in string.ascii_lowercase]
qi = 0
while qi < len(queue):
    kw = queue[qi]; qi += 1
    if kw in done:
        continue
    rows = search(kw)
    if rows is None:
        print(f"FAILED prefix {kw}", flush=True)
        continue
    for row in rows:
        if row['permit'] not in places:
            places[row['permit']] = row
    done.add(kw)
    if len(rows) >= CAP:
        for c in string.ascii_lowercase:
            ext = kw + c
            if ext not in done and ext not in queue:
                queue.append(ext)
        print(f"{kw}: {len(rows)} rows (CAP HIT -> expanding) unique={len(places)} queue={len(queue)-qi}", flush=True)
    else:
        print(f"{kw}: {len(rows)} rows unique={len(places)} queue_left={len(queue)-qi}", flush=True)
    json.dump(list(places.values()), open(OUT, 'w'))
    json.dump(sorted(done), open(DONE, 'w'))
    time.sleep(1.2)

print(f"DONE unique Jefferson places: {len(places)}", flush=True)
