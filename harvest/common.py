#!/usr/bin/env python3
"""Shared harvest plumbing — the parts every adapter family used to
carry a private copy of. Family-specific parsing/normalizing stays in
the family module; this file owns only the parts that were
byte-identical everywhere:

  UA               the canonical KyronHarvest User-Agent
  fetch/fetch_json GET with the shared UA + one retry (flaky portals)
  validate_places  the standard gate: dup ids, empty names,
                   geo/provenance mismatch, inspection dates, score range
  emit             the standard artifact set (places.json,
                   fetch_log.json, validate_report.json,
                   exclusions.json, manifest.json) written to out/<key>/

The ASP.NET session harvesters (sfi, dhd, mhd) keep their bespoke
fetchers (viewstate/cookies/referers) — this module is for the adapters
that fetch plain GET endpoints and emit the standard artifact set.
"""
import hashlib
import json
import os
import time
import urllib.request

UA = "KyronHarvest/1.0 (public data; github.com/markbentzjr/kyron)"
NO_SCORE = -1


def fetch(url, *, timeout=300, retries=1, ua=UA, headers=None):
    """GET url -> body bytes, shared UA, `retries` extra attempts."""
    hdrs = {"User-Agent": ua}
    if headers:
        hdrs.update(headers)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if attempt == retries:
                raise RuntimeError(f"GET failed: {e!r} {url[:120]}") from e
            time.sleep(5)


def fetch_json(url, **kw):
    return json.loads(fetch(url, timeout=180, **kw).decode("utf-8"))


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def validate_places(places, *, forbid_scores=False, score_max=300):
    """The standard normalized-record gate every family writes:
    duplicate ids, empty names, geo/provenance mismatch, inspections
    without dates, and score-range sanity. `forbid_scores` covers
    PASS_FAIL / VIOLATIONS_ONLY families where any numeric score is a
    fabrication."""
    errs = []
    ids = set()
    for p in places:
        if p["id"] in ids:
            errs.append(f"duplicate id {p['id']}")
        ids.add(p["id"])
        if not p["n"]:
            errs.append(f"{p['id']}: empty name")
        if (p["lat"] is None) != (p["gs"] != "ACCEPTED"):
            errs.append(f"{p['id']}: geo/provenance mismatch")
        for i in p["insp"]:
            if forbid_scores and i["s"] != -1:
                errs.append(f"{p['id']}: inspection has a score")
            if i["s"] != -1 and not (0 <= i["s"] <= score_max):
                errs.append(f"{p['id']}: score out of range {i['s']}")
            if not i["d"]:
                errs.append(f"{p['id']}: inspection without date")
    return {"places": len(places),
            "inspections": sum(len(p["insp"]) for p in places),
            "violations": sum(len(i["v"]) for p in places for i in p["insp"]),
            "with_coords": sum(p["lat"] is not None for p in places),
            "errors": errs[:50], "error_count": len(errs)}


def emit(out_dir, **files):
    """Write the standard artifact set. `emit(out, places=…,
    fetch_log=…, validate_report=…, exclusions=…, manifest=…)` writes
    places.json, fetch_log.json, … — kwarg name becomes the filename.
    All output is UTF-8; NEVER rely on the platform default encoding
    (cp1252 mojibake corrupted non-ASCII names in earlier packs —
    read side is equally affected: always open() with encoding='utf-8').
    """
    os.makedirs(out_dir, exist_ok=True)
    for name, obj in files.items():
        with open(os.path.join(out_dir, name + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
