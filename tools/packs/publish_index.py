#!/usr/bin/env python3
"""Collect built region packs + manifests into dist/, write a pack index
(index.json: regionId -> manifest file, pack file, bytes, sha256) and,
when PACK_SIGNING_KEY (Ed25519 PEM) is set, a detached signature
index.json.sig (raw Ed25519 over index.json bytes, base64) via openssl.

The app-side check is: fetch index.json + index.json.sig, verify with
the bundled public key, then verify each pack's sha256 from the index.
"""
import base64, glob, hashlib, json, os, shutil, subprocess, sys, tempfile
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DIST = os.path.join(REPO, "dist")


def main():
    os.makedirs(DIST, exist_ok=True)
    entries = {}
    for man in sorted(glob.glob(os.path.join(REPO, "harvest", "**", "*.manifest.json"),
                                recursive=True)):
        m = json.load(open(man))
        pack = os.path.join(os.path.dirname(man), m["full"]["file"])
        if not os.path.exists(pack):
            continue
        sha = hashlib.sha256(open(pack, "rb").read()).hexdigest()
        if sha != m["full"]["sha256"]:
            sys.exit(f"sha mismatch {pack}")
        shutil.copy(pack, DIST)
        shutil.copy(man, DIST)
        entries[m["regionId"]] = {"manifest": os.path.basename(man),
                                  "file": m["full"]["file"], "bytes": m["full"]["bytes"],
                                  "sha256": sha, "datasetVersion": m["datasetVersion"],
                                  "placeCount": m["placeCount"]}
    idx = {"schema": 1, "generatedAt": datetime.now(timezone.utc).isoformat(),
           "packs": entries}
    ip = os.path.join(DIST, "index.json")
    with open(ip, "w") as f:
        json.dump(idx, f, indent=1, sort_keys=True)
    key = os.environ.get("PACK_SIGNING_KEY")
    if key:
        with tempfile.NamedTemporaryFile("w", delete=False) as k:
            k.write(key)
        sig = subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", k.name, "-rawin",
                              "-in", ip], capture_output=True, check=True).stdout
        os.unlink(k.name)
        open(ip + ".sig", "w").write(base64.b64encode(sig).decode())
        print("signed index.json")
    else:
        print("PACK_SIGNING_KEY not set: index.json left UNSIGNED")
    print(f"{len(entries)} packs -> {DIST}")


if __name__ == "__main__":
    main()
