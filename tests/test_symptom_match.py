"""Tests für den Symptom-Treffer-Hook und die doctor-Prüfungen (v1.6.0).

Ausführen:  python -m unittest discover tests
Deckt die Akzeptanzkriterien AK-01 bis AK-06 der Spec ab.
"""

import io
import json
import os
import random
import string
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hooks"))
import doctor_checks as dc  # noqa: E402
import symptom_match as sm  # noqa: E402

KB = """# Test — Wissensdatenbank

## Tag-Index

| Tag | Bedeutung |
|---|---|
| #builder | Builder-Pipeline |

## Schnell-Lookup nach Symptom / Fehlermeldung

| Was du siehst | Springe zu |
|---|---|
| Eskalation `Existing tests are immutable` oder `Existing test weakened` | [E-011](#e-011-builder-testdateien) |
| Deploy kopiert alte Version | [E-024](#e-024-deploy-kopie) |
| `Timed out after 600s` | [E-025](#e-025-zeitlimit) |
| `kurz` (zu kurze Phrase) | [E-026](#e-026-kurz) |

---

## E-011 — Builder-Testdateien

**Symptom:** `Existing tests are immutable`

**Root Cause:** Vom Menschen committete Testdateien sind für den Builder unveränderlich.

**Fix:** Neue Testdatei anlegen statt bestehende ändern.

**Tags:** `#builder`

---

## E-024 — Deploy-Kopie

**Symptom:** Deploy kopiert alte Version

---

## E-025 — Zeitlimit

**Symptom:** `Timed out after 600s`

**Fix:** Timeout hochsetzen.

---

## Pflege dieser Datei

- blabla
"""

PAD = "Lorem ipsum dolor sit amet, consetetur sadipscing elitr. " * 6  # > 200 Zeichen


def run_hook(project, tool_response, session="abcdef12", env=None):
    """symptom_match.main() mit synthetischem Payload – liefert additionalContext oder ''."""
    payload = json.dumps(
        {
            "session_id": session,
            "cwd": project,
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_response": tool_response,
        }
    ).encode("utf-8")
    alt_env = dict(os.environ)
    os.environ["CLAUDE_PROJECT_DIR"] = project
    os.environ.pop("CLAUDE_MEMORY_SYMPTOMS", None)
    os.environ.update(env or {})
    alt_stdin, alt_stdout = sys.stdin, sys.stdout
    try:
        sys.stdin = type("S", (), {"buffer": io.BytesIO(payload)})()
        sys.stdout = io.StringIO()
        sm.main()
        out = sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = alt_stdin, alt_stdout
        os.environ.clear()
        os.environ.update(alt_env)
    if not out.strip():
        return ""
    data = json.loads(out)
    return data["hookSpecificOutput"]["additionalContext"]


class TestPhrasen(unittest.TestCase):
    def test_nur_backticks_liefern_phrasen(self):
        phrases = sm.build_phrases(KB.splitlines())
        ids = {entry for _, entry in phrases}
        self.assertEqual(ids, {"E-011", "E-025"})  # E-024 ohne Backticks, E-026 zu kurz
        self.assertIn(("existing tests are immutable", "E-011"), phrases)
        self.assertIn(("existing test weakened", "E-011"), phrases)

    def test_fallback_ohne_ankerlink(self):
        kb = ["## Lookup", "| Was du siehst | Eintrag |", "|---|---|",
              "| `Connection refused by peer` | E-007 |"]
        self.assertEqual(sm.build_phrases(kb), [("connection refused by peer", "E-007")])

    def test_eintrag_wird_vollstaendig_extrahiert(self):
        entry = sm.extract_entry(KB.splitlines(), "E-011")
        self.assertTrue(entry.startswith("## E-011 — Builder-Testdateien"))
        self.assertIn("**Fix:**", entry)
        self.assertNotIn("E-024", entry)  # endet am ---
        self.assertIsNone(sm.extract_entry(KB.splitlines(), "E-999"))


class TestHookEndToEnd(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.dir.name, "docs"))
        with open(os.path.join(self.dir.name, "docs", "LEARNINGS.md"), "w", encoding="utf-8") as f:
            f.write(KB)

    def tearDown(self):
        self.dir.cleanup()

    def test_ak01_treffer_einmal_pro_session(self):
        out = run_hook(self.dir.name, {"stdout": PAD + "Error: Existing tests are immutable", "stderr": ""})
        self.assertIn("Symptom von E-011", out)
        self.assertIn("## E-011 — Builder-Testdateien", out)
        self.assertIn("**Fix:** Neue Testdatei", out)        # vollständiger Eintrag
        self.assertIn("docs/LEARNINGS.md", out)
        # zweiter Treffer desselben Eintrags in derselben Session -> still
        out = run_hook(self.dir.name, {"stdout": PAD + "Existing tests are immutable", "stderr": ""})
        self.assertEqual(out, "")
        # andere Session -> wieder scharf
        out = run_hook(self.dir.name, {"stdout": PAD + "Existing tests are immutable"}, session="zzzz9999")
        self.assertIn("E-011", out)

    def test_ak01_gross_klein_und_mehrfachleerzeichen(self):
        out = run_hook(self.dir.name, {"stdout": PAD + "existing   TESTS are\n  immutable"})
        self.assertIn("Symptom von E-011", out)

    def test_ak02_laengster_treffer_gewinnt(self):
        out = run_hook(self.dir.name, {"stdout": PAD + "Timed out after 600s ... Existing tests are immutable"})
        self.assertIn("Symptom von E-011", out)   # 28 Zeichen schlägt 20
        self.assertNotIn("E-025", out)

    def test_ak02_ohne_symptom_still(self):
        self.assertEqual(run_hook(self.dir.name, {"stdout": PAD + "alles gut"}), "")

    def test_ak03_eigene_learnings_ausgabe_loest_nicht_aus(self):
        # cat LEARNINGS.md in Bash – Inhaltserkennung am ## E-Header
        self.assertEqual(run_hook(self.dir.name, {"stdout": KB, "stderr": ""}), "")
        # Read auf die Datei – gleiche Struktur wie das Read-Tool liefert
        read_response = {"type": "text", "file": {"filePath": "docs/LEARNINGS.md", "content": KB}}
        self.assertEqual(run_hook(self.dir.name, read_response), "")
        # nur die Lookup-Tabelle (z. B. Grep-Treffer) – Erkennung an der Kopfzeile
        table = PAD + "| Was du siehst | Springe zu |\n| `Existing tests are immutable` | E-011 |"
        self.assertEqual(run_hook(self.dir.name, {"stdout": table}), "")
        # der eigene Banner-Text (Hook-Ausgabe landete in einer Datei)
        banner = PAD + sm.BANNER + " Die Werkzeugausgabe enthält das Symptom … Existing tests are immutable"
        self.assertEqual(run_hook(self.dir.name, {"stdout": banner}), "")

    def test_ak03_agent_bericht_loest_aus(self):
        agent_response = {
            "content": [{"type": "text", "text": PAD + "Review escalation: Existing test weakened – aborting."}],
            "totalDurationMs": 1234,
        }
        out = run_hook(self.dir.name, agent_response)
        self.assertIn("Symptom von E-011", out)

    def test_ak04_fehlende_oder_defekte_datenbank_schweigt(self):
        os.remove(os.path.join(self.dir.name, "docs", "LEARNINGS.md"))
        self.assertEqual(run_hook(self.dir.name, {"stdout": PAD + "Existing tests are immutable"}), "")
        with open(os.path.join(self.dir.name, "docs", "LEARNINGS.md"), "w", encoding="utf-8") as f:
            f.write("# kaputt\n\nkeine Tabelle, nur Text `Existing tests are immutable`\n")
        self.assertEqual(run_hook(self.dir.name, {"stdout": PAD + "Existing tests are immutable"}), "")

    def test_ak04_abschaltung_per_env(self):
        out = run_hook(
            self.dir.name,
            {"stdout": PAD + "Existing tests are immutable"},
            env={"CLAUDE_MEMORY_SYMPTOMS": "0"},
        )
        self.assertEqual(out, "")

    def test_ak05_kurze_ausgabe_steigt_vor_dem_parsen_aus(self):
        # Backtick-Symptom enthalten, aber Ausgabe < 200 Zeichen -> kein Treffer, kein Marker
        out = run_hook(self.dir.name, {"stdout": "Existing tests are immutable"})
        self.assertEqual(out, "")
        self.assertFalse(os.path.isdir(os.path.join(self.dir.name, "tmp")))

    def test_marker_liegt_im_geschuetzten_handoff_ordner(self):
        run_hook(self.dir.name, {"stdout": PAD + "Existing tests are immutable"})
        marker = os.path.join(self.dir.name, "tmp", "handoff", ".symptoms-abcdef12.json")
        with open(marker, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"seen": ["E-011"]})
        with open(os.path.join(self.dir.name, "tmp", "handoff", ".gitignore"), encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "*")

    def test_alte_marker_werden_entsorgt(self):
        handoff_dir = os.path.join(self.dir.name, "tmp", "handoff")
        os.makedirs(handoff_dir)
        alt = os.path.join(handoff_dir, ".symptoms-alt00000.json")
        with open(alt, "w", encoding="utf-8") as f:
            f.write('{"seen": []}')
        old = time.time() - (sm.STATE_MAX_AGE_DAYS + 1) * 86_400
        os.utime(alt, (old, old))
        run_hook(self.dir.name, {"stdout": PAD + "Existing tests are immutable"})
        self.assertFalse(os.path.exists(alt))


class TestAK05Laufzeit(unittest.TestCase):
    def test_500_eintraege_20k_zeichen_unter_100ms(self):
        rows = ["## Schnell-Lookup", "| Was du siehst | Springe zu |", "|---|---|"]
        entries = []
        for i in range(1, 501):
            phrase = f"synthetic error code {i:03d} occurred in module alpha"
            rows.append(f"| `{phrase}` | [E-{i:03d}](#e-{i:03d}) |")
            entries += [f"## E-{i:03d} — Eintrag {i}", "", f"**Symptom:** `{phrase}`", "", "---", ""]
        kb = rows + ["", "---", ""] + entries
        rnd = random.Random(42)
        out = "".join(rnd.choice(string.ascii_lowercase + " \n") for _ in range(19_900))
        out += " SYNTHETIC ERROR CODE 437 occurred in module alpha"
        start = time.perf_counter()
        norm = sm.normalize(out)
        self.assertFalse(sm.looks_like_learnings(out, norm))
        match = sm.find_match(norm, sm.build_phrases(kb))
        entry = sm.extract_entry(kb, match[1])
        elapsed_ms = (time.perf_counter() - start) * 1000
        self.assertEqual(match[1], "E-437")
        self.assertIn("## E-437", entry)
        self.assertLess(elapsed_ms, 100, f"Abgleich dauerte {elapsed_ms:.1f} ms")


class TestDoctorChecks(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.handoff_dir = os.path.join(self.dir.name, "tmp", "handoff")
        os.makedirs(self.handoff_dir)

    def tearDown(self):
        self.dir.cleanup()

    def write_handoff(self, lines):
        path = os.path.join(self.handoff_dir, "handoff-2026-10-24-abcd1234.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Handoff\n\n" + "\n".join(lines) + "\n")

    def test_ak06_regelzeilen_zaehlung(self):
        regeln = ["- Nie `git add -A` benutzen", "* **Immer** vorher Tests laufen lassen",
                  "- niemals force-pushen", "- Nicht committen, bevor CI grün ist"]
        zustand = ["- Keine Änderungen heute", "- Nur noch drei Tests offen",
                   "- Nächster Schritt: CLI-Skelett", "Immer wieder lustig (keine Listenzeile)",
                   "- Nicht alle Tests laufen (Zustand, kein Infinitiv)"]
        self.assertEqual(dc.count_rule_lines("\n".join(regeln)), 4)
        self.assertEqual(dc.count_rule_lines("\n".join(zustand)), 0)

    def test_ak06_warnung_bei_16_nicht_bei_10(self):
        self.write_handoff([f"- Nie Regel Nummer {i} brechen" for i in range(16)]
                           + ["- Keine Änderungen heute", "- Nur Zustand"])
        self.assertIn("✗", dc.check_handoff_rules(self.dir.name))
        self.write_handoff([f"- Immer Regel Nummer {i} beachten" for i in range(10)]
                           + [f"- Keine Zustandszeile {i}" for i in range(20)])
        self.assertIn("✓", dc.check_handoff_rules(self.dir.name))

    def test_kein_handoff_ist_kein_fehler(self):
        self.assertIn("–", dc.check_handoff_rules(self.dir.name))

    def test_symptom_reichweite(self):
        os.makedirs(os.path.join(self.dir.name, "docs"))
        with open(os.path.join(self.dir.name, "docs", "LEARNINGS.md"), "w", encoding="utf-8") as f:
            f.write(KB)
        out = dc.check_symptom_coverage(self.dir.name)
        self.assertIn("2 von 4 Lookup-Zeilen", out)
        self.assertIn("3 Phrasen", out)
        self.assertIn("unsichtbar", out)


if __name__ == "__main__":
    unittest.main()
