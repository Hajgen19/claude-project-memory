#!/usr/bin/env python3
"""Sessionstart (SessionStart-Hook, Matcher: startup|clear|compact).

Speist zwei Dinge in den frischen Kontext ein, sofern vorhanden:

  1. Das passende Übergabedokument aus tmp/handoff/ – nach einer Kompaktierung
     bevorzugt das der EIGENEN Session (Dateiname enthält die Session-Kurz-ID),
     sonst das jüngste. So kann die Arbeit nahtlos dort weitergehen, wo die
     letzte Session (bzw. der Stand vor der Kompaktierung) aufgehört hat.
  2. Die Schnell-Lookup-Tabelle der Wissensdatenbank – damit das Modell von
     Anfang an weiß, WELCHE gelösten Probleme dokumentiert sind, ohne die
     vollen Einträge zu tragen. Datei- und Überschrift-Varianten entsprechen
     dem knowledge-base-entry-Skill, der die Datenbank pflegt.

Nebenbei: Beim compact-Event wird der Stufen-Marker des Kontext-Wächters für
diese Session zurückgesetzt (neuer Kompaktierungszyklus = Stufen wieder frei),
und Marker älter als 7 Tage werden entsorgt. Fehler enden immer mit Exit 0 –
ein kaputter Hook darf den Sessionstart niemals stören.
"""

import datetime
import glob
import json
import os
import sys
import time

MAX_HANDOFF_CHARS = 6_000
MAX_LOOKUP_CHARS = 2_500
HANDOFF_MAX_AGE_DAYS = 14
STATE_MAX_AGE_DAYS = 7

# Muss zur Suchreihenfolge des knowledge-base-entry-Skills passen (Schritt 1)
KB_CANDIDATES = [
    os.path.join("docs", "LEARNINGS-CLAUDE-PROJECT.md"),
    os.path.join("docs", "LEARNINGS.md"),
    os.path.join("docs", "KNOWLEDGE.md"),
    os.path.join("docs", "KNOWLEDGE-BASE.md"),
    "LEARNINGS-CLAUDE-PROJECT.md",
    "LEARNINGS.md",
    "KNOWLEDGE.md",
    "KNOWLEDGE-BASE.md",
]
# Überschrift-Varianten der Lookup-Tabelle, die der Skill pflegt (Schritt 2c)
LOOKUP_PREFIXES = ("## schnell-lookup", "## lookup", "## quick-lookup", "## symptom-lookup")


def read_stdin_json():
    """stdin als Bytes lesen und BOM-tolerant dekodieren (vgl. context_guard.py)."""
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    return json.loads(raw)


def session_start_time(transcript_path):
    """Epoch-Zeit des Session-Beginns aus der ersten Transcript-Zeile – oder None.

    (Identisch zu context_guard.py; getctime wäre auf POSIX die wandernde
    Inode-Change-Time und als Session-Start-Proxy unbrauchbar.)
    """
    if not transcript_path:
        return None
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


def pick_handoff(project, session, session_started):
    """(dateiname, alter_in_tagen, inhalt) des passendsten Handoffs – oder None.

    Nach einer Kompaktierung (session gesetzt) gehören zwei Sorten Dateien zur
    eigenen Session: die vom Kontext-Wächter angestoßenen (Session-Kurz-ID im
    Namen) UND manuell per /handoff geschriebene (beliebiger Name, aber mtime
    innerhalb der Session-Laufzeit). Beide bevorzugen – parallele Sessions im
    selben Projekt dürfen den eigenen Stand nicht verdrängen, und ein frisches
    manuelles Handoff darf nicht gegen ein älteres Wächter-Handoff verlieren.
    """
    # Nur echte Übergabedokumente (handoff-*.md) – der Ordner enthält auch
    # eine selbst angelegte README.md, die nie als Handoff gelten darf.
    all_files = glob.glob(os.path.join(project, "tmp", "handoff", "handoff-*.md"))
    if not all_files:
        return None
    own = [p for p in all_files if session and session in os.path.basename(p)]
    if session and session_started:
        for p in all_files:
            try:
                if os.path.getmtime(p) >= session_started - 5:
                    own.append(p)
            except OSError:
                pass
    pool = sorted(set(own)) or all_files
    path = max(pool, key=os.path.getmtime)
    age_days = int((time.time() - os.path.getmtime(path)) / 86_400)
    if age_days > HANDOFF_MAX_AGE_DAYS:
        return None  # veraltete Handoffs stiften mehr Verwirrung als Nutzen
    with open(path, encoding="utf-8", errors="replace") as f:
        content = f.read().strip()
    if not content:
        return None
    if len(content) > MAX_HANDOFF_CHARS:
        content = content[:MAX_HANDOFF_CHARS] + "\n[… gekürzt – Volltext in der Datei]"
    return os.path.basename(path), age_days, content


def learnings_lookup(project):
    """(relativer pfad, lookup-tabelle) der Wissensdatenbank – oder None."""
    for candidate in KB_CANDIDATES:
        path = os.path.join(project, candidate)
        if os.path.isfile(path):
            break
    else:
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    section, collecting = [], False
    for line in lines:
        if line.startswith("## "):
            if collecting:
                break
            collecting = line.strip().lower().startswith(LOOKUP_PREFIXES)
            continue
        if collecting:
            section.append(line)
    table = "\n".join(section).strip()
    if not table or "|" not in table:
        return None
    if len(table) > MAX_LOOKUP_CHARS:
        table = table[:MAX_LOOKUP_CHARS] + "\n[… gekürzt]"
    return candidate.replace(os.sep, "/"), table


def reset_guard_marker(project, session):
    """Stufen des Kontext-Wächters freigeben (neuer Kompaktierungszyklus).

    Nur die Stufe wird genullt – ein per Messung erkanntes Kontextfenster
    (window_detected) bleibt erhalten, sonst fiele die Erkenntnis nach jeder
    Kompaktierung zurück und die Stufen kämen wieder zu früh.
    """
    if not session:
        return
    path = os.path.join(project, "tmp", "handoff", f".state-{session}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    data["stage"] = 0
    data["pct"] = 0.0
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def cleanup_state(project):
    """Marker-Dateien des Kontext-Wächters entsorgen, die älter als 7 Tage sind."""
    for path in glob.glob(os.path.join(project, "tmp", "handoff", ".state-*.json")):
        try:
            if time.time() - os.path.getmtime(path) > STATE_MAX_AGE_DAYS * 86_400:
                os.remove(path)
        except OSError:
            pass


def main():
    payload = read_stdin_json()
    project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    session = (payload.get("session_id") or "")[:8]
    source = payload.get("source") or ""

    if source == "compact":
        reset_guard_marker(project, session)
    cleanup_state(project)

    # Bei compact UND resume läuft dieselbe Session weiter – Handoffs der
    # eigenen Session-ID bzw. der eigenen Laufzeit haben Vorrang. Bei fork
    # entsteht eine neue Session-ID (Ursprung nicht zuverlässig bestimmbar):
    # wie startup behandeln, also projektweit jüngstes Handoff.
    own_session = source in ("compact", "resume")

    parts = []
    # Onboarding-Netz: Lief memory-init in diesem Projekt noch nie (keine
    # Marker-Datei), bekommt das Modell einen Einzeiler mit – es erwähnt den
    # fehlenden Schritt beim passenden Moment, statt dass er nur im README steht.
    if source == "startup" and not os.path.isfile(
        os.path.join(project, "tmp", "handoff", ".init-done")
    ):
        parts.append(
            "## project-memory: Andocken steht aus\n\n"
            "Das project-memory-Plugin ist aktiv (Kontext-Wächter läuft), aber "
            "/project-memory:memory-init wurde in diesem Projekt noch nicht ausgeführt – "
            "es fehlen also .gitignore-Absicherung der Learnings-Datenbank, "
            "Changelog-Konvention und Kontextfenster-Konfiguration. Weise den User "
            "bei passender Gelegenheit EINMAL kurz darauf hin (ein Satz genügt, "
            "nicht wiederholen, nicht drängen)."
        )
    started = session_start_time(payload.get("transcript_path")) if own_session else None
    handoff = pick_handoff(project, session if own_session else "", started)
    if handoff:
        name, age_days, content = handoff
        alter = "heute" if age_days == 0 else f"vor {age_days} Tag(en)"
        parts.append(
            f"## Übergabedokument der letzten Session (tmp/handoff/{name}, {alter})\n\n"
            f"{content}\n\n"
            "Wenn die aktuelle Aufgabe daran anknüpft, arbeite nahtlos auf diesem Stand "
            "weiter, statt bereits Entschiedenes neu aufzurollen. Wenn der User etwas "
            "Unabhängiges beginnt, ignoriere das Dokument."
        )
    lookup = learnings_lookup(project)
    if lookup:
        kb_path, table = lookup
        parts.append(
            f"## Wissensdatenbank-Index ({kb_path})\n\n"
            "Diese gelösten Probleme sind im Projekt dokumentiert. Tritt ein passendes "
            f"Symptom auf, lies zuerst den vollen Eintrag in {kb_path}, bevor du "
            "neu diagnostizierst:\n\n"
            f"{table}"
        )
    if not parts:
        return
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n\n---\n\n".join(parts),
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # niemals den Sessionstart stören
    sys.exit(0)
