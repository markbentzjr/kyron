import requests, time
from bs4 import BeautifulSoup
UA = {"User-Agent": "KyronHealthApp/2.0 (probe)"}

def probe(county):
    s = requests.Session(); s.headers.update(UA)
    for a in range(4):
        try:
            r = s.get("https://foodscores.state.al.us/default.aspx", timeout=60)
            break
        except Exception:
            time.sleep(4)
    d = BeautifulSoup(r.text, 'html.parser')
    hv = lambda n: (d.find('input', {'name': n}) or {}).get('value', '')
    tsel = d.find('select', {'name': 'ctl00$ContentPlaceHolder1$DrpEstdType'})
    csel = d.find('select', {'name': 'ctl00$ContentPlaceHolder1$DrpCnty'})
    cval = 'Select County'
    for o in csel.find_all('option'):
        if o.get_text(strip=True).upper() == county.upper():
            cval = o.get('value')
    data = {'__VIEWSTATE': hv('__VIEWSTATE'), '__VIEWSTATEGENERATOR': hv('__VIEWSTATEGENERATOR'),
     '__EVENTVALIDATION': hv('__EVENTVALIDATION'),
     'ctl00$ContentPlaceHolder1$TxtEstdNm': '',
     'ctl00$ContentPlaceHolder1$DrpEstdType': tsel.find_all('option')[0].get('value'),
     'ctl00$ContentPlaceHolder1$txtCity': '',
     'ctl00$ContentPlaceHolder1$DrpCnty': cval,
     'ctl00$ContentPlaceHolder1$BtnSearch.x': '10', 'ctl00$ContentPlaceHolder1$BtnSearch.y': '10'}
    r2 = s.post(r.url, data=data, timeout=110)
    title = BeautifulSoup(r2.text, 'html.parser').title
    print(f"{county}: final_url={r2.url}")
    print(f"  history={[(h.status_code, h.headers.get('Location')) for h in r2.history]}")
    print(f"  title={title.get_text(strip=True) if title else None} bytes={len(r2.text)}", flush=True)

probe('Jefferson')
time.sleep(2)
probe('Mobile')
