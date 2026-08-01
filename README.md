# claude-project-memory

Projektgedächtnis für jedes Claude-Code-Projekt – als Plugin, das sich an **bestehende** Projekte andockt, egal ob Code, Content oder Beratung. Es sichert den Arbeitsstand, *bevor* er im Kontextfenster verloren geht, und speist ihn in neue Sessions zurück.

Das Kernproblem, das es löst: Wenn eine Claude-Code-Session lang wird, kompaktiert die CLI den Kontext – verlustbehaftet. Entscheidungen, verworfene Ansätze und der aktuelle Zwischenstand sind danach weg. Dieses Plugin misst den **echten Tokenverbrauch** aus dem Session-Transcript und rettet den Stand rechtzeitig in Dateien, die jede Kompaktierung und jede Session-Grenze überleben.

## Das Vier-Ebenen-Modell

| Ablage | Beantwortet | Lebensdauer | Im Repo? |
|---|---|---|---|
| `changelog/YYYY-MM-DD.md` | Was wurde wann getan? | permanent, append-only | ja |
| `tmp/handoff/` | Wo steht die Arbeit gerade? | eine Session-Grenze | nein (gitignored) |
| `docs/LEARNINGS.md` | Dieses Symptom gab es schon – was war die Ursache? | permanent, Nachschlagewerk | nein (gitignored) |
| CLAUDE.md-Sektion (optional) | Konventionen, die das Modell proaktiv kennt | permanent | ja |

Faustregel: **Interessiert es in einem Jahr noch jemanden → Changelog. Interessiert es nur die nächste Session → Handoff. Ist es ein gelöstes technisches Problem → Learnings.**

## Wie es arbeitet

**Kontext-Wächter** (Stop-Hook): Misst nach jeder Antwort die tatsächliche Kontextfüllung (input + cache-read + cache-creation aus dem Transcript – gemessen, nicht geschätzt) und stößt gestuft an, je einmal pro Session und Stufe:

| Schwelle | Auftrag |
|---|---|
| **25 %** | Changelog-Check + Learning-Frühprüfung – nur falls die heutige Tagesdatei in dieser Session noch unberührt ist |
| **60 %** | Übergabedokument schreiben + Changelog nachziehen + Learnings prüfen (zweites Netz) |
| **85 %** | Übergabedokument auf den letzten Stand bringen – kurz bevor kompaktiert wird |

Nach einer Kompaktierung sind alle Stufen automatisch wieder scharf (neuer Zyklus, erkannt am compact-Event und zusätzlich am Token-Einbruch).

**Sessionstart-Hook**: Lädt beim Start, nach `/clear` und nach jeder Kompaktierung das jüngste Übergabedokument (nach Kompaktierung bevorzugt das der eigenen Session – parallele Sessions im selben Projekt kommen sich nicht in die Quere) und den Schnell-Lookup-Index der Learnings-Datenbank in den frischen Kontext. Die neue Session weiß sofort, wo die letzte aufgehört hat und welche Probleme schon gelöst wurden.

**Skills:**

| Skill | Aufruf | Zweck |
|---|---|---|
| `memory-init` | `/project-memory:memory-init` | Das Andock-Ritual: `.gitignore` absichern, `changelog/` starten, optional CLAUDE.md-Sektion + Kontextfenster-Konfiguration. Einmal pro Projekt. |
| `handoff` | `/project-memory:handoff` | Manuelle Session-Übergabe nach `tmp/handoff/`, jederzeit. |
| `knowledge-base-entry` | `/project-memory:knowledge-base-entry` oder „neues Learning" | Strukturierter Eintrag in die Wissensdatenbank (Symptom → Root Cause → Fix → Tags), formaterhaltend, mit Volltext-Suche per Symptom-Wortlaut. |

## Installation

```
/plugin marketplace add Hajgen19/claude-project-memory
/plugin install project-memory@claude-project-memory
```

Danach im jeweiligen Projekt einmalig andocken:

```
/project-memory:memory-init
```

Der Init-Schritt ist wichtig: Er trägt `tmp/handoff/` und die Learnings-Dateinamen in die `.gitignore` ein (sonst landen Übergabedokumente und persönliche Notizen im Repo), startet die Changelog-Konvention und bietet an, die Konventionen in der CLAUDE.md zu verankern. Jeder Schritt zeigt vor dem Schreiben ein Diff – nichts wird ungefragt geändert.

## Voraussetzungen & Konfiguration

- **Python 3.x** – die beiden Hooks sind Python-Skripte (nur Standardbibliothek). Sie rufen `python` auf; auf macOS/Linux-Systemen, die nur `python3` kennen, hilft der Hinweis-Abschnitt in `memory-init` (Alias/Homebrew). Fehlt Python, bleibt das Plugin still – die Session funktioniert normal, nur ohne Sicherheitsnetz.
- **Kontextfenster – mit Auto-Erkennung (v1.1):** Der Wächter rechnet gegen `CLAUDE_CONTEXT_WINDOW` (Default `200000`) und korrigiert sich selbst: Übersteigen die *gemessenen* Tokens das angenommene Fenster, ist das Fenster beweisbar größer – der Wächter schaltet auf `1000000` um und merkt sich das für den Rest der Session (überlebt auch Kompaktierungen). Trägt die Modell-ID im Transcript eine `[1m]`-Kennung, greift die Umschaltung sofort. Der explizite Eintrag in der Projekt-`settings.json` bleibt trotzdem empfohlen (macht `memory-init` auf Wunsch), denn er stimmt von der ersten Antwort an – die Beweis-Erkennung greift naturgemäß erst, sobald 200k überschritten sind; bis dahin kämen die Zwischenrufe in einer 1M-Session zu früh:

```json
{
  "env": {
    "CLAUDE_CONTEXT_WINDOW": "1000000"
  }
}
```

- Die Hooks enden in **jedem** Fehlerfall mit Exit 0 – ein kaputter Wächter darf niemals die Session stören.

## Grenzen, ehrlich benannt

- **`memory-init` direkt nach der Installation ausführen.** Der Wächter ist ab der Installation in jedem Projekt aktiv; der Handoff-Ordner schützt sich zwar selbst vor Commits (er legt eine eigene `.gitignore` mit `*` an), aber die Learnings-Absicherung und die Konventions-Abstimmung kommen erst mit dem Init.
- **Projekte, deren Build `tmp/` leert** (Clean-Tasks): Ein solcher Task löscht auch Übergabedokumente und Wächter-Marker. `memory-init` warnt in dem Fall; die Abhilfe ist, den Clean-Task `tmp/handoff/` verschonen zu lassen.
- **Sessions, die unter 25 % bleiben,** bekommen keinen automatischen Anstoß – dort trägt die Konvention aus der CLAUDE.md-Sektion (oder ein manuelles `/project-memory:handoff`).
- **Eigene Changelog-Konventionen werden respektiert:** Der Wächter verweist auf die Konvention der Projekt-CLAUDE.md und legt keine zweite Struktur an; der Datei-Check der 25-%-Stufe kennt allerdings nur das Standard-Schema `changelog/YYYY-MM-DD.md` – bei abweichender Konvention kommt der Zwischenruf daher maximal einmal pro Session, auch wenn schon eingetragen wurde.

## Was es bewusst NICHT tut

- Es schreibt nie ungefragt in `CLAUDE.md`, `.gitignore` oder andere Projektdateien – das macht nur `memory-init`, mit Diff und Bestätigung.
- Es sendet nichts nach außen. Alle Daten bleiben im Projektordner.
- Die Learnings-Datenbank wandert nie ins Repo – sie gehört dem jeweiligen Nutzer.
- Es ersetzt keine Projektdokumentation. Handoffs sind bewusst flüchtig; was dauerhaft zählt, gehört ins Changelog oder in die Doku.

## Deaktivieren / Entfernen

```
/plugin disable project-memory@claude-project-memory   # temporär
/plugin uninstall project-memory@claude-project-memory # ganz
```

Die im Projekt angelegten Dateien (`changelog/`, `tmp/handoff/`, Learnings, CLAUDE.md-Sektion) bleiben erhalten – es sind deine Daten.
