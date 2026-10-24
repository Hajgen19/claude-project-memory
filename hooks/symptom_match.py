#!/usr/bin/env python3
"""Symptom-Treffer (PostToolUse-Hook für Bash, Read, Grep, Agent).

Schließt die Lücke zwischen „Learning steht in der Datenbank" und „Learning
wird im richtigen Moment gelesen": Die Lookup-Tabelle der Wissensdatenbank
wirkt nur, wenn das Modell beim passenden Symptom selbst nachschlägt – und
genau das unterbleibt in der Praxis, obwohl der Fehlertext wörtlich durch die
Werkzeugausgabe läuft. Dieser Hook übernimmt das Nachschlagen:

  1. Werkzeugausgabe aus dem Hook-Input ziehen (alle Strings in tool_response,
     maximal die letzten MAX_OUTPUT_CHARS Zeichen).
  2. Aus der Spalte „Was du siehst" der Lookup-Tabelle Suchphrasen ableiten –
     NUR Inhalte in Backticks (wörtliche Fehlertexte). Beschreibender Text
     ohne Backticks taucht nie wörtlich in Werkzeugausgaben auf, hätte aber
     Rauschpotenzial, und bleibt deshalb außen vor.
  3. Wörtlicher Substring-Abgleich (Groß-/Kleinschreibung und Mehrfach-
     Leerzeichen egal). Längster Treffer gewinnt, ein Eintrag je Aufruf.
  4. Den vollständigen Eintrag (vom `## E-nnn`-Header bis zum nächsten `---`)
     als additionalContext zurückgeben – je Session jeder Eintrag höchstens
     einmal (Marker tmp/handoff/.symptoms-<session>.json).

Rauschschutz: Enthält die Ausgabe selbst Learnings (ein `## E-nnn`-Header,
die Lookup-Kopfzeile oder den eigenen Banner-Text), schweigt der Hook – sonst
meldete `cat LEARNINGS.md` alle Einträge auf einmal. Erkannt wird am Inhalt,
nicht am Pfad, damit auch Bash-Ausgaben abgedeckt sind.

Keine Einbettungen, keine externen Dienste, nur Standardbibliothek. Der
Abgleich kostet unter 10 ms; der eigentliche Preis ist der Interpreterstart
je Werkzeugaufruf (≈ 30–50 ms), bewusst in Kauf genommen. Abschalten:
CLAUDE_MEMORY_SYMPTOMS=0. Fehler enden immer mit Exit 0.
"""

import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import context_guard as cg  # noqa: E402  (ensure_state_dir)
import session_start as ss  # noqa: E402  (Pfadsuche, Lookup-Parsing)

MAX_OUTPUT_CHARS = 20_000   # nur das Ende der Ausgabe abgleichen
MIN_OUTPUT_CHARS = 200      # darunter: Ausstieg vor dem Parsen
MIN_PHRASE_CHARS = 12       # kürzere Backtick-Inhalte sind keine Symptome
MAX_ENTRY_CHARS = 6_000     # Schutz vor Monster-Einträgen (vgl. MAX_HANDOFF_CHARS)
STATE_MAX_AGE_DAYS = 14     # wie die Wächter-Marker

BANNER = "[project-memory · Symptom-Treffer]"
BACKTICK_RE = re.compile(r"`([^`\n]+)`")
ENTRY_LINK_RE = re.compile(r"\[([A-Za-z]+-\d+)\]\(#")          # [E-011](#e-011-…)
ENTRY_ID_RE = re.compile(r"\b([A-Z]+-\d{3,})\b")                # Fallback: E-011 ohne Link
ENTRY_HEADER_RE = re.compile(r"^## [A-Za-z]+-\d+\b", re.MULTILINE)
TABLE_SEPARATOR_RE = re.compile(r"^\|[\s:|-]+\|$")


def normalize(text):
    """Kleinschreibung, jede Whitespace-Folge zu einem Leerzeichen."""
    return re.sub(r"\s+", " ", text).lower().strip()


def collect_text(obj, parts=None):
    """Alle String-Werte einer verschachtelten JSON-Struktur einsammeln.

    tool_response hat je nach Werkzeug eine andere Form (Bash: stdout/stderr,
    Read: file.content, Agent: content[].text, manchmal ein nackter String).
    Statt jede Form zu kennen, nehmen wir alles, was Text ist.
    """
    if parts is None:
        parts = []
    if isinstance(obj, str):
        parts.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            collect_text(value, parts)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            collect_text(value, parts)
    return parts


def tool_output(payload):
    """Werkzeugausgabe als ein String, auf die letzten MAX_OUTPUT_CHARS gekürzt."""
    text = "\n".join(collect_text(payload.get("tool_response")))
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[-MAX_OUTPUT_CHARS:]
    return text


def looks_like_learnings(raw, norm):
    """True, wenn die Ausgabe selbst Wissensdatenbank-Inhalt ist."""
    return (
        ENTRY_HEADER_RE.search(raw) is not None
        or "was du siehst" in norm
        or BANNER.lower() in norm
    )


def build_phrases(kb_lines):
    """Liste (suchphrase_normalisiert, eintrag_id) aus der Lookup-Tabelle.

    Je Tabellenzeile: Eintrag-ID aus dem Anker-Link (Fallback: nacktes
    `E-nnn` in der letzten Zelle), Suchphrasen aus allen Backtick-Inhalten
    der Zeile außerhalb der Link-Zelle. Zeilen ohne Backticks liefern nichts.
    """
    phrases, seen = [], set()
    for line in ss.extract_lookup_lines(kb_lines):
        row = line.strip()
        if not row.startswith("|") or TABLE_SEPARATOR_RE.match(row):
            continue
        cells = [c.strip() for c in row.strip("|").split("|")]
        if not cells or "was du siehst" in row.lower():
            continue  # Kopfzeile
        link = ENTRY_LINK_RE.search(row)
        if link:
            entry_id = link.group(1)
            link_cell = next((c for c in cells if link.group(0) in c), "")
        else:
            m = ENTRY_ID_RE.search(cells[-1])
            if not m:
                continue
            entry_id, link_cell = m.group(1), cells[-1]
        for cell in cells:
            if cell == link_cell:
                continue
            for phrase in BACKTICK_RE.findall(cell):
                norm = normalize(phrase)
                if len(norm) < MIN_PHRASE_CHARS or norm in seen:
                    continue
                seen.add(norm)
                phrases.append((norm, entry_id))
    return phrases


def find_match(norm_output, phrases, skip=()):
    """(phrase, eintrag_id) des längsten Treffers – oder None."""
    best = None
    for phrase, entry_id in phrases:
        if entry_id in skip:
            continue
        if phrase in norm_output and (best is None or len(phrase) > len(best[0])):
            best = (phrase, entry_id)
    return best


def extract_entry(kb_lines, entry_id):
    """Vollständiger Eintrag vom `## <id>`-Header bis zum nächsten `---` – oder None."""
    header_re = re.compile(r"^## " + re.escape(entry_id) + r"\b")
    out, collecting = [], False
    for line in kb_lines:
        if collecting:
            if line.strip() == "---" or line.startswith("## "):
                break
            out.append(line)
        elif header_re.match(line):
            collecting = True
            out.append(line)
    if not collecting:
        return None
    entry = "\n".join(out).strip()
    if len(entry) > MAX_ENTRY_CHARS:
        entry = entry[:MAX_ENTRY_CHARS] + "\n[… gekürzt – Volltext in der Datei]"
    return entry


def state_path(project, session):
    return os.path.join(project, "tmp", "handoff", f".symptoms-{session}.json")


def load_seen(path):
    try:
        with open(path, encoding="utf-8") as f:
            return set(json.load(f).get("seen") or [])
    except (OSError, ValueError, TypeError, AttributeError):
        return set()


def save_seen(path, seen):
    cg.ensure_state_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"seen": sorted(seen)}, f)


def cleanup_state(project):
    """Symptom-Marker älter als STATE_MAX_AGE_DAYS entsorgen."""
    for path in glob.glob(os.path.join(project, "tmp", "handoff", ".symptoms-*.json")):
        try:
            if time.time() - os.path.getmtime(path) > STATE_MAX_AGE_DAYS * 86_400:
                os.remove(path)
        except OSError:
            pass


def build_context(entry_id, entry, kb_rel_path):
    return (
        f"{BANNER} Die Werkzeugausgabe enthält das Symptom von {entry_id}. "
        "Lies den Eintrag, bevor du weiterarbeitest:\n\n"
        f"{entry}\n\n"
        f"(Automatischer PostToolUse-Hook des project-memory-Plugins, Quelle: {kb_rel_path}. "
        "Jeder Eintrag wird pro Session höchstens einmal eingespielt; deaktivieren: "
        "CLAUDE_MEMORY_SYMPTOMS=0 in der Projekt-settings.json.)"
    )


def main():
    if os.environ.get("CLAUDE_MEMORY_SYMPTOMS", "").strip() == "0":
        return
    payload = ss.read_stdin_json()
    raw = tool_output(payload)
    if len(raw) < MIN_OUTPUT_CHARS:
        return  # früher Ausstieg, bevor irgendetwas geparst wird

    project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or "."
    found = ss.find_kb_path(project)
    if not found:
        return
    kb_rel_path, kb_path = found
    with open(kb_path, encoding="utf-8", errors="replace") as f:
        kb_lines = f.read().splitlines()

    norm = normalize(raw)
    if looks_like_learnings(raw, norm):
        return
    phrases = build_phrases(kb_lines)
    if not phrases:
        return

    session = (payload.get("session_id") or "unbekannt")[:8]
    marker = state_path(project, session)
    seen = load_seen(marker)
    match = find_match(norm, phrases, skip=seen)
    if not match:
        return
    _, entry_id = match
    entry = extract_entry(kb_lines, entry_id)
    if not entry:
        return  # Lookup-Zeile ohne passenden Eintrag: nichts einspielen

    seen.add(entry_id)
    save_seen(marker, seen)
    cleanup_state(project)
    # ensure_ascii (Default) hält die Ausgabe unabhängig vom Konsolen-Encoding
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": build_context(entry_id, entry, kb_rel_path),
                }
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # ein kaputter Hook darf die Session niemals stören
    sys.exit(0)
