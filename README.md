# envdrift

Detect drift between `.env.example` and your real `.env` files. It reports keys that
are **missing**, **extra** (undocumented), **empty**, or **duplicated**.

**Values are never printed**, so the output is safe in CI logs and bug reports.
One file, standard library only.

## Usage

```bash
python3 envdrift.py                          # compare .env against .env.example
python3 envdrift.py .env .env.production     # several targets
python3 envdrift.py -e config/sample.env --strict -i "AWS_*"
```

Example output:

```
DRIFT .env
  missing   SMTP_HOST
  extra     OLD_FEATURE_FLAG
  empty     API_KEY
OK    .env.production
```

| Option | Meaning |
|--------|---------|
| `-e, --example FILE` | reference file (default `.env.example`) |
| `--strict` | also fail on extra, empty and duplicate keys (default: only missing keys fail) |
| `-i, --ignore GLOB` | ignore matching keys (repeatable) |

"Empty" means the key is empty in your file while the example gives a non-empty default.

Exit codes: `0` in sync, `1` drift, `2` unreadable file. Use it in CI or a pre-commit hook:

```bash
python3 envdrift.py .env.ci --strict
```

Parsing covers `KEY=value`, `export KEY=value`, quoted values, and inline ` # comments`.
It is not a full dotenv implementation (no variable interpolation, no multi-line values).

## Tests

```bash
python3 -m unittest -v
```

## License

MIT (c) TPOALOS
