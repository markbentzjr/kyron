import requests, json, os, time, sys
from bs4 import BeautifulSoup
OUT = os.path.expanduser(os.environ.get('KYRON_BUILD','~/kyron-build'))+'/harvest/adph'
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "KyronHealthApp/2.0 (statewide data harvest)"}

def fetch_county(code, name):
    for attempt in range(4):
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
            r2 = s.post(r.url, data=data, timeout=100)
            d2 = BeautifulSoup(r2.text, 'html.parser')
            dt = d2.find(id='ctl00_ContentPlaceHolder1_DtList')
            if dt is None: raise ValueError("no DtList")
            places = []
            for td in dt.find_all('td'):
                parts = [p.strip() for p in td.get_text('|', strip=True).split('|')]
                if len(parts) < 12: continue
                rec = {}
                LABELS = {'establishment name', 'address', 'city', 'zip code', 'score', 'smoke free', 'inspection date'}
                j = 0
                while j < len(parts):
                    lab = parts[j].rstrip(':').strip().lower()
                    if lab in LABELS:
                        nxt = parts[j + 1] if j + 1 < len(parts) else ''
                        if nxt.rstrip(':').strip().lower() in LABELS:
                            rec[lab] = ''
                        else:
                            rec[lab] = nxt
                            j += 1
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
            print(f"  {name} attempt {attempt+1} failed: {type(e).__name__} {str(e)[:120]}", flush=True)
            time.sleep(5 * (attempt + 1))
    return None

# county map from the form itself
s = requests.Session(); s.headers.update(UA)
r = s.get("https://foodscores.state.al.us/default.aspx", timeout=60)
d = BeautifulSoup(r.text, 'html.parser')
sel = d.find('select', {'name': 'ctl00$ContentPlaceHolder1$DrpCnty'})
counties = [(o.get('value'), o.get_text(strip=True)) for o in sel.find_all('option') if o.get('value') and o.get('value') != 'Select County']
print(f"counties to harvest: {len(counties)}", flush=True)
total = 0
for code, name in counties:
    path = f"{OUT}/{code}.json"
    if os.path.exists(path):
        n = len(json.load(open(path))); total += n
        print(f"skip {name} ({n})", flush=True); continue
    places = fetch_county(code, name.title())
    if places is None:
        print(f"FAILED {name}", flush=True); continue
    json.dump(places, open(path, 'w'))
    total += len(places)
    print(f"{name}: {len(places)} places (running total {total})", flush=True)
    time.sleep(2)
print(f"DONE total={total}", flush=True)
