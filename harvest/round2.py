import sys, json, os
src = open('/home/hatch/kyron-build/harvest/reharvest_dates.py').read()
exec(src.split('targets = []')[0])
OUT = '/home/hatch/kyron-build/harvest/adph'
# Tallapoosa (62) — never harvested
p = fetch_county('62', 'Tallapoosa')
if p:
    json.dump(p, open(f'{OUT}/62.json', 'w'))
    print(f"OK Tallapoosa: {len(p)} places, missing dates {sum(1 for r in p if not r.get('date'))}", flush=True)
else:
    print("FAILED Tallapoosa", flush=True)
# Etowah (28) — main pass failed; keep whichever file has fewer missing dates
old = json.load(open(f'{OUT}/28.json'))
old_nd = sum(1 for r in old if not r.get('date'))
p = fetch_county('28', 'Etowah')
if p and len(p) >= len(old) * 0.8:
    nd = sum(1 for r in p if not r.get('date'))
    if nd < old_nd:
        json.dump(p, open(f'{OUT}/28.json', 'w'))
        print(f"OK Etowah replaced: {len(p)} places, missing dates {nd} (was {old_nd})", flush=True)
    else:
        print(f"Etowah kept old (new missing {nd} >= old {old_nd})", flush=True)
else:
    print("FAILED Etowah retry — old file kept", flush=True)
print("ROUND2 DONE", flush=True)
