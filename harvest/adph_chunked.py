import requests, json, os, time, sys
from bs4 import BeautifulSoup
UA = {"User-Agent": "KyronHealthApp/2.0 (statewide data harvest)"}
OUT = '/home/hatch/kyron-build/harvest/adph'

def search(county_code, city, county_name):
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
             'ctl00$ContentPlaceHolder1$txtCity': city,
             'ctl00$ContentPlaceHolder1$DrpCnty': county_code,
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
                it = iter(parts)
                for a, b in zip(it, it):
                    rec[a.rstrip(':').strip().lower()] = b
                if 'establishment name' in rec and 'score' in rec:
                    try: sc = int(rec['score'])
                    except: continue
                    places.append({"name": rec['establishment name'], "address": rec.get('address',''),
                                   "city": rec.get('city',''), "zip": rec.get('zip code',''),
                                   "county": county_name, "score": sc, "date": rec.get('inspection date',''),
                                   "source": "ADPH"})
            return places
        except Exception as e:
            print(f"  {city} attempt {attempt+1}: {type(e).__name__} {str(e)[:100]}", flush=True)
            time.sleep(5 * (attempt + 1))
    return None

JEFFERSON_CITIES = ["Birmingham","Hoover","Bessemer","Vestavia Hills","Homewood","Mountain Brook",
 "Trussville","Leeds","Fairfield","Fultondale","Gardendale","Pinson","Center Point","Pleasant Grove",
 "Hueytown","Warrior","Irondale","Tarrant","Midfield","Adamsville","Clay","Kimberly","Morris",
 "Brighton","Lipscomb","Graysville","Brookside","Maytown","Mulga","Sylvan Springs","North Johns",
 "Argo","Trafford","Forestdale","Edgewater","Dolomite","Concord","Rock Creek","Sayre","Bagley","Pinson Valley"]

county_code, county_name, cities = sys.argv[1], sys.argv[2], None
if sys.argv[3] == 'jefferson': cities = JEFFERSON_CITIES
seen = {}
failed = []
for city in cities:
    got = search(county_code, city, county_name)
    if got is None:
        failed.append(city); print(f"CITY FAILED {city}", flush=True); continue
    for p in got:
        k = (p['name'].upper(), p['zip'][:5], p['address'].split(' ')[0].upper())
        seen[k] = p
    print(f"{city}: {len(got)} (unique so far {len(seen)})", flush=True)
    time.sleep(1.5)
path = f"{OUT}/{county_code}.json"
json.dump(list(seen.values()), open(path, 'w'))
print(f"WROTE {path}: {len(seen)} places; failed cities: {failed}", flush=True)
