import requests, sys
from bs4 import BeautifulSoup
s = requests.Session()
s.headers.update({"User-Agent":"KyronHealthApp/2.0 (data verification)"})
r = s.get("https://foodscores.state.al.us/default.aspx", timeout=60)
print("GET", r.status_code, r.url, len(r.text))
d = BeautifulSoup(r.text, 'html.parser')
def hv(n):
    el = d.find('input', {'name': n}); return el.get('value','') if el else ''
sel = d.find('select', {'name': 'ctl00$ContentPlaceHolder1$DrpCnty'})
opts = {o.get_text(strip=True).upper(): o.get('value') for o in sel.find_all('option')}
print("counties:", len(opts), "| JEFFERSON:", opts.get('JEFFERSON'), "| MOBILE:", opts.get('MOBILE'), "| LEE:", opts.get('LEE'), "| MONTGOMERY:", opts.get('MONTGOMERY'))
tsel = d.find('select', {'name': 'ctl00$ContentPlaceHolder1$DrpEstdType'})
data = {'__VIEWSTATE': hv('__VIEWSTATE'), '__VIEWSTATEGENERATOR': hv('__VIEWSTATEGENERATOR'),
 '__EVENTVALIDATION': hv('__EVENTVALIDATION'),
 'ctl00$ContentPlaceHolder1$TxtEstdNm': '',
 'ctl00$ContentPlaceHolder1$DrpEstdType': tsel.find_all('option')[0].get('value'),
 'ctl00$ContentPlaceHolder1$txtCity': 'Auburn',
 'ctl00$ContentPlaceHolder1$DrpCnty': opts.get('LEE','41'),
 'ctl00$ContentPlaceHolder1$BtnSearch.x': '10', 'ctl00$ContentPlaceHolder1$BtnSearch.y': '10'}
try:
    r2 = s.post(r.url, data=data, timeout=110)
    print("POST", r2.status_code, len(r2.text))
    open('/home/hatch/kyron-build/harvest/adph_auburn.html','w').write(r2.text)
    d2 = BeautifulSoup(r2.text, 'html.parser')
    gv = d2.find('table', {'id': lambda x: x and 'gvSearchResults' in x})
    if gv:
        rows = gv.find_all('tr')
        print("gvSearchResults rows:", len(rows))
        for row in rows[:5]:
            cells = [c.get_text(' ', strip=True) for c in row.find_all(['td','th'])]
            links = [a.get('href') for a in row.find_all('a')]
            print(" ROW:", cells, "| links:", links[:2])
    else:
        print("tables:", [(t.get('id'), len(t.find_all('tr'))) for t in d2.find_all('table')][:10])
except Exception as e:
    print("POST failed:", type(e).__name__, str(e)[:200])
