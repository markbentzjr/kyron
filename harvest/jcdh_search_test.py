import requests
from bs4 import BeautifulSoup
s = requests.Session(); s.headers.update({"User-Agent":"KyronHealthApp/2.0 (data verification)"})
url = "https://www.jcdh.org/SitePages/Programs-Services/Scores-Lists/Food/FoodServScores.aspx"
r = s.get(url, timeout=60)
d = BeautifulSoup(r.text, 'html.parser')
hv = lambda n: (d.find('input', {'name': n}) or {}).get('value', '')
data = {'__VIEWSTATE': hv('__VIEWSTATE'), '__VIEWSTATEGENERATOR': hv('__VIEWSTATEGENERATOR'),
 '__EVENTVALIDATION': hv('__EVENTVALIDATION'),
 'ctl00$MainContent$txtBKeyword': 'BBQ', 'ctl00$MainContent$btnSearch': 'Search'}
r2 = s.post(url, data=data, timeout=110)
print("POST", r2.status_code, len(r2.text))
d2 = BeautifulSoup(r2.text, 'html.parser')
gv = d2.find('table', {'id': 'MainContent_gvFoodScores'})
rows = gv.find_all('tr') if gv else []
print("result rows:", len(rows))
for row in rows[1:4]:
    print("  ", [c.get_text(' ', strip=True)[:70] for c in row.find_all('td')])
# pager?
pg = d2.find(class_='pager') or d2.select('[id*=Pager]')
print("pager elements:", len(pg) if pg else 0)
links = [a.get_text(strip=True) for a in d2.find_all('a') if a.get_text(strip=True).isdigit()]
print("numeric links (pages?):", links[:10])
