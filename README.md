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
python3 envdrift.py .env --json            # key names only, never values
python3 envdrift.py .env --suggest         # prints `KEY=` lines for the missing keys
# or: pip install git+https://github.com/TPOALOS/envdrift && envdrift .env
```

Example output:

```
DRIFT .env
  missing     SMTP_HOST
  extra       OLD_FEATURE_FLAG
  empty       API_KEY
  unchanged   SECRET_KEY
OK    .env.production
```

| Option | Meaning |
|--------|---------|
| `-e, --example FILE` | reference file (default `.env.example`) |
| `--strict` | also fail on extra, empty, duplicate, unchanged and placeholder keys (default: only missing keys fail) |
| `--json` | machine-readable output (key names only) |
| `--suggest` | print `KEY=` lines for the missing keys, ready to append (never any values, never the example's values) |
| `-i, --ignore GLOB` | ignore matching keys (repeatable) |

"Empty" means the key is empty in your file while the example gives a non-empty default.

Two checks target secrets that were never really set (key names containing `secret`, `token`, `password`, `api_key`, `salt`, `private`, ...):
`unchanged` means the value is identical to the example's (a copied dev secret), `placeholder` means it is an obvious stand-in such as
`changeme`, `password`, `1234`, `<token>` or `your-api-key`. Only the key name is ever printed.

Exit codes: `0` in sync, `1` drift, `2` unreadable file. Use it in CI or a pre-commit hook:

```bash
python3 envdrift.py .env.ci --strict
```

Parsing covers `KEY=value`, `export KEY=value`, quoted values (including quoted values that span several lines, such as PEM keys),
and inline ` # comments`. It is not a full dotenv implementation (no variable interpolation).

## Tests

```bash
python3 -m unittest -v
```

## License

MIT (c) TPOALOS
