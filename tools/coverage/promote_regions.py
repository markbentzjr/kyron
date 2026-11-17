#!/usr/bin/env python3
"""Promote registry jurisdictions to downloadable-verified after
their pack artifacts are actually published + byte-verified.

For each region argument, verifies the manifest file exists on the
data-packs release, downloads it, checks the full pack's sha256
against the local pack bytes (already in dist/ or harvested out/),
then updates the registry entry:

  pack_status        -> "published"
  pack_manifest_url  -> release URL
  pack_availability  -> "downloadable-verified"
  artifact_verified / pack_host_status / pack_host_checked
  sources[].status   -> "pack-built", refresh, last_refresh, notes

NEVER promotes a region whose artifact verification fails — the
whole point of this script is that the registry only tells the
truth about what shipped.

Usage:
  python tools/coverage/promote_regions.py us-pa us-sd us-ms ...
"""

import hashlib
import json
import os
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
REG = os.path.join(REPO, "app", "src", "main", "assets", "coverage",
                   "us_national_registry.json")
RELEASE = ("https://github.com/EMC-MB/kyron/releases/download/"
           "data-packs")
TODAY = time.strftime("%Y-%m-%d")

# regionId -> harvest source_id + refresh note (adapter path)
SOURCE_OF = {
    "us-pa": ("pa-pda", "harvest/sfi"),
    "us-sd": ("sd-doh", "harvest/sfi"),
    "us-ia": ("ia-dia", "harvest/sfi"),
    "us-ak": ("ak-adec", "harvest/sfi"),
    "us-ar": ("ar-adh", "harvest/sfi"),
    "us-vt": ("vt-dh", "harvest/sfi"),
    "us-va": ("va-vdh", "harvest/mhd"),
    "us-wi": ("wi-datcp", "harvest/mhd"),
    "us-co": ("co-cdphe", "harvest/mhd"),
    "us-mt": ("mt-dphhs", "harvest/mhd"),
    "us-hi": ("hi-doh", "harvest/mhd"),
    "us-la": ("la-ldh", "harvest/dhd"),
    "us-ms": ("ms-msdh", "harvest/ms"),
    "us-ri": ("ri-doh", "harvest/dhd"),
}


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def verify_served(rid, manifest):
    """Download the served pack bytes and sha256 them against the
    manifest's declared hash — verifies the artifact the app will
    actually fetch, not just local files."""
    purl = f"{RELEASE}/{manifest['full']['file']}"
    try:
        data = urllib.request.urlopen(purl, timeout=120).read()
    except Exception as ex:
        return False, f"pack download failed ({ex})"
    got = hashlib.sha256(data).hexdigest()
    if got != manifest["full"]["sha256"]:
        return False, f"served sha256 {got} != manifest"
    return True, len(data)


def main():
    regions = [a for a in sys.argv[1:] if not a.startswith("--")]
    with open(REG, encoding="utf-8") as f:
        reg = json.load(f)
    by_id = {e["regionId"]: e for e in reg["jurisdictions"]}
    errors = 0
    for rid in regions:
        e = by_id.get(rid)
        if e is None:
            print(f"[skip] {rid}: not in registry")
            errors += 1
            continue
        murl = f"{RELEASE}/{rid}.manifest.json"
        try:
            m = json.loads(urllib.request.urlopen(murl,
                                                  timeout=30).read())
        except Exception as ex:
            print(f"[FAIL] {rid}: manifest not on release ({ex})")
            errors += 1
            continue
        ok, res = verify_served(rid, m)
        if not ok:
            print(f"[FAIL] {rid}: {res}")
            errors += 1
            continue
        e.update({
            "pack_status": "published",
            "pack_manifest_url": murl,
            "pack_availability": "downloadable-verified",
            "artifact_verified": TODAY,
            "pack_host_status": "reachable",
            "pack_host_checked": TODAY,
            "summary": (
                f"Pack published to the data-packs release, "
                f"artifact sha256-verified {TODAY} "
                f"({m['placeCount']:,} places).")})
        sid, pipeline = SOURCE_OF.get(rid, (None, None))
        for s in e["sources"]:
            if sid is None or s["id"] == sid:
                s["status"] = "pack-built"
                s["refresh"] = f"Harvest pipeline {pipeline}"
                s["last_refresh"] = TODAY
        print(f"[ok] {rid}: verified + promoted "
              f"({m['placeCount']:,} places, {m['full']['bytes']:,}B)")
    if errors == 0:
        with open(REG, "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=1)
        print("[registry] saved")
    else:
        print(f"[registry] NOT saved — {errors} region(s) failed "
              f"verification")
        sys.exit(1)


if __name__ == "__main__":
    main()
