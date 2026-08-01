"""Test-Suite für die project-memory-Hooks (nur Standardbibliothek).

Ausführen:  python -m unittest discover tests
Deckt die Kernlogik mit synthetischen Transcripts ab – insbesondere die
Fälle, die im echten Betrieb nur schwer beobachtbar sind (Fail-silent).
"""

import io
import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import context_guard as cg  # noqa: E402
import session_start as ss  # noqa: E402


def make_transcript(path, tokens=100_000, model="claude-test-1", ts="2026-08-01T10:00:00.000Z"):
    """Synthetisches Transcript: eine Kopfzeile mit timestamp, eine usage-Zeile."""
    lines = [
        json.dumps({"type": "queue-operation", "timestamp": ts}),
        json.dumps(
            {
                "type": "assistant",
                "isSidechain": False,
                "timestamp": ts,
                "message": {
                    "model": model,
                    "usage": {
                        "input_tokens": 2,
                        "cache_read_input_tokens": tokens - 2,
                        "cache_creation_input_tokens": 0,
                    },
                },
            }
        ),
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class TestResolveStages(unittest.TestCase):
    def test_default_bei_leer(self):
        self.assertEqual(cg.resolve_stages(None), (25.0, 60.0, 85.0))
        self.assertEqual(cg.resolve_stages(""), (25.0, 60.0, 85.0))

    def test_regulaer_und_sortierung(self):
        self.assertEqual(cg.resolve_stages("20,50,80"), (20.0, 50.0, 80.0))
        self.assertEqual(cg.resolve_stages("80,20,50"), (20.0, 50.0, 80.0))

    def test_unsinn_faellt_auf_defaults(self):
        for kaputt in ("20,50", "20,50,80,95", "20,20,80", "0,50,80", "20,50,120", "abc"):
            self.assertEqual(cg.resolve_stages(kaputt), (25.0, 60.0, 85.0), kaputt)


class TestResolveWindow(unittest.TestCase):
    def test_env_gilt(self):
        self.assertEqual(cg.resolve_window("1000000", 0, 50_000, "x"), (1_000_000, False))

    def test_beweis_schlaegt_alles(self):
        window, detected = cg.resolve_window("200000", 0, 432_000, "claude-x")
        self.assertEqual(window, 1_000_000)
        self.assertTrue(detected)

    def test_modell_id_hinweis(self):
        window, detected = cg.resolve_window(None, 0, 150_000, "claude-opus-5[1m]")
        self.assertEqual(window, 1_000_000)
        self.assertTrue(detected)

    def test_cache_ueberlebt(self):
        window, detected = cg.resolve_window(None, 1_000_000, 50_000, "claude-x")
        self.assertEqual(window, 1_000_000)
        self.assertFalse(detected)

    def test_kaputtes_env(self):
        self.assertEqual(cg.resolve_window("quatsch", 0, 50_000, "x")[0], 200_000)


class TestTranscriptLesen(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.tr = os.path.join(self.dir.name, "t.jsonl")

    def tearDown(self):
        self.dir.cleanup()

    def test_tokens_und_modell(self):
        make_transcript(self.tr, tokens=123_456, model="claude-test-9")
        tokens, model = cg.read_context_tokens(self.tr)
        self.assertEqual(tokens, 123_456)
        self.assertEqual(model, "claude-test-9")

    def test_sidechain_wird_uebersprungen(self):
        make_transcript(self.tr, tokens=100_000)
        with open(self.tr, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "isSidechain": True,
                        "message": {"model": "sub", "usage": {"input_tokens": 999_999}},
                    }
                )
                + "\n"
            )
        tokens, _ = cg.read_context_tokens(self.tr)
        self.assertEqual(tokens, 100_000)

    def test_session_start_time_aus_timestamp(self):
        make_transcript(self.tr, ts="2026-08-01T10:00:00.000Z")
        start = cg.session_start_time(self.tr)
        self.assertIsNotNone(start)
        # 2026-08-01T10:00:00Z als Epoch, unabhängig von der lokalen Zeitzone
        import datetime

        expected = datetime.datetime(
            2026, 8, 1, 10, 0, 0, tzinfo=datetime.timezone.utc
        ).timestamp()
        self.assertAlmostEqual(start, expected, delta=1)


class TestBomStdin(unittest.TestCase):
    def test_bom_wird_toleriert(self):
        payload = '{"a": 1}'.encode("utf-8")
        alt = sys.stdin
        try:
            sys.stdin = type("S", (), {"buffer": io.BytesIO(b"\xef\xbb\xbf" + payload)})()
            self.assertEqual(cg.read_stdin_json(), {"a": 1})
        finally:
            sys.stdin = alt


class TestChangelogUntouched(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.tr = os.path.join(self.dir.name, "t.jsonl")

    def tearDown(self):
        self.dir.cleanup()

    def test_fehlende_datei_ist_untouched(self):
        make_transcript(self.tr)
        self.assertTrue(cg.changelog_untouched(self.dir.name, self.tr, "2026-08-01"))

    def test_frisch_beruehrte_datei_unterdrueckt(self):
        # Session-Start liegt in der Vergangenheit (timestamp 2026), Datei ist jünger
        make_transcript(self.tr, ts="2020-01-01T00:00:00.000Z")
        os.makedirs(os.path.join(self.dir.name, "changelog"))
        cl = os.path.join(self.dir.name, "changelog", "2026-08-01.md")
        with open(cl, "w", encoding="utf-8") as f:
            f.write("# heute")
        self.assertFalse(cg.changelog_untouched(self.dir.name, self.tr, "2026-08-01"))

    def test_alte_datei_ist_untouched(self):
        make_transcript(self.tr, ts="2030-01-01T00:00:00.000Z")  # Session "später"
        os.makedirs(os.path.join(self.dir.name, "changelog"))
        cl = os.path.join(self.dir.name, "changelog", "2026-08-01.md")
        with open(cl, "w", encoding="utf-8") as f:
            f.write("# alt")
        self.assertTrue(cg.changelog_untouched(self.dir.name, self.tr, "2026-08-01"))


class TestStufenlogikEndToEnd(unittest.TestCase):
    """main() komplett: stdin, env, Marker, Block-Ausgabe."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.tr = os.path.join(self.dir.name, "t.jsonl")
        self.alt_env = dict(os.environ)
        os.environ["CLAUDE_PROJECT_DIR"] = self.dir.name
        os.environ.pop("CLAUDE_MEMORY_STAGES", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.alt_env)
        self.dir.cleanup()

    def run_guard(self, tokens, window="200000", session="testsess"):
        make_transcript(self.tr, tokens=tokens)
        os.environ["CLAUDE_CONTEXT_WINDOW"] = window
        payload = json.dumps(
            {
                "session_id": session,
                "transcript_path": self.tr,
                "cwd": self.dir.name,
                "stop_hook_active": False,
            }
        ).encode("utf-8")
        alt_stdin, alt_stdout = sys.stdin, sys.stdout
        try:
            sys.stdin = type("S", (), {"buffer": io.BytesIO(payload)})()
            sys.stdout = io.StringIO()
            cg.main()
            return sys.stdout.getvalue()
        finally:
            sys.stdin, sys.stdout = alt_stdin, alt_stdout

    @staticmethod
    def reason(out):
        """Block-Output parsen: liefert die dekodierte reason (oder '')."""
        return json.loads(out).get("reason", "") if out.strip() else ""

    def test_stufen_eskalieren_und_feuern_einmal(self):
        out = self.run_guard(tokens=60_000)  # 30 % -> Stufe 1
        self.assertIn("Gedächtnis-Check", self.reason(out))
        out = self.run_guard(tokens=61_000)  # wieder Stufe-1-Zone -> still
        self.assertEqual(out, "")
        out = self.run_guard(tokens=140_000)  # 70 % -> Stufe 2
        self.assertIn("HANDOFF", self.reason(out))
        out = self.run_guard(tokens=180_000)  # 90 % -> Stufe 3
        self.assertIn("AKTUALISIERE", self.reason(out))
        out = self.run_guard(tokens=185_000)  # bleibt still
        self.assertEqual(out, "")

    def test_kompaktierung_gibt_stufen_frei(self):
        self.run_guard(tokens=180_000)  # Stufe 3 verbraucht
        out = self.run_guard(tokens=60_000)  # Einbruch > 25 Punkte -> Reset -> Stufe 1
        self.assertIn("Gedächtnis-Check", self.reason(out))

    def test_beweis_erkennung_ohne_doppelzuendung(self):
        self.run_guard(tokens=180_000)  # Stufe 3 bei 200k-Annahme (90 %)
        # 250k Tokens: Beweis -> Fenster 1M, pct stürzt auf 25 % - darf NICHT re-feuern
        out = self.run_guard(tokens=250_000)
        self.assertEqual(out, "")
        state_files = [
            f
            for f in os.listdir(os.path.join(self.dir.name, "tmp", "handoff"))
            if f.startswith(".state-")
        ]
        with open(
            os.path.join(self.dir.name, "tmp", "handoff", state_files[0]), encoding="utf-8"
        ) as f:
            self.assertEqual(json.load(f).get("window_detected"), 1_000_000)

    def test_selbstschutz_gitignore_entsteht(self):
        self.run_guard(tokens=10_000)  # unter allen Stufen, Marker wird trotzdem geschrieben
        gi = os.path.join(self.dir.name, "tmp", "handoff", ".gitignore")
        with open(gi, encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "*")


class TestSessionStart(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.handoff_dir = os.path.join(self.dir.name, "tmp", "handoff")
        os.makedirs(self.handoff_dir)

    def tearDown(self):
        self.dir.cleanup()

    def test_compact_bevorzugt_eigene_session(self):
        eigen = os.path.join(self.handoff_dir, "handoff-2026-08-01-abcd1234.md")
        fremd = os.path.join(self.handoff_dir, "handoff-2026-08-01-fremd999.md")
        with open(eigen, "w", encoding="utf-8") as f:
            f.write("EIGEN")
        time.sleep(0.05)
        with open(fremd, "w", encoding="utf-8") as f:
            f.write("FREMD")
        # fremd ist jünger, aber session_started liegt NACH eigen und VOR fremd? Nein:
        # ohne mtime-Fenster gewinnt die Session-ID-Präferenz
        name, _, content = ss.pick_handoff(self.dir.name, "abcd1234", None)
        self.assertEqual(content, "EIGEN")

    def test_compact_nimmt_manuelles_handoff_der_laufzeit(self):
        alt = os.path.join(self.handoff_dir, "handoff-2026-08-01-abcd1234.md")
        with open(alt, "w", encoding="utf-8") as f:
            f.write("WAECHTER-STAND")
        time.sleep(0.05)
        session_started = time.time()  # Session "begann" jetzt
        time.sleep(0.05)
        manuell = os.path.join(self.handoff_dir, "handoff-2026-08-01-relaunch.md")
        with open(manuell, "w", encoding="utf-8") as f:
            f.write("MANUELL-FRISCH")
        name, _, content = ss.pick_handoff(self.dir.name, "abcd1234", session_started)
        self.assertEqual(content, "MANUELL-FRISCH")

    def test_lookup_erkennt_varianten(self):
        os.makedirs(os.path.join(self.dir.name, "docs"))
        with open(os.path.join(self.dir.name, "docs", "KNOWLEDGE.md"), "w", encoding="utf-8") as f:
            f.write("# DB\n\n## Quick-Lookup\n\n| a | b |\n|---|---|\n| SympX | E-1 |\n\n## E-1\nvoll")
        pfad, tabelle = ss.learnings_lookup(self.dir.name)
        self.assertEqual(pfad, "docs/KNOWLEDGE.md")
        self.assertIn("SympX", tabelle)
        self.assertNotIn("voll", tabelle)

    def test_marker_reset_erhaelt_fenster_cache(self):
        marker = os.path.join(self.handoff_dir, ".state-abcd1234.json")
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"stage": 3, "pct": 90.0, "window_detected": 1_000_000}, f)
        ss.reset_guard_marker(self.dir.name, "abcd1234")
        with open(marker, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["stage"], 0)
        self.assertEqual(data["window_detected"], 1_000_000)


if __name__ == "__main__":
    unittest.main()
