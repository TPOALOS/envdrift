# Changelog

## 1.1.0

- Multi-line quoted values (PEM keys, JSON) are read as one value instead of creating phantom keys
- New `unchanged` (secret-looking key still equal to the example) and `placeholder` (changeme, <token>, ...) findings, reported always and failing with `--strict`
- `--json` output and `--suggest` (prints `KEY=` for missing keys, never values)
- Installable with pip (`envdrift` command), CI on Linux and macOS

## 1.0.0

Initial release.
