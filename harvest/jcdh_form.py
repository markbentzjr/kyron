from bs4 import BeautifulSoup
d = BeautifulSoup(open('/tmp/jcdh.html', encoding='utf-8', errors='replace').read(), 'html.parser')
for inp in d.find_all(['input','select','button']):
    n = inp.get('name') or inp.get('id')
    if n and 'MainContent' in str(n): print(inp.name, inp.get('type'), n, (inp.get('value') or '')[:30])
