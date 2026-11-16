# Kyron harvest folders — all 50 states + D.C.

_Generated 2026-11-16 — rerun `tools/coverage/gen_state_harvest_dirs.py`._

One folder per jurisdiction (`harvest/<st>/SOURCES.md`) records the
official source(s), access type and pack status — the registry is the
source of truth. Family adapters (sfi, mhd, dhd, socrata_cities) are
shared pipelines that serve many states; state folders point at them.

| state | pack | availability | pipeline |
|---|---|---|---|
| [AL](al/SOURCES.md) | bundled | bundled | harvest/ root (adph_*.py, jcdh_*.py, mchd_harvest.py) — bundled seed |
| [FL](fl/SOURCES.md) | published | downloadable-verified | harvest/fl_dbpr/ — published pack |
| [GA](ga/SOURCES.md) | published | declared-only | harvest/ga/ — pack built, NOT yet published |
| [TN](tn/SOURCES.md) | published | downloadable-verified | harvest/tn/ — published pack |
| [SC](sc/SOURCES.md) | published | downloadable-verified | harvest/sc/ — published pack |
| [NC](nc/SOURCES.md) | none | none | harvest/nc/ — pipeline exists; blocked on cdpehs_lib helper |
| [MS](ms/SOURCES.md) | none | none | — |
| [VA](va/SOURCES.md) | none | none | harvest/mhd/ — MyHealthDepartment adapter |
| [AR](ar/SOURCES.md) | none | none | harvest/sfi/ — SafeFoodInspection adapter |
| [LA](la/SOURCES.md) | none | none | — |
| [PA](pa/SOURCES.md) | none | none | harvest/sfi/ — SafeFoodInspection adapter |
| [NY](ny/SOURCES.md) | built | staged-local | harvest/socrata_cities/ — nyc source |
| [IL](il/SOURCES.md) | built | staged-local | harvest/socrata_cities/ — chicago source |
| [CA](ca/SOURCES.md) | published | downloadable-verified | harvest/socrata_cities/ — sf source (San Francisco only) |
| [MA](ma/SOURCES.md) | none | none | — |
| [WA](wa/SOURCES.md) | built | staged-local | harvest/socrata_cities/ — kingco source (King County only) |
| [OR](or/SOURCES.md) | none | none | harvest/mhd/ — MyHealthDepartment adapter |
| [WI](wi/SOURCES.md) | none | none | harvest/mhd/ — MyHealthDepartment adapter (proof pack only) |
| [OK](ok/SOURCES.md) | none | none | — |
| [VT](vt/SOURCES.md) | none | none | harvest/sfi/ — SafeFoodInspection adapter |
| [SD](sd/SOURCES.md) | none | none | harvest/sfi/ — SafeFoodInspection adapter |
| [WY](wy/SOURCES.md) | none | none | harvest/sfi/ — SafeFoodInspection adapter |
| [RI](ri/SOURCES.md) | none | none | harvest/dhd/ — healthinspections.us adapter |
| [NJ](nj/SOURCES.md) | none | none | — |
| [NV](nv/SOURCES.md) | published | downloadable-verified | harvest/snhd/ — published pack (Clark County only) |
| [TX](tx/SOURCES.md) | published | downloadable-verified | harvest/socrata_cities/ — austin source (Austin only) |
| [UT](ut/SOURCES.md) | none | none | — |
| [MI](mi/SOURCES.md) | none | none | — |
| [MD](md/SOURCES.md) | published | downloadable-verified | harvest/socrata_cities/ — montgomery source |
| [MO](mo/SOURCES.md) | none | none | — |
| [MN](mn/SOURCES.md) | none | none | — |
| [MT](mt/SOURCES.md) | none | none | harvest/mhd/ — MyHealthDepartment adapter |
| [NE](ne/SOURCES.md) | none | none | — |
| [NH](nh/SOURCES.md) | none | none | — |
| [NM](nm/SOURCES.md) | none | none | — |
| [ND](nd/SOURCES.md) | none | none | — |
| [WV](wv/SOURCES.md) | none | none | — |
| [AZ](az/SOURCES.md) | none | none | — |
| [CO](co/SOURCES.md) | none | none | harvest/mhd/ — MyHealthDepartment adapter (proof pack only) |
| [AK](ak/SOURCES.md) | none | none | harvest/sfi/ — SafeFoodInspection adapter |
| [HI](hi/SOURCES.md) | none | none | harvest/mhd/ — MyHealthDepartment adapter |
| [CT](ct/SOURCES.md) | none | none | — |
| [DE](de/SOURCES.md) | published | downloadable-verified | harvest/de_socrata/ — published pack |
| [ID](id/SOURCES.md) | none | none | — |
| [IA](ia/SOURCES.md) | none | none | harvest/sfi/ — SafeFoodInspection adapter |
| [KS](ks/SOURCES.md) | none | none | — |
| [ME](me/SOURCES.md) | none | none | — |
| [KY](ky/SOURCES.md) | none | none | — |
| [IN](in/SOURCES.md) | none | none | — |
| [OH](oh/SOURCES.md) | none | none | — |
| [DC](dc/SOURCES.md) | none | none | — |

Legacy family folders kept where they are: `de_socrata/`, `fl_dbpr/`,
`ga/`, `nc/`, `sc/`, `snhd/`, `tn/` (state pipelines) and `dhd/`,
`mhd/`, `sfi/`, `socrata_cities/` (multi-state adapters). Alabama's
seed pipeline lives at this directory's root (`adph_*.py`, `jcdh_*.py`).
