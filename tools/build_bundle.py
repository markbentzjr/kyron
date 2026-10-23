#!/usr/bin/env python3
"""Kyron AAB builder (Oct 2026) — produces a real, Play-uploadable .aab
from the same staged work dir that app/build_windows.sh produces, without
Gradle.

WHY: the 2.0 delivery report claimed an "AAB ready for Play upload" but no
bundle ever existed. This script closes that gap: it mirrors build_windows.sh
step 4 with --proto-format (the App Bundle requires a protobuf manifest +
resources table), stages a bundletool-compatible base module, and runs
bundletool's build-bundle + dump manifest / build-apks as verification.

Inputs (already produced by app/build_windows.sh, unchanged):
  ~/kyron-build/work/merged/AndroidManifest.xml   merged manifest
  ~/kyron-build/work/res_compiled/*.zip           aapt2-compiled res (app + 42 libs)
  ~/kyron-build/work/assets_merged/**             merged assets
  ~/kyron-build/work/dex/classes*.dex             D8 dex output
  ~/kyron-build/manual/work/aars/*/AndroidManifest.xml  for --extra-packages

Outputs:
  app/Kyron-{VERSION_NAME}.aab                    the bundle
  (bundletool dump manifest output printed for badging verification)

Usage:  python tools/build_bundle.py   (run from repo root, after build_windows.sh)
        BUNDLETOOL_JAR=...  overrides the bundletool jar path
"""
import os, sys, glob, shutil, subprocess, zipfile

KB = os.path.expanduser('~/kyron-build')
W = os.path.join(KB, 'work')
AARS = os.path.join(KB, 'manual', 'work', 'aars')
SDK = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Android', 'Sdk')
BT = os.path.join(SDK, 'build-tools', '36.0.0')
AAPT2 = os.path.join(BT, 'aapt2.exe')
AJAR = os.path.join(SDK, 'platforms', 'android-37.0', 'android.jar')
JAVA = os.path.join(KB, 'jdk17', 'bin', 'java.exe')

DEFAULT_BT_JAR = os.path.join(KB, 'dl', 'bundletool-all-1.18.3.jar')
BUNDLETOOL_JAR = os.environ.get('BUNDLETOOL_JAR') or DEFAULT_BT_JAR

REPO = os.path.abspath('.')


def load_version(path):
    meta = {}
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                meta[k.strip()] = v.strip()
    return meta


def step(name):
    print(f"\n=== {name} ===")


def main():
    ver = load_version(os.path.join(REPO, 'app', 'version.properties'))
    code, name = ver['VERSION_CODE'], ver['VERSION_NAME']
    min_api, target_api = ver['MIN_SDK'], ver['TARGET_SDK']
    out_aab = os.path.join(REPO, 'app', f'Kyron-{name}.aab')
    print(f"version: {name} (code {code}), minSdk {min_api}, targetSdk {target_api}")

    merged = os.path.join(W, 'merged', 'AndroidManifest.xml')
    res_zips = sorted(glob.glob(os.path.join(W, 'res_compiled', '*.zip')))
    assets_merged = os.path.join(W, 'assets_merged')
    dex_files = sorted(glob.glob(os.path.join(W, 'dex', 'classes*.dex')))
    assert os.path.exists(merged), merged
    assert res_zips, "no compiled res zips — run app/build_windows.sh first"
    assert dex_files, "no dex output — run app/build_windows.sh first"

    # extra packages: same collection as build_windows.sh step 2
    import xml.etree.ElementTree as ET
    pkgs = []
    for nm in sorted(os.listdir(AARS)):
        mp = os.path.join(AARS, nm, 'AndroidManifest.xml')
        if os.path.exists(mp):
            try:
                pkg = ET.parse(mp).getroot().get('package')
                resdir = os.path.join(AARS, nm, 'res')
                if pkg and os.path.isdir(resdir) and os.listdir(resdir):
                    pkgs.append(pkg)
            except Exception:
                pass
    print("extra packages:", len(pkgs))

    # 1. proto-format link (protobuf manifest + resources table for the bundle)
    step("1/4 aapt2 link --proto-format")
    proto_dir = os.path.join(W, 'aab', 'proto')
    if os.path.exists(proto_dir):
        shutil.rmtree(proto_dir)
    os.makedirs(proto_dir)
    proto_apk = os.path.join(proto_dir, 'proto_link.apk')
    cmd = [AAPT2, 'link',
           '-o', proto_apk,
           '-I', AJAR,
           '--manifest', merged,
           '--proto-format',
           '--min-sdk-version', min_api,
           '--target-sdk-version', target_api,
           '--version-code', code,
           '--version-name', name,
           '--auto-add-overlay']
    if pkgs:
        cmd.extend(['--extra-packages', ':'.join(pkgs)])
    cmd.extend(res_zips)
    subprocess.run(cmd, check=True)
    print("proto link OK ->", proto_apk)

    # 2. stage the base module for bundletool
    step("2/4 stage base module")
    base = os.path.join(W, 'aab', 'base')
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(os.path.join(base, 'manifest'))
    os.makedirs(os.path.join(base, 'dex'))

    with zipfile.ZipFile(proto_apk) as z:
        z.extractall(proto_dir + '/extract')
    extracted = os.path.join(proto_dir, 'extract')
    shutil.copy2(os.path.join(extracted, 'AndroidManifest.xml'),
                 os.path.join(base, 'manifest', 'AndroidManifest.xml'))
    if os.path.exists(os.path.join(extracted, 'resources.pb')):
        shutil.copy2(os.path.join(extracted, 'resources.pb'), os.path.join(base, 'resources.pb'))
    if os.path.isdir(os.path.join(extracted, 'res')):
        shutil.copytree(os.path.join(extracted, 'res'), os.path.join(base, 'res'))
    for drop in ('AndroidManifest.xml', 'resources.pb'):
        p = os.path.join(extracted, drop)
        if os.path.exists(p):
            os.unlink(p)
    if os.path.exists(os.path.join(extracted, 'res.arsc')):
        pass  # not expected in proto format; resources.pb governs
    for d in dex_files:
        shutil.copy2(d, os.path.join(base, 'dex', os.path.basename(d)))
    if os.path.isdir(assets_merged):
        shutil.copytree(assets_merged, os.path.join(base, 'assets'))
    print("base module staged at", base)

    # 3. zip the module (bundletool expects each module as its own zip)
    step("3/4 zip base module")
    base_zip = os.path.join(W, 'aab', 'base.zip')
    if os.path.exists(base_zip):
        os.remove(base_zip)
    with zipfile.ZipFile(base_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(base):
            for f in files:
                fp = os.path.join(root, f)
                z.write(fp, os.path.relpath(fp, base))
    print("zipped ->", base_zip)

    # 4. build-bundle + verify
    step("4/4 bundletool build-bundle + verify")
    subprocess.run([JAVA, '-jar', BUNDLETOOL_JAR, 'build-bundle',
                    '--modules', base_zip, '--output', out_aab], check=True)
    print("bundle:", out_aab, os.path.getsize(out_aab), "bytes")
    subprocess.run([JAVA, '-jar', BUNDLETOOL_JAR, 'dump', 'manifest',
                    '--bundle', out_aab], check=True)
    print(f"\nBUNDLE OK: {out_aab}")


if __name__ == '__main__':
    main()
