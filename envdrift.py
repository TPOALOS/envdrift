#!/usr/bin/env python3
"""envdrift - detect drift between .env.example and your real .env files.

Reports keys that are missing, undocumented (extra), empty, or duplicated.
Values are never printed, so the output is safe to paste into CI logs.
Standard library only. Exit code 0 = in sync, 1 = drift, 2 = error.
"""
import argparse
import fnmatch
import json
import re
import sys

__version__ = "1.1.0"

LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*)$")
SECRETISH = re.compile(r"(?i)(secret|token|passw|pwd|api[_-]?key|private|credential|salt|signing|encryption)")
PLACEHOLDER = re.compile(r"(?i)^(changeme|change[-_ ]?me|password|passw0rd|secret|todo|tbd|xxx+|\*+|1234+|12345678|test|dummy|"
                         r"example|your[-_ ].*|<.*>|replace[-_ ]?me|insert[-_ ].*|default)$")


def parse_env(text):
    """Return (values, duplicates): dict key->value and sorted list of repeated keys.

    Quoted values may span several lines (PEM blocks, JSON); they are read as one value.
    """
    values, seen, dups = {}, set(), set()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = LINE.match(raw)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest[:1] in ("'", '"'):
            quote = rest[0]
            end = rest.find(quote, 1)
            while end == -1 and i < len(lines):  # the closing quote is on a later line
                rest += "\n" + lines[i]
                i += 1
                end = rest.find(quote, 1)
            value = rest[1:end] if end != -1 else rest[1:]
        else:
            value = re.split(r"\s+#", rest, maxsplit=1)[0].strip()
        if key in seen:
            dups.add(key)
        seen.add(key)
        values[key] = value
    return values, sorted(dups)


def compare(example, target, ignore=()):
    """Compare two parsed envs (dicts). Returns dict of sorted key lists."""
    def keep(k):
        return not any(fnmatch.fnmatch(k, pat) for pat in ignore)
    ex = {k for k in example if keep(k)}
    tg = {k for k in target if keep(k)}
    return {
        "missing": sorted(ex - tg),
        "extra": sorted(tg - ex),
        "empty": sorted(k for k in ex & tg if target[k] == "" and example[k] != ""),
        # secret-looking keys still holding the example's value, or an obvious placeholder
        "unchanged": sorted(k for k in ex & tg if SECRETISH.search(k) and target[k] != "" and target[k] == example[k]),
        "placeholder": sorted(k for k in tg if SECRETISH.search(k) and PLACEHOLDER.match(target[k]) and target[k] != example.get(k)),
    }


def read(path):
    with open(path, errors="replace") as fh:
        return parse_env(fh.read())


LABELS = ("missing", "extra", "empty", "duplicate", "unchanged", "placeholder")
STRICT_ONLY = ("extra", "empty", "duplicate", "unchanged", "placeholder")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect .env / .env.example drift (values never printed).")
    ap.add_argument("targets", nargs="*", default=[".env"], help="env files to check (default: .env)")
    ap.add_argument("-e", "--example", default=".env.example", help="reference file")
    ap.add_argument("--strict", action="store_true",
                    help="also fail on extra, empty, duplicate, unchanged-secret and placeholder keys (default: only missing)")
    ap.add_argument("-i", "--ignore", action="append", default=[],
                    help="glob of keys to ignore (repeatable)")
    ap.add_argument("--json", action="store_true", help="machine-readable output (key names only)")
    ap.add_argument("--suggest", action="store_true",
                    help="print `KEY=` lines for the missing keys, ready to append (never any values)")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    try:
        example, _ = read(args.example)
    except OSError as exc:
        print("envdrift: cannot read example file: %s" % exc, file=sys.stderr)
        return 2
    failed, report = False, []
    for path in args.targets:
        try:
            target, dups = read(path)
        except OSError as exc:
            print("envdrift: cannot read %s: %s" % (path, exc), file=sys.stderr)
            return 2
        d = compare(example, target, args.ignore)
        d["duplicate"] = [k for k in dups if not any(fnmatch.fnmatch(k, p) for p in args.ignore)]
        problems = d["missing"] + [k for label in STRICT_ONLY for k in d[label]] if args.strict else d["missing"]
        report.append({"file": path, "ok": not problems, **{label: d[label] for label in LABELS}})
        failed = failed or bool(problems)
        if args.json:
            continue
        print("%s %s" % ("DRIFT" if problems else "OK   ", path))
        for label in LABELS:
            for key in d[label]:
                print("  %-11s %s" % (label, key))
        if args.suggest and d["missing"]:
            print("  # append to %s:" % path)
            for key in d["missing"]:
                print("  %s=" % key)
    if args.json:
        print(json.dumps(report, indent=2))
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
