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
WINDOW_1M = 1_000_000
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
    """(tokens, modell_id) der letzten Haupt-Antwort – oder (None, None).

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
        message = obj.get("message") or {}
        usage = message.get("usage") or {}
        if "input_tokens" not in usage:
            continue
        tokens = (
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
        )
        return tokens, str(message.get("model") or "")
    return None, None


def resolve_stages(env_value):
    """Schwellen aus CLAUDE_MEMORY_STAGES ("25,60,85") – oder die Defaults.

    Erwartet genau drei Prozentwerte, wird aufsteigend sortiert. Bei allem,
    was keine drei sauberen Werte zwischen 0 und 100 ergibt, gelten die
    Defaults – eine kaputte Konfiguration darf den Wächter nicht lahmlegen.
    """
    if not env_value:
        return STAGE1_PCT, STAGE2_PCT, STAGE3_PCT
    try:
        parts = sorted(float(x.strip()) for x in env_value.split(","))
    except ValueError:
        return STAGE1_PCT, STAGE2_PCT, STAGE3_PCT
    if len(parts) != 3 or not (0 < parts[0] < parts[1] < parts[2] <= 100):
        return STAGE1_PCT, STAGE2_PCT, STAGE3_PCT
    return parts[0], parts[1], parts[2]


def resolve_window(env_value, cached_window, tokens, model):
    """Effektives Kontextfenster bestimmen (v1.1: Auto-Erkennung).

    Prioritäten:
      1. Beweis dieser Messung: Übersteigen die gemessenen Tokens das
         angenommene Fenster, IST das Fenster größer – hochschalten auf 1M.
      2. Modell-ID-Hinweis: trägt sie eine 1M-Kennung ("[1m]"), sofort 1M.
      3. In dieser Session bereits erkanntes Fenster (Marker-Cache) – sonst
         fiele die Erkenntnis nach einer Kompaktierung zurück.
      4. Explizites CLAUDE_CONTEXT_WINDOW aus der Projekt-settings.json.
      5. Default 200000.

    Rückgabe: (fenster, erkannt_bool) – erkannt=True, wenn 1/2 gegriffen
    haben und der Wert in den Marker gecacht werden soll.
    """
    try:
        window = int(env_value) if env_value else WINDOW_DEFAULT
    except ValueError:
        window = WINDOW_DEFAULT
    if window <= 0:
        window = WINDOW_DEFAULT

    if cached_window and cached_window > window:
        window = cached_window

    detected = False
    if model and "[1m]" in model.lower() and window < WINDOW_1M:
        window = WINDOW_1M
        detected = True
    if tokens and tokens > window:
        window = WINDOW_1M
        detected = True
    return window, detected


def load_state(state_file):
    """(stage, letzter_prozentwert, erkanntes_fenster) aus der Marker-Datei."""
    try:
        with open(state_file, encoding="utf-8") as f:
            data = json.load(f)
        return (
            int(data.get("stage", 0)),
            float(data.get("pct", 0.0)),
            int(data.get("window_detected") or 0),
        )
    except (OSError, ValueError, TypeError):
        return 0, 0.0, 0


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
    info = os.path.join(state_dir, "README.md")
    if not os.path.isfile(info):
        with open(info, "w", encoding="utf-8") as f:
            f.write(
                "# tmp/handoff/\n\n"
                "Angelegt vom project-memory-Plugin: Session-Übergabedokumente und\n"
                "Wächter-Marker. Bleibt per eigener .gitignore lokal, ist gefahrlos\n"
                "löschbar. Doku: https://github.com/Hajgen19/claude-project-memory\n"
            )


def de_number(n):
    """120400 -> '120.400' (deutsche Tausendertrennung)."""
    return f"{n:,}".replace(",", ".")


def build_reason(stage, pct, tokens, window, handoff_file, today):
    kopf = (
        f"[project-memory · Kontext-Wächter] Diese Session hat {pct:.0f} % des "
        f"Kontextfensters erreicht ({de_number(tokens)} von {de_number(window)} Tokens)."
    )
    fuss = (
        "\n\n(Automatischer Stop-Hook des project-memory-Plugins. Wenn du dabei etwas "
        "schreibst, erwähne dem User kurz, dass die Sicherung vom Plugin kommt. Schwellen: "
        "CLAUDE_MEMORY_STAGES, manueller Handoff: /project-memory:handoff, "
        "deaktivieren: /plugin disable project-memory.)"
    )
    if stage == 1:
        return (
            f"{kopf} Kurzer Gedächtnis-Check, einmal pro Session:\n\n"
            f"1. CHANGELOG: Liegen in dieser Session bereits ABGESCHLOSSENE Ergebnisse "
            "vor, die im Changelog des Projekts noch fehlen? Falls ja, trage sie jetzt "
            "ein. Maßgeblich ist die Changelog-Konvention des Projekts (CLAUDE.md); hat "
            f"das Projekt keine, gilt der Standard changelog/{today}.md (Datei bei Bedarf "
            f"anlegen; Überschrift '# {today} – Kurztitel', Einträge knapp und thematisch "
            "gruppiert, nur Fakten im Perfekt – nichts Halbfertiges). Lege KEINE zweite "
            "Changelog-Struktur an, wenn bereits eine andere existiert.\n\n"
            "2. LEARNINGS: Wurde in dieser Session bereits ein technisches Problem "
            "gelöst, auf das alle vier Learning-Kriterien zutreffen (mehr als ein "
            "Anlauf; Ursache nicht aus der Fehlermeldung ablesbar; wiederholbar; Lösung "
            "nicht trivial)? Falls ja, schlage dem User einen Eintrag über den "
            "knowledge-base-entry-Skill des project-memory-Plugins vor.\n\n"
            "Trifft beides nicht zu, beende deinen Turn einfach normal, ohne das dem "
            "User gegenüber zu erwähnen." + fuss
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
            "Danach beende deinen Turn normal." + fuss
        )
    return (
        f"{kopf} Die Kompaktierung rückt näher – bring das Übergabedokument auf den letzten "
        f"Stand:\n\n"
        f"AKTUALISIERE {handoff_file} so, dass es den JETZIGEN Stand vollständig wiedergibt "
        "(seit dem letzten Handoff Erledigtes, neue Entscheidungen, aktueller nächster Schritt). "
        "Die Datei komplett neu schreiben, nicht anhängen. Falls im heutigen Changelog-Eintrag "
        "inzwischen abgeschlossene Ergebnisse fehlen, ergänze sie ebenfalls.\n\n"
        "Und: Wurde seit der letzten Prüfung ein technisches Problem gelöst, auf das alle "
        "vier Learning-Kriterien zutreffen (mehr als ein Anlauf; Ursache nicht aus der "
        "Fehlermeldung ablesbar; wiederholbar; Lösung nicht trivial)? Falls ja, schlage dem "
        "User JETZT einen Eintrag über den knowledge-base-entry-Skill vor – nach der "
        "Kompaktierung sind die Details der Lösung womöglich verloren. Falls nein, "
        "kommentarlos übergehen.\n\n"
        "Danach beende deinen Turn normal." + fuss
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

    # Die usage-Zeile der soeben beendeten Antwort wird u. U. erst NACH dem
    # Stop-Event ins Transcript geflusht (Race, v. a. beim ersten Stop einer
    # frischen Session). Kurz nachfassen, bevor wir aufgeben.
    tokens, model = read_context_tokens(transcript)
    for _ in range(4):
        if tokens:
            break
        time.sleep(0.7)
        tokens, model = read_context_tokens(transcript)
    if not tokens:
        return
    today = datetime.date.today().isoformat()

    session = (payload.get("session_id") or "unbekannt")[:8]
    state_dir = os.path.join(project, "tmp", "handoff")
    state_file = os.path.join(state_dir, f".state-{session}.json")
    stage, last_pct, cached_window = load_state(state_file)

    window, detected = resolve_window(
        os.environ.get("CLAUDE_CONTEXT_WINDOW"), cached_window, tokens, model
    )
    pct = tokens * 100.0 / window
    s1, s2, s3 = resolve_stages(os.environ.get("CLAUDE_MEMORY_STAGES"))

    # Kompaktierung erkennen: Fällt der Verbrauch deutlich unter den beim
    # letzten Lauf gemessenen Stand, beginnt ein neuer Zyklus – Stufen wieder
    # freigeben. (Primär setzt session_start.py den Marker beim compact-Event
    # zurück; dieser Fallback greift, falls der Hook dort nicht lief.)
    # Ausnahme: Wurde das Fenster SOEBEN per Beweis hochgeschaltet (frische
    # Erkennung, noch kein Cache), ist der pct-Einbruch nur die Umrechnung –
    # keine Kompaktierung, Stufen bleiben verbraucht.
    fresh_detection = detected and not cached_window
    if stage > 0 and last_pct - pct > 25.0 and not fresh_detection:
        stage = 0

    new_stage = None
    if observe_only:
        pass  # nur messen, Marker aktualisieren – keine Stufe zünden
    elif pct >= s3 and stage < 3:
        new_stage = 3
    elif pct >= s2 and stage < 2:
        new_stage = 2
    elif pct >= s1 and stage < 1:
        # Changelog-Check nur, wenn die Tagesdatei diese Session noch nicht sah;
        # sonst Stufe still als erledigt markieren.
        if changelog_untouched(project, transcript, today):
            new_stage = 1
        else:
            stage = 1

    # Marker bei JEDEM Lauf schreiben: pct dient dem nächsten Lauf als
    # Referenz für die Kompaktierungs-Erkennung, window_detected konserviert
    # ein per Beweis erkanntes 1M-Fenster über Kompaktierungen hinweg.
    ensure_state_dir(state_dir)
    state = {"stage": new_stage or stage, "pct": round(pct, 1)}
    if detected or cached_window:
        state["window_detected"] = max(window if detected else 0, cached_window)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f)
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
