import requests, time
from bs4 import BeautifulSoup
UA = {"User-Agent": "KyronHealthApp/2.0 (probe)"}

def search(name='', city='', county='', typeval=None):
    s = requests.Session(); s.headers.update(UA)
    r = s.get("https://foodscores.state.al.us/default.aspx", timeout=60)
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
    t0 = time.time()
    r2 = s.post(r.url, data=data, timeout=110)
    d2 = BeautifulSoup(r2.text, 'html.parser')
    dt = d2.find(id='ctl00_ContentPlaceHolder1_DtList')
    n = len(dt.find_all('td')) if dt else -1
    print(f"name={name!r} city={city!r} county={county!r} type={typeval!r} -> HTTP {r2.status_code} bytes={len(r2.text)} cells={n} in {time.time()-t0:.0f}s", flush=True)
    return d2

search(city='Birmingham', county='Jefferson', typeval='Food Service Establishment')
time.sleep(3)
d = search(name='McDonald', county='Jefferson')
if d:
    dt = d.find(id='ctl00_ContentPlaceHolder1_DtList')
    if dt:
        for td in dt.find_all('td')[:3]:
            print("  ", td.get_text(' ', strip=True)[:130], flush=True)
