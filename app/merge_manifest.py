#!/usr/bin/env python3
"""Merge AAR library manifests into the app manifest the way AGP would:
- root-level <permission>/<uses-permission> (dedup, ${applicationId} substituted)
- <application> children appended; the shared androidx.startup.InitializationProvider
  is merged into a single provider whose meta-data children are unioned."""
import os, sys, copy
import xml.etree.ElementTree as ET

ANDROID = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID)
APP_ID = "com.kyronapp.kyron"

def an(name):
    return f"{{{ANDROID}}}{name}"

def subst(value):
    if value is None:
        return None
    return value.replace("${applicationId}", APP_ID)

def fix_attrs(el):
    for k in list(el.attrib):
        el.set(k, subst(el.get(k)))
    for ch in el:
        fix_attrs(ch)

base_path, aars_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
tree = ET.parse(base_path)
root = tree.getroot()
app_el = root.find("application")

existing_perms = {p.get(an("name")) for p in root.findall("uses-permission")}
existing_root_perms = {p.get(an("name")) for p in root.findall("permission")}
startup_provider = None
merged_report = []

for name in sorted(os.listdir(aars_dir)):
    mpath = os.path.join(aars_dir, name, "AndroidManifest.xml")
    if not os.path.exists(mpath):
        continue
    try:
        lib = ET.parse(mpath).getroot()
    except Exception:
        continue
    for perm in lib.findall("permission"):
        fix_attrs(perm)
        if perm.get(an("name")) not in existing_root_perms:
            root.insert(list(root).index(app_el), perm)
            existing_root_perms.add(perm.get(an("name")))
            merged_report.append(f"{name}: <permission> {perm.get(an('name'))}")
    for up in lib.findall("uses-permission"):
        fix_attrs(up)
        if up.get(an("name")) not in existing_perms:
            root.insert(list(root).index(app_el), up)
            existing_perms.add(up.get(an("name")))
    lib_app = lib.find("application")
    if lib_app is None:
        continue
    for child in list(lib_app):
        fix_attrs(child)
        if child.tag == "provider" and child.get(an("name")) == "androidx.startup.InitializationProvider":
            if startup_provider is None:
                startup_provider = child
                app_el.append(child)
                merged_report.append(f"{name}: startup provider (base)")
            else:
                have = {(md.get(an("name"))) for md in startup_provider.findall("meta-data")}
                for md in child.findall("meta-data"):
                    if md.get(an("name")) not in have:
                        startup_provider.append(md)
                        merged_report.append(f"{name}: startup meta-data {md.get(an('name'))}")
            continue
        app_el.append(child)
        merged_report.append(f"{name}: <{child.tag}> {child.get(an('name'))}")

os.makedirs(os.path.dirname(out_path), exist_ok=True)
tree.write(out_path, encoding="utf-8", xml_declaration=True)
print(f"merged {len(merged_report)} entries")
for line in merged_report:
    print("  ", line)
