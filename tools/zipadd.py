#!/usr/bin/env python3
"""Tiny `zip -r` replacement for the Windows-local build harness.

Usage: zipadd.py <archive> <path1> [path2 ...]
Adds every file under each path into the archive (paths preserved as given,
same semantics Git-for-Windows was missing `zip` for). Creates the archive
if missing; otherwise appends. No compression (APK-safe either way).
"""
import sys, zipfile, os

def main(argv):
    archive, paths = argv[1], argv[2:]
    arcroot = os.path.abspath(archive)
    mode = "a" if os.path.exists(arcroot) else "w"
    n = 0
    with zipfile.ZipFile(arcroot, mode, zipfile.ZIP_DEFLATED) as z:
        existing = set(z.namelist())
        for p in paths:
            ap = os.path.abspath(p)
            if os.path.isfile(ap):
                rel = p.replace("\\", "/")
                if rel.startswith("./"): rel = rel[2:]
                if rel not in existing:
                    z.write(ap, rel); n += 1
                continue
            base = os.path.dirname(ap.rstrip(os.sep))
            for root, _dirs, files in os.walk(ap):
                for f in files:
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, base).replace("\\", "/") if f != full else f
                    if rel not in existing:
                        z.write(full, rel); n += 1
    print(f"zipadd: +{n} files -> {archive}")

if __name__ == "__main__":
    main(sys.argv)
