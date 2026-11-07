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


if __name__ == "__main__":
    unittest.main()
