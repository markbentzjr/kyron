# Kyron FIX3 — Independent Pass-2 QA Report (bug-hunt)

**Candidate:** `~/kyron-build/manual/Kyron-2.0-FIX3.apk`
**md5 (verified before and after all QA work):** `239d2b234304a7099b8521e04d4308e7`
**Badging (verified):** package `com.kyronapp.kyron`, **versionCode 7 / versionName "2.0"**,
signing cert SHA-256 `cb932a5158d51ff577be2ac5e40b3c30760aeb10248a31d26e2fe7db6af24f56`
— identical to FIX2 and every prior build, so it installs over the diagnostic
ladder (vc4–6) on Mark's phone.

## Verdict: **SHIP** — for CSDM review

Every decisive builder claim in `Kyron-Dev-Update-FIX3.md` was re-verified
independently (own AXML parser, own pathData tokenizer, own dex parser, own
gate re-proof, own test runs). No discrepancies found. **Mark's Z Fold7
device gate remains the final closer** — no sandbox executes the native
PathParser or a real-device first frame, and per the binding release gate
nothing is "ready" until his phone opens this exact md5.

---

## 1. Binary-level path audit — the decisive check (PASS)

I wrote my own binary-AXML parser (string-pool + start-element walk) and my
own `android.util.PathParser`-grammar arity validator (M/L/T=2, H/V=1, C=6,
S/Q=4, A=7 with implicit-group repetition and single-char arc flags), and ran
it over **every pathData in the compiled FIX3 APK** — not the source:

- **55 files / 62 pathData attributes** (the app's 23 icons + AppCompat /
  library vectors, animators, interpolators): **0 malformed.**
- Compiled `res/drawable/ic_search.xml` in FIX3 carries the canonical string:
  corrupt segment `5.91,19` **absent**, canonical `5.91,16 9.5,16` **present**.

**Negative control (proves the audit has teeth):** the identical audit run
against FIX2's APK flags **exactly 1 malformed path** — `ic_search.xml` —
with the error text matching the D1 device trace verbatim:
*"S needs to be followed by a multiple of 4 floats. However, 10 float(s) are
found: 3 5.91 3 9.5 3 16 5.91 19 9.5 19."* Unit probes of my tokenizer:
corrupt S (flagged), L handed 3 floats (flagged), packed arc flags
(`a7,7 0 115,15`), exponents (`1e-3`), sign-as-separator (`5-3`), and
leading-dot fractions (`.5`) all tokenize per spec.

## 2. Canonical identity (PASS)

Independently extracted `res/drawable/ic_search_black_24.xml` from
`manual/deps/material-1.12.0.aar` and byte-compared its `android:pathData`
with the app's source `res/drawable/ic_search.xml`: **byte-identical.**
The canonical source stated in the FIX3 changelog is the real one — the
2.1 team's GitHub push can match it byte-for-byte.

## 3. Build-gate proof — my own re-proof (PASS)

`build_manual.sh` lines 43–52 run `tools/validate_pathdata.py` as a named
gate step immediately before "3/8 aapt2 compile resources" and exit 1 on
any malformed path. Re-proven in a scratch tree under a fake HOME
(production tree untouched), with **my own corruption** (different file
and command than the builder's proof: `ic_tune.xml`, an M handed 3 floats):

- Corrupted run: **exit 1 at the gate**, output names the file and the
  offending segment (`3 17 4`); the string "aapt2 compile resources"
  appears **0 times** — the build never reached aapt2.
- Positive control (drawable restored): gate passes (23 files, 25 paths,
  0 malformed) and the build proceeds into step 3/8.

## 4. Sweep-disagreement check (PASS — consensus holds)

Three independent tokenizers now agree that ic_search was the only
malformed vector: the 2.1 team's, the builder's, and mine. My own source
sweep post-fix: **23 files / 25 pathData attributes / 0 malformed**, and a
`<path` census over all of `src` (23 files, 25 attributes, all in
`res/drawable`) confirms the sweep scope is complete — no pathData hides
in layouts or other resources. I re-ran the builder's validator myself on
the production res (OK) and on a re-corrupted copy of ic_search (it
refuses, naming the exact segment). The arc-flag/exponent edge cases the
CSDM flagged as suspect divergence points do not diverge on this tree.
**No discrepancy to adjudicate.**

## 5. Regression suite — my runs, against the FIX3 build (PASS)

Harness runs compile/run against `work/classes.jar` + the extracted FIX3
APK (`Kyron-2.0.apk`, md5-verified identical to the staged FIX3):

| Suite | Result (mine) |
|---|---|
| StartupUpgradeTest (unguarded onCreate, pre-LF4 fixture) | **OK (3 tests)** |
| Lf4Test (incl. F-1/F-2 pack attacks) | **OK (9 tests)** |
| DbTest | **OK (3 tests)** |
| QaAdvTest | **OK (7 tests)** |
| QaLikeTest | **OK (1 test)** |
| GeoTest | **OK (1 test)** |
| PerfTest | **OK (1 test)** |

25 tests, all green — the builder's claimed results reproduce exactly.

Method note: QaAdvTest / QaLikeTest / PerfTest exist only as pre-compiled
harness classes (sources absent from the tree, as prior passes recorded);
I ran them via direct JUnitCore on the harness classpath against FIX3's
classes — the same method prior passes used. (Trap documented for future
passes: `run_one.sh <Class>` with no source arguments drops `kotlinc`
into its interactive REPL and waits forever; the class-name-only
invocation is not a valid way to run these suites.)

**Classified non-failure:** `BaselineTest` fails with
`FileNotFoundException: robo-apk/assets/places_seed.json`. It is an
LF-0-era test hardcoding the pre-geocoding asset name; the seed has
shipped as `assets/places_seed_geocoded.json` (7,146,478 bytes, identical
in FIX2 and FIX3) since the LF-1 wave, so this test fails identically on
FIX2 — a stale test already filed on the backlog for retirement, **not**
a FIX3 regression. GeoTest, the current seed test, passes.

## 6. Audits — my own parsers (PASS)

- **Dex:** 2 dexes; **7,845 defined / 9,293 referenced types** (matches the
  builder's census numbers exactly). The referenced-but-undefined type
  **sets are set-identical between FIX2 and FIX3** (empty diff both ways)
  — zero new undefined classes under one consistent method. All **13
  known-benign** entries are present in both builds (BouncyCastle ×3,
  Conscrypt ×3, OpenJSSE ×3, jspecify `NullMarked`, XmlPull ×3).
- **R↔arsc:** `resources.arsc` is **byte-identical** between FIX2 and FIX3
  (306,876 bytes) — stronger than the claimed id-map identity. My R-class
  census counts 595 defined R classes in each build (the builder's 599
  uses a different counting convention; the FIX2 pass-2 documented the
  same +4 method offset — under any single method, FIX2 == FIX3).
- **Production-policy sweep** over the raw FIX3 APK bytes: **0 hits** for
  `kyronfoodsafety`, `geocodio`/`Geocodio`, and key-shaped strings
  (`AIza`, `ghp_`, `AKIA`, `sk-live`, valued `api_key=`/`apikey=`).
- **No diagnostic remnants:** 0 hits for `CrashDiag`,
  `CrashReportActivity`, `kyron-diag`, `diag-d1/d2/d3`, `breadcrumb`.
  Badging is the clean versionCode 7 / "2.0" (FIX2 was vc3 / "2.1").

## 7. Diff discipline — FIX3 vs FIX2 (PASS)

Zip-level diff: 498 entries in each, none added or removed. **Exactly 5
entries changed:** `AndroidManifest.xml` (same size — the vc3/"2.1" →
vc7/"2.0" stamp), the three `META-INF` signature files (expected), and
**`res/drawable/ic_search.xml` (804 → 800 bytes)**. `classes.dex` and
`classes2.dex` have identical CRCs — the code is byte-identical to FIX2;
`resources.arsc` is byte-identical (§6). The FIX3 delta is confined to
exactly what was ordered: the one icon string + the version stamp (the
validator + build gate are source-side and do not ship in the APK). The
compiled ic_search strings extracted from both APKs differ only in the
one segment: `3,16 5.91,19 9.5,19` (FIX2) → `5.91,16 9.5,16` (FIX3).

## Residual unknowns, stated plainly

- No sandbox runs the real-device native PathParser; the case rests on
  the device-captured crash string being verifiably absent from this
  binary, the arity defect class being build-gated, and every other
  system in the build being byte-identical to the FIX2 configuration
  whose upstream startup the D1 breadcrumbs exonerated on Mark's real
  data. **Mark's device gate on md5 `239d2b23…` is the final closer.**
- The builder's `ic_place` observation (a possible `2.87` vs `3.87`
  control point vs. the remembered published path) is arity-valid,
  renders a valid pin either way, and remains an unverified visual nit
  for the 2.1 team's canonical pass — not a finding, not blocking.

**Nothing was delivered to Mark; `~/workspace/your_files/` was not
touched.** Verdict **SHIP** is for the CSDM's review under the binding
release gate.
