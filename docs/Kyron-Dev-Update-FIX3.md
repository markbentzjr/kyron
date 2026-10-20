# Kyron dev update — FIX3: the ic_search pathData fix (P0 root cause)

**Staged candidate:** `~/kyron-build/manual/Kyron-2.0-FIX3.apk`
**md5:** `239d2b234304a7099b8521e04d4308e7` (identical to the build output
`~/kyron-build/manual/Kyron-2.0.apk`)
**Badging:** package `com.kyronapp.kyron`, **versionCode 7 / versionName "2.0"**,
same debug cert as every prior build (SHA-256
`cb932a5158d51ff577be2ac5e40b3c30760aeb10248a31d26e2fe7db6af24f56`), so it
installs over the diagnostic ladder (vc4–6) on Mark's phone with no uninstall.
Size 6,727,118 bytes. **Not delivered to Mark** — CSDM reviews independent
pass 2 first, then Mark device-gates.
**Pre-fix snapshot:** `~/kyron-build/manual_snapshot_pre_fix3` (src verified
byte-identical to the FIX2 tree before any edit).

---

## 1. Root cause (pinned by the D1 device trace, Oct 14, 2026)

Mark's Z Fold7 crash trace (captured by the D1 diagnostic build) shows:
`MainActivity.onCreate → setContentView → InflateException` at
`activity_main` line 62 — a TextView inflating drawable `ic_search`
(0x7f070077) — caused by `java.lang.IllegalArgumentException` in
`android.util.PathParser`: *"S needs to be followed by a multiple of 4
floats. However, 10 float(s) are found."*

`res/drawable/ic_search.xml` carried corrupt pathData, a transcription
error in the hand-authored 2.1-wave icon set:

- Corrupt segment: `…9.5,3S3,5.91 3,9.5 **3,16 5.91,19 9.5,19**c…`
  (the S command is handed 10 floats)
- Canonical segment: `…9.5,3S3,5.91 3,9.5 **5.91,16 9.5,16**c…`
  (two clean 4-float S groups)

Why every sandbox audit passed while every vc3-era build died: aapt2
validates XML well-formedness, never pathData arity; Robolectric never
runs the native PathParser. The device-proven 9f2eab88 build predates
the vector icons (text glyphs), so it never carried the defect. D1's
breadcrumbs exonerated everything upstream on Mark's real data (attach,
startup providers, user-DB open, repository/regions, osmdroid,
WorkManager enqueue, onCreate end all completed) — the drawable was the
only failure.

## 2. The fix

`ic_search.xml`'s pathData was replaced with the canonical string. Final
canonical source, stated for byte-for-byte matching by the 2.1 team's
GitHub push:

> The `android:pathData` value in `res/drawable/ic_search_black_24.xml`
> inside **material-1.12.0.aar** (`com.google.android.material:material:1.12.0`,
> AOSP), extracted from `~/kyron-build/manual/deps/material-1.12.0.aar`.

Post-fix, the app file's pathData is verified **byte-identical** to that
AAR string. The full final value:

```
M15.5,14h-0.79l-0.28,-0.27C15.41,12.59 16,11.11 16,9.5 16,5.91 13.09,3 9.5,3S3,5.91 3,9.5 5.91,16 9.5,16c1.61,0 3.09,-0.59 4.23,-1.57l0.27,0.28v0.79l5,4.99L20.49,19l-4.99,-5zM9.5,14C7.01,14 5,11.99 5,9.5S7.01,5 9.5,5 14,7.01 14,9.5 11.99,14 9.5,14z
```

Binary-level confirmation in the staged APK: the compiled
`res/drawable/ic_search.xml` string pool contains the corrupt segment
`5.91,19 9.5,19` **0 times** and the canonical segment `5.91,16 9.5,16`
**exactly 1 time**.

## 3. Validator + full sweep (two dimensions kept separate)

New tool: **`~/kyron-build/manual/tools/validate_pathdata.py`** — a strict
pathData validator mirroring `android.util.PathParser` grammar: full
tokenizer (command letters; numbers incl. sign-as-separator, leading-dot
fractions, exponents; comma/whitespace separators), per-command arity
(M/L/T=2, H/V=1, C=6, S/Q=4, A=7, Z=0) with implicit-group repetition,
arc-flag value checks (A group params 4–5 must be 0/1), moveto-first and
non-empty rules. Any violation reports file, path index, command and the
offending float segment.

Sweep scope (this pass): every XML under
`~/kyron-build/manual/src/main/res` — **23 files carrying pathData, 25
pathData attributes**, confirmed complete by an independent grep for
`<path` elements across all of `src` (25 elements, all in
`res/drawable`, all carrying pathData; no pathData exists in layouts or
any other resource). Enumeration note: the 2.1 team's sweep counted
24 files / 27 attributes; the file-count difference is
`ic_launcher_background.xml`, which contains no pathData. No arity
disagreement resulted (below).

### (a) Arity-MALFORMED (crash-class — the only blocking dimension)

| File | Finding | Disposition |
|---|---|---|
| `ic_search.xml` | S handed 10 floats: `3 5.91 3 9.5 3 16 5.91 19 9.5 19` | **FIXED** — replaced with material-1.12.0.aar canonical string (byte-identical, §2) |
| all other 22 files (24 paths) | parse clean | unchanged |

This **agrees exactly** with the 2.1 team's independent validator sweep
(ic_search the only corrupt file). No discrepancy to adjudicate: my
tokenizer flags nothing beyond ic_search, and the arc-flag/exponent
edge cases did not diverge on this tree (the launcher foreground's arcs
use separator-delimited 0/1 flags; no path uses exponents or packed
flags).

Post-fix validator run over the production res:
`23 files, 25 path(s), 0 malformed — OK`.

### (b) Arity-valid but geometrically NON-CANONICAL (fidelity — non-blocking)

Six icons have a same-icon canonical counterpart inside this repo's own
library artifacts; token streams (command letters + floats, formatting
ignored) were diffed against them:

| App icon | Canonical source | Result |
|---|---|---|
| `ic_search` | material-1.12.0.aar `ic_search_black_24` | was DIFF (the corruption) → now **byte-identical** |
| `ic_arrow_back` | material-1.12.0.aar `ic_arrow_back_black_24` | token-identical — already canonical |
| `ic_edit` | material-1.12.0.aar `material_ic_edit_black_24dp` | token-identical — already canonical |
| `ic_close` | material-1.12.0.aar `ic_clear_black_24` | token-identical — already canonical |
| `ic_arrow_drop_down` | material-1.12.0.aar `mtrl_ic_arrow_drop_down` | token-identical — already canonical |
| `ic_star` | appcompat-1.7.0.aar `abc_star_black_48dp` | token-identical — already canonical |

The remaining 17 pathData files (check, chevron_right, delete,
directions, download, info, map, my_location, notifications, person,
place, share, star_border, sync, tune, warning, launcher foreground)
have no same-icon counterpart in the in-repo AARs; all are arity-valid
and were left byte-unchanged. One *unverified visual observation* (not a
sweep finding, not acted on): `ic_place`'s top-curve control segment
reads `c0,-2.87 …` where the published material-icons "place" path is
remembered as `c0,-3.87 …`; the path closes correctly and renders a
valid pin either way. Flagged for the 2.1 team's canonical pass to
confirm or dismiss against an authoritative source.

## 4. The build gate

`build_manual.sh` now runs the validator over `src/main/res` as a named
gate step immediately **before** "3/8 aapt2 compile resources". On any
malformed path the build exits 1 with the validator's file + segment
output and a refusal message — a bad path can no longer reach aapt2.

Gate proof (scratch tree, production tree untouched): with `ic_check.xml`
deliberately corrupted (an L command handed 3 floats: `4.83 12 99`), the
build stopped at the gate, before aapt2, exit 1:

```
=== gate: validate vector pathData ===
MALFORMED …/scratch_gate/manual/src/main/res/drawable/ic_check.xml [path #1]:
L needs to be followed by a multiple of 2 floats. However, 3 float(s) are found: 4.83 12 99
BUILD FAILED: malformed vector pathData above (file + segment named).
```

Full log: `~/kyron-build/manual/build_gate_proof.log`. The production
build's own log (`build_fix3.log`) shows the gate passing
(23 files, 25 paths, 0 malformed) before aapt2 ran.

## 5. What FIX3 is (and is not)

FIX2 configuration, unchanged except §2 + version: classic
AppCompat/classic-Views UI, LF-4 data layer, and all prior fixes (F-1/F-2
pack validation, FTS onOpen probe, scheduleSync hardening, F-6 rig
guard). Rebuilt from source via the gated pipeline. **No diagnostic
harness**: string sweep of the staged APK finds zero occurrences of
`CrashDiag`, `CrashReportActivity`, `kyron-diag`, or any `diag-d*`
version name; badging is the clean versionCode 7 / "2.0".

## 6. Pass-1 verification (this agent; independent pass 2 still to come)

Robolectric harness (`~/kyron-build/test/run_one.sh`), all against the
FIX3 build's classes:

| Suite | Result |
|---|---|
| StartupUpgradeTest (unguarded onCreate, faithful pre-LF4 fixture) | **OK (3 tests)** |
| Lf4Test (incl. F-1/F-2 pack-attack regressions) | **OK (9 tests)** |
| DbTest | **OK (3 tests)** |
| GeoTest | **OK (1 test)** |
| PerfTest | **OK (1 test)** |
| QaAdvTest + QaLikeTest | **OK (8 tests)** |

Audits on the staged APK (`239d2b23…`):

- **Dex audit** (`tools/dex_audit.py`): 2 dexes, 7,845 defined classes,
  9,293 referenced types. Referenced-but-undefined set = **exactly the
  13 known-benign** from FIX2 (BouncyCastle/Conscrypt/OpenJSSE TLS
  providers ×10 incl. jspecify `NullMarked`, XmlPull ×3) — **zero new
  missing**. R classes: 599 (matches FIX2 and the device-proven profile).
- **R↔arsc audit**: 0 absent, 0 type/name mismatches across 65,100 R
  constants by this pass's census (the FIX2 pass counted 53,935 with a
  different census method; substance agrees). Stronger identity check:
  the `resources.arsc` id→(type,name) maps of FIX2 and FIX3 are
  **byte-identical (1,541 entries each)** — the only resource change in
  the binary is the ic_search string value.
- **Production-policy sweep**: zero hits for `kyronfoodsafety`,
  `geocodio`/Geocodio, and key-shaped strings (`AIza…`, `ghp_…`, `AKIA…`,
  `sk-…`, valued `api_key=`) across all APK files. The single bare
  `apikey=` occurrence is the known valueless osmdroid library literal,
  unchanged from prior passes. Guest-first untouched (no auth code
  exists in the tree).
- **Validator report**: §3 — 23 files / 25 paths, **0 malformed**;
  gate wired and proven (§4).

## 7. Residual unknown, stated plainly

No sandbox executes the real-device native PathParser, so a real-device
first frame still cannot be run here. What is different from FIX2: the
*failure itself* is no longer inferred — it was captured on device,
traced to one string, and that exact string is verifiably absent from
this binary (0 occurrences of the corrupt segment; the S-command arity
defect class is now build-gated for every drawable). Mark's device gate
remains the final closer, per the binding release gate.
