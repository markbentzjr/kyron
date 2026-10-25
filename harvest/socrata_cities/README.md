# Socrata city/county harvest (NYC, Chicago, King County WA)

| key | Region | Dataset | Result model | Window |
|---|---|---|---|---|
| `nyc` | us-ny | NYC DOHMH `43nn-pn8j` (data.cityofnewyork.us) | PENALTY_LOW (violation points; grade A/B/C in result text) | source's own ~3 yrs |
| `chicago` | us-il | Chicago CDPH `4ijn-s7e5` (data.cityofchicago.org) | PASS_FAIL (no score; result text = Pass / Pass w/ Conditions / Fail …) | 2 years |
| `kingco` | us-wa | Seattle & King County `r878-4sxa` (data.kingcounty.gov) | PENALTY_LOW (red+blue points; result + rating in result text) | 2 years |

```bash
python3 harvest/socrata_cities/harvest.py nyc        # fetch -> normalize -> validate
python3 tools/packs/build_pack_socrata.py nyc        # -> out/nyc/us-ny-<date>.1.db.gz + us-ny.manifest.json
```

Outputs live in `out/<key>/` (gitignored; packs are 2–10 MB and are
published as release assets, not committed). Read-only HTTP GETs, no
app token required. Normalizers (`sources.py`) never invent scores or
coordinates: King County publishes no coordinates; NYC 0/0 coordinates
are dropped.

## Attribution / terms
- NYC Department of Health and Mental Hygiene, via NYC Open Data — NYC Open Data Terms of Use.
- City of Chicago, via the Chicago Data Portal — City of Chicago Data Portal Terms of Use.
- Public Health — Seattle & King County, via King County Open Data — King County open data terms.

The app must show the source agency and data date with every result and
note that data may lag the agency's own site.
