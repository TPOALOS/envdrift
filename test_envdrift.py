import contextlib
import io
import json
import os
import tempfile
import unittest

import envdrift

EXAMPLE = """# sample
DB_URL=postgres://localhost/app
API_KEY=
DEBUG=false
export PORT=3000
"""


class ParseTests(unittest.TestCase):
    def test_parse_basic(self):
        v, d = envdrift.parse_env(EXAMPLE)
        self.assertEqual(v, {"DB_URL": "postgres://localhost/app", "API_KEY": "",
                             "DEBUG": "false", "PORT": "3000"})
        self.assertEqual(d, [])

    def test_quotes_comments_and_spaces(self):
        v, _ = envdrift.parse_env('A = "hello world"  # c\nB=\'x y\'\nC=plain # trailing\n#D=1\n')
        self.assertEqual(v, {"A": "hello world", "B": "x y", "C": "plain"})

    def test_hash_inside_value_kept(self):
        v, _ = envdrift.parse_env("URL=http://x/#frag\n")
        self.assertEqual(v["URL"], "http://x/#frag")

    def test_duplicates(self):
        _, d = envdrift.parse_env("A=1\nB=2\nA=3\n")
        self.assertEqual(d, ["A"])

    def test_garbage_lines_skipped(self):
        v, _ = envdrift.parse_env("not a pair\n=novalue\nOK=1\n")
        self.assertEqual(v, {"OK": "1"})


class CompareTests(unittest.TestCase):
    def test_compare(self):
        ex, _ = envdrift.parse_env(EXAMPLE)
        tg, _ = envdrift.parse_env("DB_URL=\nAPI_KEY=\nEXTRA=1\nDEBUG=true\n")
        d = envdrift.compare(ex, tg)
        self.assertEqual(d["missing"], ["PORT"])
        self.assertEqual(d["extra"], ["EXTRA"])
        self.assertEqual(d["empty"], ["DB_URL"])  # API_KEY empty in example too

    def test_ignore(self):
        d = envdrift.compare({"A": "1", "SECRET_X": "1"}, {}, ignore=["SECRET_*"])
        self.assertEqual(d["missing"], ["A"])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.example = self.write(".env.example", EXAMPLE)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = os.path.join(self.dir, name)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    def test_in_sync(self):
        env = self.write(".env", "DB_URL=x\nAPI_KEY=k\nDEBUG=1\nPORT=1\nEXTRA=1\n")
        self.assertEqual(envdrift.main(["-e", self.example, env]), 0)

    def test_missing_fails(self):
        env = self.write(".env", "DB_URL=x\n")
        self.assertEqual(envdrift.main(["-e", self.example, env]), 1)

    def test_strict_extra(self):
        env = self.write(".env", "DB_URL=x\nAPI_KEY=k\nDEBUG=1\nPORT=1\nEXTRA=1\n")
        self.assertEqual(envdrift.main(["-e", self.example, env, "--strict"]), 1)

    def test_values_never_printed(self):
        import io
        from unittest import mock
        env = self.write(".env", "DB_URL=supersecretvalue123\nEXTRA=anothersecret456\n")
        buf = io.StringIO()
        with mock.patch("sys.stdout", buf):
            envdrift.main(["-e", self.example, env, "--strict"])
        self.assertNotIn("supersecretvalue123", buf.getvalue())
        self.assertNotIn("anothersecret456", buf.getvalue())
        self.assertIn("EXTRA", buf.getvalue())

    def test_missing_files(self):
        self.assertEqual(envdrift.main(["-e", "/nonexistent/.env.example"]), 2)
        self.assertEqual(envdrift.main(["-e", self.example, "/nonexistent/.env"]), 2)


class MultilineTests(unittest.TestCase):
    PEM = 'KEY="-----BEGIN X-----\nAAA=BBB\nCCC=DDD\n-----END X-----"\nAFTER=1\n'

    def test_quoted_multiline_value_is_one_key(self):
        v, d = envdrift.parse_env(self.PEM)
        self.assertEqual(set(v), {"KEY", "AFTER"})
        self.assertEqual(v["KEY"], "-----BEGIN X-----\nAAA=BBB\nCCC=DDD\n-----END X-----")
        self.assertEqual((v["AFTER"], d), ("1", []))

    def test_lines_inside_a_value_are_not_phantom_keys(self):
        v, _ = envdrift.parse_env('JSON={\n"a": 1\n}\nPLAIN=x\n')
        self.assertEqual(set(v), {"JSON", "PLAIN"})  # unquoted JSON is not multi-line: only first line counts
        v, _ = envdrift.parse_env("J='{\nFOO=1\n}'\nPLAIN=x\n")
        self.assertEqual(set(v), {"J", "PLAIN"})

    def test_unterminated_quote_swallows_the_rest_but_does_not_crash(self):
        v, _ = envdrift.parse_env('A="never closed\nB=2\n')
        self.assertEqual(set(v), {"A"})

    def test_single_line_quotes_unchanged(self):
        v, _ = envdrift.parse_env('A="x y"\nB=\'z\'\n')
        self.assertEqual(v, {"A": "x y", "B": "z"})

    def test_duplicate_detection_with_multiline(self):
        _, d = envdrift.parse_env('A="1\n2"\nA=3\n')
        self.assertEqual(d, ["A"])


class SecretHygieneTests(unittest.TestCase):
    EX = {"SECRET_KEY": "dev-secret", "API_TOKEN": "", "DEBUG": "true", "DB_PASSWORD": "changeme"}

    def test_unchanged_secret(self):
        d = envdrift.compare(self.EX, {"SECRET_KEY": "dev-secret", "API_TOKEN": "", "DEBUG": "true", "DB_PASSWORD": "real-one"})
        self.assertEqual(d["unchanged"], ["SECRET_KEY"])  # DEBUG is not secret-looking; empty values never count

    def test_placeholder_values(self):
        target = {"SECRET_KEY": "x", "API_TOKEN": "<your-token>", "DB_PASSWORD": "changeme", "DEBUG": "changeme"}
        d = envdrift.compare(self.EX, target)
        self.assertEqual(d["placeholder"], ["API_TOKEN"])      # DB_PASSWORD equals the example: reported as unchanged instead
        self.assertEqual(d["unchanged"], ["DB_PASSWORD"])

    def test_real_looking_values_are_fine(self):
        d = envdrift.compare(self.EX, {k: "qk3J9zLw0pX2vB7n" for k in self.EX})
        self.assertEqual((d["unchanged"], d["placeholder"]), ([], []))

    def test_ignore_applies(self):
        d = envdrift.compare(self.EX, dict(self.EX), ignore=["SECRET_*"])
        self.assertNotIn("SECRET_KEY", d["unchanged"])

    def test_placeholder_patterns(self):
        for v in ("changeme", "CHANGE_ME", "password", "xxxx", "1234", "<token>", "your-api-key", "TODO", "replace_me"):
            self.assertTrue(envdrift.PLACEHOLDER.match(v), v)
        for v in ("qk3J9zLw0pX2vB7n", "passwordless-sso-9f2", "s3cr3t-value-77"):
            self.assertFalse(envdrift.PLACEHOLDER.match(v), v)


def run_main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = envdrift.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class NewCliTests(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = self._t.name
        self.example = self.path(".env.example", "SECRET_KEY=dev-secret\nDB_URL=postgres://localhost/app\nDEBUG=false\n")

    def tearDown(self):
        self._t.cleanup()

    def path(self, name, text):
        p = os.path.join(self.d, name)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    def test_json_never_contains_values(self):
        env = self.path(".env", "SECRET_KEY=dev-secret\nEXTRA=hunter2hunter2\n")
        code, out, _ = run_main(env, "-e", self.example, "--json", "--strict")
        data = json.loads(out)[0]
        self.assertEqual(code, 1)
        self.assertEqual((data["missing"], data["extra"], data["unchanged"]), (["DB_URL", "DEBUG"], ["EXTRA"], ["SECRET_KEY"]))
        self.assertNotIn("hunter2", out)
        self.assertNotIn("dev-secret", out)
        self.assertFalse(data["ok"])

    def test_default_run_fails_only_on_missing(self):
        env = self.path(".env", "SECRET_KEY=dev-secret\nDB_URL=x\nDEBUG=true\nEXTRA=1\n")
        code, out, _ = run_main(env, "-e", self.example)
        self.assertEqual(code, 0)
        self.assertIn("unchanged", out)          # reported ...
        self.assertTrue(out.startswith("OK"))    # ... but not failing without --strict
        self.assertEqual(run_main(env, "-e", self.example, "--strict")[0], 1)

    def test_suggest_prints_empty_assignments_only(self):
        env = self.path(".env", "SECRET_KEY=abc\n")
        _, out, _ = run_main(env, "-e", self.example, "--suggest")
        self.assertIn("  DB_URL=\n", out)
        self.assertIn("  DEBUG=\n", out)
        self.assertNotIn("postgres", out)       # example values are never copied
        self.assertNotIn("false", out)

    def test_suggest_prints_nothing_when_in_sync(self):
        env = self.path(".env", "SECRET_KEY=abc\nDB_URL=1\nDEBUG=1\n")
        self.assertNotIn("append to", run_main(env, "-e", self.example, "--suggest")[1])

    def test_several_targets_json(self):
        a = self.path("a.env", "SECRET_KEY=a\nDB_URL=1\nDEBUG=1\n")
        b = self.path("b.env", "SECRET_KEY=a\n")
        code, out, _ = run_main(a, b, "-e", self.example, "--json")
        data = json.loads(out)
        self.assertEqual((code, [d["ok"] for d in data]), (1, [True, False]))

    def test_missing_files(self):
        self.assertEqual(run_main("/nonexistent/.env", "-e", self.example)[0], 2)
        self.assertEqual(run_main(self.path(".env", ""), "-e", "/nonexistent/.env.example")[0], 2)

    def test_placeholder_reported_in_text(self):
        env = self.path(".env", "SECRET_KEY=changeme\nDB_URL=1\nDEBUG=1\n")
        _, out, _ = run_main(env, "-e", self.example)
        self.assertIn("placeholder", out)
        self.assertNotIn("changeme", out)


if __name__ == "__main__":
    unittest.main()
