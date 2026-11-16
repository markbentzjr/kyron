#!/usr/bin/env python3
"""Extract hardcoded android:text/hint/contentDescription/textOff/textOn
literals from res/layout/*.xml into res/values/strings.xml.

One-shot migration tool — literal -> resource-name mapping is explicit so
names stay semantic. Idempotent: re-running leaves @string refs alone.
"""
import html
import os
import re
import sys

RES = "app/src/main/res"
LAYOUTS = os.path.join(RES, "layout")
STRINGS = os.path.join(RES, "values", "strings.xml")

# attr -> (string name, literal) pairs; literal is the XML-decoded text
MAP = {
    # ---- shared actions
    "action_watch": "Watch",
    "action_directions": "Directions",
    "action_share": "Share",
    "action_cancel": "Cancel",
    "action_done": "Done",
    "action_clear_all": "Clear all",
    "action_use_location": "Use my location",
    "action_use_current_location": "Use my current location",
    "action_refresh": "Refresh",
    "action_sync_now": "Sync now",
    "action_save_profile": "Save profile",
    "action_export_backup": "Export backup",
    "action_import_backup": "Import backup",
    "action_browse_restaurants": "Browse restaurants",
    "action_got_it": "Got it",
    "action_clear_filters": "Clear search and filters",
    "action_choose_counties": "Choose counties",
    "action_select_all_counties": "Select all counties",
    "action_edit_area_alerts": "Edit area alerts",
    "action_remove_rule": "Remove this rule",
    "action_full_details": "Full details",
    "action_load_full_details": "Load full inspection details",
    # ---- main / browse
    "region_chip_default": "Alabama",
    "browse_guide": "Find a place, then tap its star to watch it. Kyron alerts you when a watched place gets a new inspection — set up area alerts in the Alerts tab below.",
    "hint_search_places": "Search restaurants, cities, ZIP codes",
    "filter_all_scores": "All scores",
    "filter_below_85": "Below 85",
    "filter_85_94": "85\u201394",
    "filter_95_plus": "95+",
    "label_county": "County",
    "label_sort_by": "Sort by",
    "loading_places": "Loading restaurants\u2026",
    "empty_no_places": "No places match. Try a different search or county.",
    # ---- favorites
    "fav_empty": "No favorites yet.\n\nTap the star on any place and Kyron will watch it for you — when it gets a new inspection, you'll get an alert here.",
    # ---- map
    "map_attribution": "\u00a9 OpenStreetMap contributors",
    # ---- detail
    "detail_title": "Restaurant details",
    "detail_history_title": "Inspection history",
    "detail_violations_title": "What the inspector found",
    "detail_scores_note": "Scores are public health-department records, shown as published. Alabama requires reinspection within 60 days for scores below 85.",
    # ---- coverage
    "coverage_title": "Coverage & states",
    "coverage_explainer": "Kyron covers states one region pack at a time, from each health department's own published data. A state listed as \u201cNot covered yet\u201d has no pack — Kyron won't pretend otherwise.",
    "hint_search_states": "Search states",
    # ---- county picker
    "picker_title": "Choose counties to watch",
    "picker_hint": "Type to filter counties",
    # ---- alerts
    "alerts_inbox_title": "Alert inbox",
    "alerts_inbox_empty": "No alerts yet. When a place you watch gets a new inspection — or a score drops below your threshold in a county you watch — it lands here and as a notification. Set up your rules below.",
    "alerts_favorites_title": "Alerts for my favorites",
    "alerts_favorites_desc": "Alert me when a place I watch gets a new score or inspection result — favorites always alert, on any new result. Tap the star on any restaurant to watch it. (The score threshold in the area rule below applies to area alerts.)",
    "cd_alert_favorites": "Alert me about my favorites",
    "cd_area_alerts": "Area alerts",
    "alerts_areas_title": "Alerts for my areas",
    "alerts_off": "Off",
    "cd_alert_areas": "Alert me about bad scores in my areas",
    "alerts_counties_label": "Counties I watch",
    "alerts_area_center_label": "My area center",
    "alerts_area_note": "County score checks run against Alabama's state and county health departments. Watched places in other states alert on their new results through your favorites.",
    "cd_data_sync": "Data sync",
    "alerts_sync_title": "Data sync",
    "alerts_sync_note": "Kyron also checks for new inspections automatically about every 12 hours in the background.",
    "cd_profile": "My profile",
    "alerts_profile_title": "My profile (on this device)",
    "alerts_name_label": "Your name",
    "alerts_profile_note": "No sign-up needed — Kyron works fully without an account. Your profile, favorites and alert rules stay on this device only; nothing is uploaded. They ride along in your phone's own Android backup when that's enabled, and you can export them yourself below.",
    "cd_data_sources": "Data sources",
    "alerts_sources_title": "Data sources",
    "alerts_sources_note": "America has no single restaurant-inspection database — every state and county publishes its own. Kyron is built with one adapter per source, so new states plug into this list without changing the app.",
    "cd_backup": "Backup and restore",
    "alerts_backup_title": "My data — backup & restore",
    "alerts_backup_desc": "Your favorites, alert rules and inbox live only on this device (and in your phone's own Android backup when that's on). Export a backup file any time — it contains only your Kyron data, and importing it on another phone restores everything.",
}

ATTRS = ["android:text", "android:hint", "android:contentDescription",
         "android:textOff", "android:textOn"]

def xml_decode(s):
    return html.unescape(s)

def xml_encode(s):
    # encode literal for storage inside <string>...</string>
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "\\'"))


def main():
    # build literal -> name (XML-attr value form -> name)
    lit2name = {}
    for name, lit in MAP.items():
        lit2name[lit] = name
        # also match the &-escaped form that appears in layout source
        esc = html.escape(lit).replace("'", "&apos;")
        if esc != lit:
            lit2name[esc] = name
        esc2 = lit.replace("&", "&amp;")
        if esc2 != lit:
            lit2name[esc2] = name

    changed = {}
    for fname in sorted(os.listdir(LAYOUTS)):
        if not fname.endswith(".xml"):
            continue
        path = os.path.join(LAYOUTS, fname)
        src = open(path, encoding="utf-8").read()
        orig = src
        for attr in ATTRS:
            # match attr="literal" where literal is not already @string/
            for m in re.finditer(re.escape(attr) + r'="([^"]*)"', src):
                lit = m.group(1)
                if lit.startswith("@") or lit == "":
                    continue
                decoded = xml_decode(lit)
                name = lit2name.get(decoded) or lit2name.get(lit)
                if not name:
                    print(f"  [unmapped] {fname}: {attr}={lit!r}")
                    continue
                src = src.replace(f'{attr}="{lit}"',
                                  f'{attr}="@string/{name}"')
        if src != orig:
            open(path, "w", encoding="utf-8").write(src)
            changed[fname] = True

    # append new entries to strings.xml (skip names already present)
    sx = open(STRINGS, encoding="utf-8").read()
    existing = set(re.findall(r'<string name="([^"]+)"', sx))
    entries = []
    for name, lit in MAP.items():
        if name in existing:
            continue
        entries.append(f'    <string name="{name}">{xml_encode(lit)}</string>')
    if entries:
        sx = sx.replace("</resources>", "\n".join(entries) + "\n</resources>")
        open(STRINGS, "w", encoding="utf-8").write(sx)

    print(f"updated layouts: {sorted(changed)}")
    print(f"strings.xml: +{len(entries)} entries")


if __name__ == "__main__":
    main()
