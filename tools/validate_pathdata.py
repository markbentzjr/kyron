#!/usr/bin/env python3
"""Strict Android vector pathData validator (Kyron build gate).

WHY THIS EXISTS: android.util.PathParser parses pathData at RUNTIME, during
layout inflation. aapt2 checks only XML well-formedness -- it never validates
pathData arity. A hand-authored icon with a corrupt path (e.g. an S command
handed 10 floats instead of a multiple of 4) compiles, links, dexes and
passes every static audit, then kills the app on a real device the first
time the drawable is inflated (Kyron FIX2 device crash, Oct 14 2026:
activity_main line 62 -> ic_search -> IllegalArgumentException
"S needs to be followed by a multiple of 4 floats. However, 10 float(s)
are found"). Robolectric never runs the native PathParser, so the JVM
rig cannot catch it either. This validator is the gate.

WHAT IT CHECKS (mirrors android.util.PathParser grammar):
  * Tokenization: command letters [MmLlHhVvCcSsQqTtAaZz]; numbers incl.
    sign-as-separator, leading-dot fractions and exponents; separators
    are whitespace/commas. Any other byte is an unparseable segment.
  * Per-command arity: M/L/T consume pairs (2), H/V consume 1, C consumes
    6, S/Q consume 4, A consumes 7, Z consumes 0. After a command letter,
    the run of numbers that follows must be non-empty (except Z) and its
    count must be an EXACT multiple of the command's arity (implicit
    group repetition). M's implicit groups are lineto -- same arity.
  * Arc flags: within each A group of 7, parameters 4 and 5
    (large-arc-flag, sweep-flag) must each be exactly 0 or 1.
  * The path must begin with a moveto (M/m) and must not be empty.

USAGE:
  validate_pathdata.py <file-or-dir> [more paths...]
  Scans every *.xml under the given paths for android:pathData
  attributes and validates each one.
EXIT: 0 = all paths valid; 1 = at least one malformed path (each is
printed with file, path index, command and the offending segment).
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
COMMANDS = set("MmLlHhVvCcSsQqTtAaZz")
ARITY = {
    "M": 2, "L": 2, "T": 2,
    "H": 1, "V": 1,
    "C": 6,
    "S": 4, "Q": 4,
    "A": 7,
    "Z": 0,
}
NUMBER_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
SEPARATORS = set(" \t\r\n,")


class PathError(Exception):
    pass


def tokenize(data):
    """Split pathData into ('cmd', letter) / ('num', float, raw) tokens."""
    tokens = []
    i, n = 0, len(data)
    while i < n:
        ch = data[i]
        if ch in SEPARATORS:
            i += 1
            continue
        if ch in COMMANDS:
            tokens.append(("cmd", ch, ch))
            i += 1
            continue
        m = NUMBER_RE.match(data, i)
        if m:
            raw = m.group(0)
            tokens.append(("num", float(raw), raw))
            i = m.end()
            continue
        raise PathError(
            f"unparseable character {ch!r} at offset {i} in segment "
            f"{data[max(0, i - 12):i + 12]!r}"
        )
    return tokens


def validate_pathdata(data):
    """Raise PathError with a precise message if pathData is malformed."""
    if data is None or not data.strip():
        raise PathError("empty pathData")
    tokens = tokenize(data)
    if not tokens or tokens[0][0] != "cmd" or tokens[0][1] not in "Mm":
        raise PathError("path does not begin with a moveto (M/m) command")

    # Group numbers under their governing command.
    groups = []  # (cmd_letter, [floats], [raws])
    cur_cmd, cur_nums, cur_raws = None, [], []
    for kind, val, raw in tokens:
        if kind == "cmd":
            if cur_cmd is not None:
                groups.append((cur_cmd, cur_nums, cur_raws))
            cur_cmd, cur_nums, cur_raws = val, [], []
        else:
            cur_nums.append(val)
            cur_raws.append(raw)
    if cur_cmd is not None:
        groups.append((cur_cmd, cur_nums, cur_raws))

    for cmd, nums, raws in groups:
        arity = ARITY[cmd.upper()]
        if arity == 0:  # Z/z takes no parameters
            if nums:
                raise PathError(
                    f"{cmd} takes no parameters but {len(nums)} float(s) "
                    f"follow: {' '.join(raws)}"
                )
            continue
        if not nums:
            raise PathError(f"{cmd} command has no parameters")
        if len(nums) % arity != 0:
            raise PathError(
                f"{cmd} needs to be followed by a multiple of {arity} "
                f"floats. However, {len(nums)} float(s) are found: "
                f"{' '.join(raws)}"
            )
        if cmd.upper() == "A":
            for g in range(0, len(nums), 7):
                for flag_idx in (3, 4):
                    flag = nums[g + flag_idx]
                    if flag not in (0.0, 1.0):
                        raise PathError(
                            f"A group {g // 7}: flag parameter "
                            f"{flag_idx + 1} must be 0 or 1, got "
                            f"{raws[g + flag_idx]!r}"
                        )
    return len(groups)


def iter_pathdata(xml_path):
    """Yield (index, pathData-string) for every path in a drawable XML."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        raise PathError(f"XML parse error: {e}")
    idx = 0
    for elem in tree.getroot().iter():
        pd = elem.get(ANDROID_NS + "pathData")
        if pd is None:
            pd = elem.get("pathData")
        if pd is not None:
            idx += 1
            yield idx, pd


def collect_files(paths):
    files = []
    for p in paths:
        if os.path.isfile(p):
            files.append(p)
        elif os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                for name in sorted(names):
                    if name.endswith(".xml"):
                        files.append(os.path.join(root, name))
        else:
            print(f"WARN: no such path: {p}", file=sys.stderr)
    return sorted(files)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    files = collect_files(argv[1:])
    total_paths = 0
    bad = 0
    files_with_paths = 0
    for f in files:
        try:
            paths = list(iter_pathdata(f))
        except PathError as e:
            print(f"MALFORMED {f}: {e}")
            bad += 1
            continue
        if paths:
            files_with_paths += 1
        for idx, pd in paths:
            total_paths += 1
            try:
                validate_pathdata(pd)
            except PathError as e:
                bad += 1
                print(f"MALFORMED {f} [path #{idx}]: {e}")
    print(
        f"pathData validation: {files_with_paths} files, "
        f"{total_paths} path(s), {bad} malformed"
    )
    if bad:
        print("pathData validation FAILED", file=sys.stderr)
        return 1
    print("pathData validation OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
