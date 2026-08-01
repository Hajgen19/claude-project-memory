#!/usr/bin/env python3
"""Kontext-Wächter (Stop-Hook des project-memory-Plugins).

Misst nach jeder Antwort den tatsächlichen Kontextverbrauch der Session anhand
der Token-Zahlen im Transcript (JSONL) und stößt gestuft die Sicherung an:

  Stufe 1 (ab 25 %): Changelog-Check – nur wenn die heutige Tagesdatei in
                     dieser Session noch nicht angefasst wurde
  Stufe 2 (ab 60 %): Handoff schreiben + Changelog nachziehen + Learnings prüfen
  Stufe 3 (ab 85 %): Handoff aktualisieren

Mechanik: Der Hook gibt {"decision": "block", "reason": "<Auftrag>"} aus.
Claude erhält den Auftrag als Anweisung und arbeitet weiter; der eingebaute
Schleifenschutz (stop_hook_active) verhindert, dass der Folge-Stop erneut
blockt. Pro Session und Stufe feuert der Wächter genau einmal (Marker-Datei
unter tmp/handoff/ im Projekt); nach einer Kompaktierung sind die Stufen
wieder frei (Marker-Reset durch session_start.py bzw. Erkennung am
Token-Einbruch).

Das Kontextfenster wird über die Umgebungsvariable CLAUDE_CONTEXT_WINDOW
konfiguriert (Default 200000; in der settings.json des Projekts unter "env"
setzbar, bei 1M-Kontext 1000000 – der /project-memory:memory-init-Skill
bietet das beim Andocken an).

Der Hook darf niemals mit Exit-Code 2 enden (das würde den Stop blockieren,
ohne dass ein Auftrag ankommt) – deshalb ist main() komplett abgesichert und
jeder Fehlerpfad endet mit Exit 0.
"""

import datetime
import json
import os
import sys
import time

WINDOW_DEFAULT = 200_000
STAGE1_PCT = 25.0  # Changelog-Check
STAGE2_PCT = 60.0  # Handoff + Changelog + Learnings
STAGE3_PCT = 85.0  # Handoff-Update
TAIL_BYTES = 512 * 1024  # Transcripts können > 70 MB groß werden – nur das Ende lesen


def read_stdin_json():
    """stdin als Bytes lesen und BOM-tolerant dekodieren.

    Manche Zubringer-Shells (z. B. Windows PowerShell 5.1) stellen dem Payload
    ein UTF-8-BOM voran, an dem json.load(sys.stdin) scheitern würde.
    """
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    return json.loads(raw)


def read_context_tokens(transcript_path):
    """Liefert den Kontextverbrauch der letzten Haupt-Antwort in Tokens (oder None).

    Liest die letzten TAIL_BYTES des Transcripts und sucht rückwärts die
    jüngste Assistant-Zeile mit usage-Block. input + cache_read + cache_creation
    ergeben zusammen die tatsächliche Kontextfüllung der letzten Anfrage.
    """
    with open(transcript_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - TAIL_BYTES))
        chunk = f.read()
    lines = chunk.decode("utf-8", errors="replace").splitlines()
    if size > TAIL_BYTES and lines:
        lines = lines[1:]  # erste Zeile ist vermutlich angeschnitten
    for line in reversed(lines):
        if '"usage"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("isSidechain"):
            continue  # Subagenten-Zeilen zählen nicht als Hauptkontext
        usage = (obj.get("message") or {}).get("usage") or {}
        if "input_tokens" not in usage:
            continue
        return (
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
        )
    return None


def load_state(state_file):
    """(stage, letzter_gemessener_prozentwert) aus der Marker-Datei."""
    try:
        with open(state_file, encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("stage", 0)), float(data.get("pct", 0.0))
    except (OSError, ValueError, TypeError):
        return 0, 0.0


def session_start_time(transcript_path):
    """Epoch-Zeit des Session-Beginns – oder None.

    Plattformfest über das timestamp-Feld der ersten Transcript-Zeile
    (os.path.getctime wäre auf Linux/macOS die Inode-Change-Time, die bei
    jedem Append wandert – als Session-Start-Proxy unbrauchbar). Fallback:
    getctime, was zumindest unter Windows die echte Erstellzeit ist.
    """
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= 10:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                ts = obj.get("timestamp")
                if ts:
                    return datetime.datetime.fromisoformat(
                        ts.replace("Z", "+00:00")
                    ).timestamp()
    except (OSError, ValueError, TypeError):
        pass
    try:
        return os.path.getctime(transcript_path)
    except OSError:
        return None


def changelog_untouched(project, transcript_path, today):
    """True, wenn die heutige Changelog-Datei in DIESER Session noch nicht
    angefasst wurde (fehlt, oder mtime liegt vor dem Session-Beginn)."""
    changelog_file = os.path.join(project, "changelog", f"{today}.md")
    if not os.path.isfile(changelog_file):
        return True
    start = session_start_time(transcript_path)
    if start is None:
        return False  # im Zweifel nicht stören
    try:
        return os.path.getmtime(changelog_file) < start
    except OSError:
        return False


def ensure_state_dir(state_dir):
    """tmp/handoff/ anlegen und mit einer eigenen .gitignore selbst schützen.

    Die Ordner-lokale .gitignore (Inhalt "*") sorgt dafür, dass Handoffs und
    Marker NIE committet werden können – auch in Projekten, deren .gitignore
    tmp/ nicht ausschließt und in denen memory-init noch nicht lief.
    """
    os.makedirs(state_dir, exist_ok=True)
    gi = os.path.join(state_dir, ".gitignore")
    if not os.path.isfile(gi):
        with open(gi, "w", encoding="utf-8") as f:
            f.write("*\n")


def de_number(n):
    """120400 -> '120.400' (deutsche Tausendertrennung)."""
    return f"{n:,}".replace(",", ".")


def build_reason(stage, pct, tokens, window, handoff_file, today):
    kopf = (
        f"[Kontext-Wächter] Diese Session hat {pct:.0f} % des Kontextfensters erreicht "
        f"({de_number(tokens)} von {de_number(window)} Tokens)."
    )
    if stage == 1:
        return (
            f"{kopf} Kurzer Changelog-Check, einmal pro Session:\n\n"
            f"Liegen in dieser Session bereits ABGESCHLOSSENE Ergebnisse vor, die im "
            "Changelog des Projekts noch fehlen? Falls ja, trage sie jetzt ein. "
            "Maßgeblich ist die Changelog-Konvention des Projekts (CLAUDE.md); hat das "
            f"Projekt keine, gilt der Standard changelog/{today}.md (Datei bei Bedarf "
            f"anlegen; Überschrift '# {today} – Kurztitel', Einträge knapp und thematisch "
            "gruppiert, nur Fakten im Perfekt – nichts Halbfertiges). Lege KEINE zweite "
            "Changelog-Struktur an, wenn bereits eine andere existiert. "
            "Falls es noch nichts einzutragen gibt, beende deinen Turn einfach normal, "
            "ohne das dem User gegenüber zu erwähnen."
        )
    if stage == 2:
        return (
            f"{kopf} Sichere jetzt den Stand, bevor du weiterarbeitest:\n\n"
            f"1. HANDOFF: Schreibe ein Übergabedokument nach {handoff_file} "
            "(Ordner bei Bedarf anlegen, bestehende Datei überschreiben). Inhalt: woran gerade "
            "gearbeitet wird, welche Entscheidungen getroffen wurden, welche Wege verworfen "
            "wurden und warum, was als Nächstes ansteht. Bereits in Dateien festgehaltenes "
            "(Specs, Briefings, Commits) nur per Pfad referenzieren, nicht duplizieren. "
            "Sensible Daten (API-Keys, Zugangsdaten) auslassen.\n\n"
            "2. CHANGELOG: Ergänze abgeschlossene Ergebnisse dieser Session, die im Changelog "
            f"des Projekts noch fehlen (Konvention laut CLAUDE.md; Standard: changelog/{today}.md). "
            "Nur Fakten im Perfekt, nichts Halbfertiges – der flüchtige Zustand gehört in den "
            "Handoff, nicht ins Changelog.\n\n"
            "3. LEARNINGS: Wurde in dieser Session ein technisches Problem gelöst, auf das "
            "alle vier Learning-Kriterien zutreffen (mehr als ein Anlauf; Ursache nicht aus "
            "der Fehlermeldung ablesbar; wiederholbar; Lösung nicht trivial)? Falls ja, "
            "schlage dem User einen Eintrag über den knowledge-base-entry-Skill des "
            "project-memory-Plugins vor. Falls nein, diesen Punkt kommentarlos überspringen.\n\n"
            "Danach beende deinen Turn normal."
        )
    return (
        f"{kopf} Die Kompaktierung rückt näher – bring das Übergabedokument auf den letzten "
        f"Stand:\n\n"
        f"AKTUALISIERE {handoff_file} so, dass es den JETZIGEN Stand vollständig wiedergibt "
        "(seit dem letzten Handoff Erledigtes, neue Entscheidungen, aktueller nächster Schritt). "
        "Die Datei komplett neu schreiben, nicht anhängen. Falls im heutigen Changelog-Eintrag "
        "inzwischen abgeschlossene Ergebnisse fehlen, ergänze sie ebenfalls.\n\n"
        "Danach beende deinen Turn normal."
    )


def main():
    payload = read_stdin_json()
    # Läuft die Konversation gerade durch einen Stop-Block weiter (unseren oder
    # den eines fremden Hooks), blocken wir NIE erneut – wir messen aber
    # trotzdem und halten den Marker frisch, damit lange fremde Block-Ketten
    # den Wächter nicht aushungern und die Kompaktierungs-Erkennung aktuell bleibt.
    observe_only = bool(payload.get("stop_hook_active"))
    transcript = payload.get("transcript_path")
    if not transcript or not os.path.isfile(transcript):
        return
    project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    try:
        window = int(os.environ.get("CLAUDE_CONTEXT_WINDOW") or WINDOW_DEFAULT)
    except ValueError:
        window = WINDOW_DEFAULT
    if window <= 0:
        window = WINDOW_DEFAULT

    # Die usage-Zeile der soeben beendeten Antwort wird u. U. erst NACH dem
    # Stop-Event ins Transcript geflusht (Race, v. a. beim ersten Stop einer
    # frischen Session). Kurz nachfassen, bevor wir aufgeben.
    tokens = read_context_tokens(transcript)
    for _ in range(4):
        if tokens:
            break
        time.sleep(0.7)
        tokens = read_context_tokens(transcript)
    if not tokens:
        return
    pct = tokens * 100.0 / window
    today = datetime.date.today().isoformat()

    session = (payload.get("session_id") or "unbekannt")[:8]
    state_dir = os.path.join(project, "tmp", "handoff")
    state_file = os.path.join(state_dir, f".state-{session}.json")
    stage, last_pct = load_state(state_file)

    # Kompaktierung erkennen: Fällt der Verbrauch deutlich unter den beim
    # letzten Lauf gemessenen Stand, beginnt ein neuer Zyklus – Stufen wieder
    # freigeben. (Primär löscht session_start.py den Marker beim compact-Event;
    # dieser Fallback greift, falls der Hook dort nicht lief.)
    if stage > 0 and last_pct - pct > 25.0:
        stage = 0

    new_stage = None
    if observe_only:
        pass  # nur messen, Marker aktualisieren – keine Stufe zünden
    elif pct >= STAGE3_PCT and stage < 3:
        new_stage = 3
    elif pct >= STAGE2_PCT and stage < 2:
        new_stage = 2
    elif pct >= STAGE1_PCT and stage < 1:
        # Changelog-Check nur, wenn die Tagesdatei diese Session noch nicht sah;
        # sonst Stufe still als erledigt markieren.
        if changelog_untouched(project, transcript, today):
            new_stage = 1
        else:
            stage = 1

    # Marker bei JEDEM Lauf schreiben: pct dient dem nächsten Lauf als
    # Referenz für die Kompaktierungs-Erkennung und darf nicht veralten.
    ensure_state_dir(state_dir)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump({"stage": new_stage or stage, "pct": round(pct, 1)}, f)
    if new_stage is None:
        return

    handoff_file = f"tmp/handoff/handoff-{today}-{session}.md"
    reason = build_reason(new_stage, pct, tokens, window, handoff_file, today)
    # ensure_ascii (Default) hält die Ausgabe unabhängig vom Konsolen-Encoding
    print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # ein kaputter Wächter darf die Session niemals stören
    sys.exit(0)
