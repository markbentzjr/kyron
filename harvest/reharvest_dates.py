import requests, json, os, time, glob, sys
sys.path.insert(0, '/home/hatch/kyron-build/harvest')
from bs4 import BeautifulSoup
OUT = '/home/hatch/kyron-build/harvest/adph'
UA = {"User-Agent": "KyronHealthApp/2.0 (statewide data harvest)"}
LABELS = {'establishment name', 'address', 'city', 'zip code', 'score', 'smoke free', 'inspection date'}

def fetch_county(code, name):
    for attempt in range(5):
        try:
            s = requests.Session(); s.headers.update(UA)
            r = s.get("https://foodscores.state.al.us/default.aspx", timeout=60)
            d = BeautifulSoup(r.text, 'html.parser')
            hv = lambda n: (d.find('input', {'name': n}) or {}).get('value', '')
            tsel = d.find('select', {'name': 'ctl00$ContentPlaceHolder1$DrpEstdType'})
            data = {'__VIEWSTATE': hv('__VIEWSTATE'), '__VIEWSTATEGENERATOR': hv('__VIEWSTATEGENERATOR'),
             '__EVENTVALIDATION': hv('__EVENTVALIDATION'),
             'ctl00$ContentPlaceHolder1$TxtEstdNm': '',
             'ctl00$ContentPlaceHolder1$DrpEstdType': tsel.find_all('option')[0].get('value'),
             'ctl00$ContentPlaceHolder1$txtCity': '',
             'ctl00$ContentPlaceHolder1$DrpCnty': code,
             'ctl00$ContentPlaceHolder1$BtnSearch.x': '10', 'ctl00$ContentPlaceHolder1$BtnSearch.y': '10'}
            r2 = s.post(r.url, data=data, timeout=120)
            d2 = BeautifulSoup(r2.text, 'html.parser')
            dt = d2.find(id='ctl00_ContentPlaceHolder1_DtList')
            if dt is None: raise ValueError("no DtList")
            places = []
            for td in dt.find_all('td'):
                parts = [p.strip() for p in td.get_text('|', strip=True).split('|')]
                if len(parts) < 12: continue
                rec = {}
                j = 0
                while j < len(parts):
                    lab = parts[j].rstrip(':').strip().lower()
                    if lab in LABELS:
                        nxt = parts[j + 1] if j + 1 < len(parts) else ''
                        if nxt.rstrip(':').strip().lower() in LABELS:
                            rec[lab] = ''
                        else:
                            rec[lab] = nxt; j += 1
                    j += 1
                if 'establishment name' in rec and 'score' in rec:
                    try: sc = int(rec['score'])
                    except: continue
                    places.append({"name": rec['establishment name'], "address": rec.get('address',''),
                                   "city": rec.get('city',''), "zip": rec.get('zip code',''),
                                   "county": name, "score": sc, "date": rec.get('inspection date',''),
                                   "source": "ADPH"})
            return places
        except Exception as e:
            print(f"  {name} attempt {attempt+1} failed: {type(e).__name__} {str(e)[:100]}", flush=True)
            time.sleep(6 * (attempt + 1))
    return None

targets = []
for path in sorted(glob.glob(f"{OUT}/*.json"), key=lambda p: int(os.path.basename(p)[:-5])):
    rows = json.load(open(path))
    nd = sum(1 for r in rows if not r.get('date'))
    if nd and rows:
        targets.append((os.path.basename(path)[:-5], rows[0]['county'], len(rows), nd))
print(f"reharvest targets: {len(targets)} counties", flush=True)
done = failed = 0
for code, name, old_n, old_nd in targets:
    places = fetch_county(code, name)
    if places is None:
        failed += 1; print(f"FAILED {name} ({code}) — keeping old file", flush=True); continue
    if len(places) < old_n * 0.8:
        failed += 1; print(f"SUSPECT {name}: new {len(places)} vs old {old_n} — keeping old file", flush=True); continue
    json.dump(places, open(f"{OUT}/{code}.json", 'w'))
    nd = sum(1 for r in rows if not r.get('date')) if (rows:=places) else 0
    done += 1
    print(f"OK {name}: {len(places)} places, missing dates now {nd} (was {old_nd})", flush=True)
    time.sleep(2)
print(f"REHARVEST DONE ok={done} failed={failed}", flush=True)
