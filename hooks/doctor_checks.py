#!/usr/bin/env python3
"""Deterministische Prüfungen für den doctor-Skill (kein Hook).

Aufruf:  python hooks/doctor_checks.py [<projektpfad>]

Der doctor-Skill läuft als Anweisung an das Modell und ist auf Shell-Befehle
angewiesen, die sich zwischen Bash und PowerShell unterscheiden. Die beiden
Prüfungen hier sind deshalb in Python gebündelt, damit der Befund auf jeder
Plattform gleich ausfällt:

  1. Betriebsregeln in der Übergabe: Zählt im jüngsten Übergabedokument die
     Listenzeilen, die mit „nie", „niemals" oder „immer" beginnen (optional
     „nicht" + Verb). Mehr als RULE_LINE_LIMIT davon heißt: Das Dokument
     trägt dauerhafte Regeln statt Zustand – die gehören in die CLAUDE.md
     unter `## Betriebsregeln`. „nur" und „keine" zählen bewusst NICHT
     (Zustandssätze wie „Keine Änderungen heute" wären Fehlalarme).
  2. Symptom-Hook-Reichweite: Wie viele Zeilen der Lookup-Tabelle haben eine
     Backtick-Suchphrase und sind damit für den Symptom-Treffer-Hook sichtbar?

Ausgabe: je Prüfung eine Zeile, immer Exit 0.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_start as ss  # noqa: E402
import symptom_match as sm  # noqa: E402

RULE_LINE_LIMIT = 15
# Listenzeile (- oder *), optional fett, dann nie/niemals/immer – oder
# „nicht" gefolgt von einem Infinitiv auf -en („nicht committen").
RULE_LINE_RE = re.compile(
    r"^\s*[-*]\s+(?:\*\*)?(?:nie|niemals|immer|nicht\s+\w+en)\b", re.IGNORECASE
)


def count_rule_lines(text):
    """Anzahl der Imperativ-Listenzeilen in einem Übergabedokument."""
    return sum(1 for line in text.splitlines() if RULE_LINE_RE.match(line))


def lookup_rows(kb_lines):
    """Datenzeilen der Lookup-Tabelle (ohne Kopf- und Trennzeile)."""
    rows = []
    for line in ss.extract_lookup_lines(kb_lines):
        row = line.strip()
        if not row.startswith("|") or sm.TABLE_SEPARATOR_RE.match(row):
            continue
        if "was du siehst" in row.lower():
            continue
        rows.append(row)
    return rows


def check_handoff_rules(project):
    found = ss.pick_handoff(project, "", None)
    if not found:
        return "Betriebsregeln: – (kein Übergabedokument unter tmp/handoff/)"
    name, _, content = found
    n = count_rule_lines(content)
    if n > RULE_LINE_LIMIT:
        return (
            f"Betriebsregeln: ✗ {name} enthält {n} Regel-Listenzeilen "
            f"(nie/niemals/immer, Grenze {RULE_LINE_LIMIT}) – dauerhafte Regeln nach "
            "CLAUDE.md unter '## Betriebsregeln' verschieben, die Übergabe trägt nur Zustand"
        )
    return f"Betriebsregeln: ✓ {name} enthält {n} Regel-Listenzeilen (Grenze {RULE_LINE_LIMIT})"


def check_symptom_coverage(project):
    found = ss.find_kb_path(project)
    if not found:
        return "Symptom-Hook: – (keine Wissensdatenbank gefunden)"
    rel_path, path = found
    with open(path, encoding="utf-8", errors="replace") as f:
        kb_lines = f.read().splitlines()
    rows = lookup_rows(kb_lines)
    phrases = sm.build_phrases(kb_lines)
    covered = len({entry_id for _, entry_id in phrases})
    if not rows:
        return f"Symptom-Hook: – ({rel_path} hat keine Lookup-Tabelle)"
    hint = "" if covered == len(rows) else (
        " – Zeilen ohne Backtick-Fehlertext sind für den Hook unsichtbar; "
        "Symptom in Backticks nachtragen"
    )
    return (
        f"Symptom-Hook: {covered} von {len(rows)} Lookup-Zeilen in {rel_path} haben "
        f"eine Backtick-Suchphrase ({len(phrases)} Phrasen){hint}"
    )


def main():
    project = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    print(check_handoff_rules(project))
    print(check_symptom_coverage(project))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # Diagnose-Helfer: Fehler benennen, aber nie crashen
        print(f"doctor_checks: Fehler – {exc}")
    sys.exit(0)
