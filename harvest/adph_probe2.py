import requests, time
from bs4 import BeautifulSoup
UA = {"User-Agent": "KyronHealthApp/2.0 (probe)"}

def get_form(s):
    for a in range(4):
        try:
            r = s.get("https://foodscores.state.al.us/default.aspx", timeout=60)
            return r
        except Exception as e:
            print("GET retry", a, type(e).__name__, flush=True); time.sleep(4)

def search(name='', city='', county='', typeval=None):
    s = requests.Session(); s.headers.update(UA)
    r = get_form(s)
    d = BeautifulSoup(r.text, 'html.parser')
    hv = lambda n: (d.find('input', {'name': n}) or {}).get('value', '')
    tsel = d.find('select', {'name': 'ctl00$ContentPlaceHolder1$DrpEstdType'})
    if typeval is None:
        typeval = tsel.find_all('option')[0].get('value')
    csel = d.find('select', {'name': 'ctl00$ContentPlaceHolder1$DrpCnty'})
    cval = 'Select County'
    if county:
        for o in csel.find_all('option'):
            if o.get_text(strip=True).upper() == county.upper():
                cval = o.get('value')
    data = {'__VIEWSTATE': hv('__VIEWSTATE'), '__VIEWSTATEGENERATOR': hv('__VIEWSTATEGENERATOR'),
     '__EVENTVALIDATION': hv('__EVENTVALIDATION'),
     'ctl00$ContentPlaceHolder1$TxtEstdNm': name,
     'ctl00$ContentPlaceHolder1$DrpEstdType': typeval,
     'ctl00$ContentPlaceHolder1$txtCity': city,
     'ctl00$ContentPlaceHolder1$DrpCnty': cval,
     'ctl00$ContentPlaceHolder1$BtnSearch.x': '10', 'ctl00$ContentPlaceHolder1$BtnSearch.y': '10'}
    r2 = s.post(r.url, data=data, timeout=110)
    return r2

r2 = search(city='Birmingham', county='Jefferson', typeval='Food Service Establishment')
open('/home/hatch/kyron-build/harvest/bham_fse.html', 'w').write(r2.text)
d2 = BeautifulSoup(r2.text, 'html.parser')
print("tables:", [(t.get('id'), len(t.find_all('tr'))) for t in d2.find_all('table')][:12])
txt = d2.get_text(' ', strip=True)
import re
for kw in ['too many', 'narrow', 'records', 'found', 'results', 'exceed', 'limit', 'refine']:
    for m in re.finditer(kw, txt, re.I):
        print(f"CTX[{kw}]:", txt[max(0, m.start()-90):m.start()+110].replace('\n', ' '))
        break
print("DtList present:", d2.find(id='ctl00_ContentPlaceHolder1_DtList') is not None)
# any label-ish spans with messages
for sp in d2.find_all(['span', 'div']):
    t = sp.get_text(' ', strip=True)
    if t and len(t) < 220 and ('result' in t.lower() or 'record' in t.lower() or 'search' in t.lower()):
        print("MSG:", t)
