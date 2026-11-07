#!/usr/bin/env python3
"""envdrift - detect drift between .env.example and your real .env files.

Reports keys that are missing, undocumented (extra), empty, or duplicated.
Values are never printed, so the output is safe to paste into CI logs.
Standard library only. Exit code 0 = in sync, 1 = drift, 2 = error.
"""
import argparse
import fnmatch
import re
import sys

__version__ = "1.0.0"

LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*(.*)$")


def parse_env(text):
    """Return (values, duplicates): dict key->value and sorted list of repeated keys."""
    values, seen, dups = {}, set(), set()
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = LINE.match(raw)
        if not m:
            continue
        key, rest = m.group(1), m.group(2).strip()
        if rest[:1] in ("'", '"'):
            end = rest.find(rest[0], 1)
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
    }


def read(path):
    with open(path, errors="replace") as fh:
        return parse_env(fh.read())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect .env / .env.example drift (values never printed).")
    ap.add_argument("targets", nargs="*", default=[".env"], help="env files to check (default: .env)")
    ap.add_argument("-e", "--example", default=".env.example", help="reference file")
    ap.add_argument("--strict", action="store_true",
                    help="also fail on extra, empty and duplicate keys (default: only missing)")
    ap.add_argument("-i", "--ignore", action="append", default=[],
                    help="glob of keys to ignore (repeatable)")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    try:
        example, _ = read(args.example)
    except OSError as exc:
        print("envdrift: cannot read example file: %s" % exc, file=sys.stderr)
        return 2
    failed = False
    for path in args.targets:
        try:
            target, dups = read(path)
        except OSError as exc:
            print("envdrift: cannot read %s: %s" % (path, exc), file=sys.stderr)
            return 2
        d = compare(example, target, args.ignore)
        d["duplicate"] = [k for k in dups if not any(fnmatch.fnmatch(k, p) for p in args.ignore)]
        problems = d["missing"] + (d["extra"] + d["empty"] + d["duplicate"] if args.strict else [])
        print("%s %s" % ("DRIFT" if problems else "OK   ", path))
        for label in ("missing", "extra", "empty", "duplicate"):
            for key in d[label]:
                print("  %-9s %s" % (label, key))
        failed = failed or bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
