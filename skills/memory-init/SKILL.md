---
name: memory-init
description: Dockt das project-memory-Plugin an das aktuelle Projekt an - .gitignore, changelog/, optionale CLAUDE.md-Sektion und Kontextfenster-Konfiguration.
disable-model-invocation: true
---

# memory-init – das Andock-Ritual

Richtet das Projektgedächtnis im **aktuellen Projekt** ein. Einmal pro Projekt ausführen, direkt nach der Plugin-Installation. Jeder Schritt zeigt vor dem Schreiben, was geändert wird – nichts wird ungefragt überschrieben.

## Das Vier-Ebenen-Modell (Kurzfassung für dich als Ausführenden)

| Ablage | Beantwortet | Lebensdauer | Ins Repo? |
|---|---|---|---|
| `changelog/YYYY-MM-DD.md` | Was wurde wann getan? | permanent, append-only | ja |
| `tmp/handoff/` | Wo steht die Arbeit gerade? | eine Session-Grenze | nein |
| `docs/LEARNINGS.md` | Gelöstes Problem – was war die Ursache? | permanent, Nachschlagewerk | nein |
| CLAUDE.md-Sektion | Konventionen, die das Modell proaktiv kennt | permanent | ja |

## Schritt 1: Bestandsaufnahme

Prüfe und berichte kompakt:

1. Existiert `.gitignore` im Projekt-Root? Enthält sie bereits `tmp/` oder `tmp/handoff/` sowie die Learnings-Dateinamen (siehe Schritt 2)?
2. Existiert `changelog/` mit Tagesdateien im Format `YYYY-MM-DD.md`? Gibt es stattdessen (oder zusätzlich) eine **andere Changelog-Konvention** – zentrale `CHANGELOG.md`, anderes Namensformat? Erkannte Bestands-Konvention notieren, sie wird in Schritt 3/4 maßgeblich.
3. Existiert eine `CLAUDE.md` im Projekt-Root? Scanne sie nicht nur auf die Sektion „Projektgedächtnis", sondern auch inhaltlich auf **bestehende eigene Konventionen** zu Changelog, Learnings/Knowledge, Wissensbasis oder Handoffs (Stichworte: changelog, learnings, knowledge, wissensbasis, memory, handoff). Treffer notieren – Schritt 4 muss sich daran ausrichten statt sie zu überschreiben.
4. Existiert `.claude/settings.json` mit einem `env`-Block?
5. Läuft `python --version` (Python 3.x)? Falls das Kommando `python` fehlt, aber `python3 --version` funktioniert: den Hinweis aus dem Abschnitt „Python-Kommando" unten geben.
6. Ist das Projekt ein Git-Repository? (Falls nein: Schritt 2 entfällt inhaltlich, trotzdem anlegen – schadet nicht und schützt, falls später `git init` kommt.)
7. **Wird `tmp/` vom Projekt anderweitig genutzt** (Build-Output, Clean-Tasks wie `rimraf tmp`)? Falls ja, den User warnen: Ein Clean-Task, der `tmp/` leert, löscht auch Übergabedokumente und Wächter-Marker mitten in der Session. Empfehlung dann: Clean-Task auf Unterordner einschränken, die `tmp/handoff/` verschonen.
8. **Hook-Selbsttest:** Liefen seit der Plugin-Installation bereits Sessions mit Antworten in diesem Projekt, muss `tmp/handoff/` eine `.state-*.json` enthalten (der Wächter schreibt sie bei JEDEM Antwort-Ende). Fehlt sie trotz gelaufener Antworten, ist der Wächter beweisbar nicht aktiv – häufigste Ursache: `python`-Kommando fehlt (siehe Abschnitt „Python-Kommando"). Ergebnis im Abschlussbericht nennen. Zusätzlich: **Liegen bereits Dateien unter `tmp/handoff/` und sind welche davon git-getrackt** (`git ls-files tmp/handoff/`)? Das kann passieren, wenn zwischen Plugin-Installation und diesem Init bereits Sessions liefen. Getrackte Handoff-/Marker-Dateien explizit melden; Abhilfe `git rm --cached <datei>` nennen, aber NICHT ungefragt ausführen.

## Schritt 2: .gitignore ergänzen (Pflicht)

Ohne diese Einträge landen Übergabedokumente und die persönliche Wissensdatenbank im Repo des Nutzers – bei Firmenprojekten ein echtes Risiko. Fehlende Einträge ergänzen (vorhandene nicht duplizieren; deckt ein bestehendes `tmp/` den Ordner schon ab, reicht das):

```gitignore
# project-memory-Plugin: Session-Uebergaben bleiben lokal
tmp/handoff/

# project-memory-Plugin: Learnings-Datenbank bleibt beim jeweiligen Nutzer
# (alle Datei-Varianten, die der knowledge-base-entry-Skill unterstuetzt)
LEARNINGS.md
LEARNINGS-CLAUDE-PROJECT.md
KNOWLEDGE.md
KNOWLEDGE-BASE.md
docs/LEARNINGS.md
docs/LEARNINGS-CLAUDE-PROJECT.md
docs/KNOWLEDGE.md
docs/KNOWLEDGE-BASE.md
```

**Vor dem Schreiben:** Prüfe mit `git ls-files`, ob eine der Learnings-Kandidaten-Dateien bereits committet ist. Falls ja, FRAGE den User, ob es sich um eine **geteilte Team-Datei** handelt (z. B. eine gepflegte `docs/KNOWLEDGE.md` als Projektdoku): Team-Dateien werden NICHT ignoriert und NICHT aus dem Repo entfernt – der entsprechende Dateiname wird dann aus dem gitignore-Block gestrichen. **Damit die persönliche Datenbank nicht in der Team-Datei landet, die Entscheidung sofort persistieren:** Die persönliche Learnings-Datei an einem ANDEREN Kandidaten-Pfad mit höherer Priorität anlegen (z. B. `docs/LEARNINGS.md`, Skelett aus der TEMPLATE.md des knowledge-base-entry-Skills) – dann finden Skill und Sessionstart-Hook automatisch die richtige Datei, ohne weitere Konfiguration. Nur für bestätigt **persönliche** Dateien gilt: warnen (ignorieren wirkt nicht auf bereits Getracktes) und `git rm --cached <datei>` als Abhilfe nennen, aber NICHT ungefragt ausführen.

Danach: Diff zeigen, Bestätigung abwarten, dann schreiben.

## Schritt 3: changelog/ anlegen (Pflicht)

Falls noch nicht vorhanden: Ordner `changelog/` anlegen und die heutige Tagesdatei starten:

```markdown
# YYYY-MM-DD – Projektgedächtnis angedockt

## Setup

- project-memory-Plugin eingerichtet (memory-init): .gitignore ergänzt, Changelog-Konvention gestartet[, CLAUDE.md-Sektion ergänzt – je nach Schritt 4].
```

**Hat Schritt 1.2 eine bestehende ANDERE Changelog-Konvention gefunden (z. B. zentrale `CHANGELOG.md` ohne `changelog/`-Ordner): KEIN `changelog/` anlegen.** Die Bestands-Konvention wird übernommen, in der CLAUDE.md-Sektion (Schritt 4) als maßgeblich dokumentiert, und der Setup-Eintrag dieses Andockens landet in der Bestandsdatei. Den User auf die Einschränkung hinweisen: Der 25-%-Datei-Check kennt nur das Standard-Schema, der Zwischenruf kommt dann einmal pro Session, auch wenn schon eingetragen wurde – harmlos, nur redundant.

Andernfalls Standard-Konvention (gilt ab jetzt): eine Datei pro Arbeitstag, `YYYY-MM-DD.md`, H1 `# YYYY-MM-DD – Kurztitel`, weitere Einträge desselben Tags werden angehängt, bestehende Tagesdateien nie rückwirkend verändert. Existiert bereits ein `changelog/`-Ordner mit anderem Format: das vorhandene Format übernehmen und NICHT umbauen – der Kontext-Wächter funktioniert mit jeder Tagesdatei-Konvention, solange der Dateiname `YYYY-MM-DD.md` ist.

## Schritt 4: CLAUDE.md-Sektion anbieten (empfohlen, Opt-in)

Frage den User: *„Soll ich die Projektgedächtnis-Konventionen in deine CLAUDE.md eintragen? Das macht sie dem Modell in jedem Turn bekannt, nicht erst beim Wächter-Zwischenruf."* Bei Zustimmung ans Ende der CLAUDE.md anfügen (bei fehlender CLAUDE.md anbieten, eine minimale mit genau dieser Sektion anzulegen).

**Hat Schritt 1.2/1.3 bestehende eigene Konventionen gefunden** (andere Changelog-Struktur, committete Team-Wissensdatenbank, eigene Learnings-Pfade): NICHT die Standard-Vorlage anbieten, sondern eine **abgeglichene Fassung**, die auf die vorhandenen Pfade und Regeln verweist und nur die Lücken ergänzt. Zwei widersprüchliche Standing-Instructions in einer CLAUDE.md sind schlimmer als gar keine Sektion – im Zweifel den Konflikt benennen und den User entscheiden lassen. Die Standard-Vorlage für den konfliktfreien Fall:

```markdown
## Projektgedächtnis (project-memory-Plugin)

| Ablage | Zweck | Im Repo? |
|---|---|---|
| `changelog/YYYY-MM-DD.md` | Was wurde wann getan – Fakten im Perfekt, pro Arbeitstag eine Datei | ja |
| `tmp/handoff/` | Session-Übergabe, wird beim Sessionstart automatisch eingelesen | nein (gitignored) |
| `docs/LEARNINGS.md` | Gelöste technische Probleme (Symptom → Ursache → Fix), via knowledge-base-entry-Skill | nein (gitignored) |

- **Changelog-Pflicht:** Nach jeder abgeschlossenen Aufgabe eine Zeile in die heutige Tagesdatei. Faustregel: Interessiert es in einem Jahr noch jemanden → Changelog. Interessiert es nur die nächste Session → Handoff.
- **Learning-Kriterien** (alle vier müssen zutreffen): mehr als ein Anlauf; Ursache nicht aus der Fehlermeldung ablesbar; wiederholbar; Lösung nicht trivial. Leitfrage: *Würde ich beim nächsten Mal wieder genauso lange suchen?*
- Ein Kontext-Wächter (Stop-Hook des Plugins) stößt die Sicherung automatisch bei 25/60/85 % Kontextfüllung an; manueller Handoff jederzeit per `/project-memory:handoff`.
```

Diff zeigen, Bestätigung abwarten, dann schreiben. Bestehenden CLAUDE.md-Inhalt niemals verändern, nur anfügen.

## Schritt 5: Wächter konfigurieren (PFLICHT – beide Werte explizit eintragen)

Der Kontext-Wächter liest zwei Werte aus `.claude/settings.json` des Projekts; stehen sie dort nicht, gelten unsichtbare Code-Defaults. **Trage beide IMMER explizit ein** – auch wenn der User die Defaults wählt: Eine sichtbare Zeile ist die einzige Konfiguration, die der User später wiederfindet und ändern kann. (Datei bzw. `env`-Block bei Bedarf anlegen, bestehende Einträge unangetastet lassen.)

1. **`CLAUDE_CONTEXT_WINDOW`** – Frage den User, welches Kontextfenster sein Claude-Modell hat (Standard: `200000`; 1M-Kontext-Modelle: `1000000`). Die Selbstkorrektur (v1.1: Umschalten auf 1M bei Messbeweis) bleibt als Netz, aber der explizite Eintrag stimmt ab der ersten Antwort.
2. **`CLAUDE_MEMORY_STAGES`** – Frage den User, ob er die Standard-Schwellen `25,60,85` behalten oder eigene setzen will (drei Prozentwerte, aufsteigend: Gedächtnis-Check / Erst-Handoff / Handoff-Update). Erkläre dabei die Warnung: Der dritte Wert braucht Puffer vor der Kompaktierung – eine lange Antwort kann 5–10 Punkte springen, bei `95` fiele das letzte Update womöglich aus. Den gewählten (oder Default-)Wert eintragen.

```json
{
  "env": {
    "CLAUDE_CONTEXT_WINDOW": "1000000",
    "CLAUDE_MEMORY_STAGES": "25,60,85"
  }
}
```

## Schritt 6: Abschluss

**Init-Marker schreiben (Pflicht):** Datei `tmp/handoff/.init-done` mit dem heutigen Datum als Inhalt anlegen (Ordner bei Bedarf inkl. `.gitignore` mit `*`). Der Sessionstart-Hook hört damit auf, an das Andocken zu erinnern.

Dann kompakt melden: was geändert wurde (mit Pfaden), was übersprungen wurde und warum – plus drei Pflicht-Informationen: (1) „Der Wächter meldet sich bei [den in Schritt 5 gesetzten Schwellen] % Kontextfüllung mit dem Präfix `[project-memory · Kontext-Wächter]` – das ist dieses Plugin, kein Fehler"; (2) „Beide Stellschrauben (Kontextfenster + Schwellen) stehen in `.claude/settings.json` und können dort jederzeit geändert werden"; (3) die Faustregel: *Interessiert es in einem Jahr noch jemanden → Changelog. Interessiert es nur die nächste Session → Handoff. Gelöstes technisches Problem → Learnings.* Dazu die Werkzeuge, die der User ab jetzt kennt:

- `/project-memory:handoff` – manuelle Session-Übergabe
- `/project-memory:knowledge-base-entry` bzw. „neues Learning" – Wissensdatenbank-Eintrag
- Der Kontext-Wächter läuft automatisch; nach einer Kompaktierung liest der Sessionstart-Hook den letzten Stand selbstständig ein.

## Python-Kommando (Hinweis für Schritt 1.5)

Die Plugin-Hooks rufen `python` auf. Auf macOS/Linux-Systemen, die nur `python3` kennen, bleibt der Wächter sonst still. Abhilfen (eine reicht): Homebrew-Python installieren und dessen `libexec/bin` in den PATH nehmen (liefert `python`), einen Alias/Symlink auf `python3` anlegen, oder pyenv verwenden. Die Session funktioniert auch ohne – nur eben ohne Sicherheitsnetz.
