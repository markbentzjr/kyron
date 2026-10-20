from bs4 import BeautifulSoup
import re, json
d = BeautifulSoup(open('/home/hatch/kyron-build/harvest/adph_auburn.html', encoding='utf-8', errors='replace').read(), 'html.parser')
dt = d.find('table', {'id': 'ctl00_ContentPlaceHolder1_DtList'}) or d.find(id='ctl00_ContentPlaceHolder1_DtList')
print("DtList tag:", dt.name if dt else None)
items = dt.find_all('td', recursive=True) if dt else []
# DataList renders one item per cell typically
seen = []
for td in dt.find_all('td'):
    txt = td.get_text(' | ', strip=True)
    if txt and len(txt) > 15: seen.append(txt)
print("cells with text:", len(seen))
for t in seen[:6]: print("CELL:", t[:300])
links = [a.get('href') for a in dt.find_all('a')]
print("links in DtList:", len(links), links[:5])
# look for score-like numbers patterns
scores = re.findall(r'\b(100|[0-9]{2})\b', dt.get_text(' '))
print("sample text:", dt.get_text(' ', strip=True)[:600])
