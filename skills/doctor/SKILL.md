---
name: doctor
description: Diagnose des project-memory-Plugins im aktuellen Projekt - prueft Python, Hook-Registrierung, Marker, Schreibrechte, Konfiguration, Transcript-Lesbarkeit, Betriebsregeln in der Uebergabe und die Reichweite des Symptom-Hooks. Die Antwort auf das Fail-silent-Design.
disable-model-invocation: true
---

# doctor – Funktions-Diagnose auf Zuruf

Das Plugin schweigt bei Fehlern absichtlich (eine Session darf nie gestört werden). Die Kehrseite: Ein toter Wächter ist vom Normalzustand nicht zu unterscheiden. Dieser Skill ist die Antwort – er prüft die komplette Kette aktiv und gibt einen klaren Befund. Jederzeit aufrufbar, ändert nichts am Projekt (außer einer sofort wieder gelöschten Schreibtest-Datei).

Führe alle Prüfungen aus und präsentiere am Ende die Befund-Tabelle. Das Plugin-Verzeichnis kennst du aus dem „Base directory"-Hinweis dieses Skill-Aufrufs (zwei Ebenen über `skills/doctor/` liegt der Plugin-Root mit `hooks/`).

## Prüfung 1: Python erreichbar?

`python --version` ausführen. Erwartung: `Python 3.x`. Bei Fehler: **Hauptursache für einen komplett stummen Wächter** – Abhilfen siehe README (Alias/Symlink `python` → `python3`, Homebrew-Python).

## Prüfung 2: Hooks registriert?

`claude plugin details project-memory@claude-project-memory` ausführen. Erwartung im Component inventory: `Hooks (3) Stop, SessionStart, PostToolUse` und `Skills (4)`. Fehlen die Hooks: Plugin neu installieren (`/plugin uninstall` + `/plugin install`), danach Session neu starten.

## Prüfung 3: Läuft der Wächter tatsächlich? (Marker-Beweis)

Existiert `tmp/handoff/` mit mindestens einer `.state-*.json`? Der Wächter schreibt sie bei jedem Antwort-Ende mit lesbarem usage-Block im Transcript (bei Transcript-Format-Problemen entsteht KEIN Marker – dann direkt zu Prüfung 6) – liefen in diesem Projekt seit der Plugin-Installation bereits Sessions mit Antworten und es gibt KEINE Marker-Datei, ist der Wächter beweisbar tot (dann sind Prüfung 1/2/6 die Verdächtigen). Frisch installiert und noch keine neue Session gelaufen: kein Befund, nur Hinweis.

## Prüfung 4: Schreibrechte

Eine Testdatei `tmp/handoff/.doctor-write-test` anlegen und sofort wieder löschen. Schlägt das Anlegen fehl: Der Wächter kann weder Marker noch Handoffs schreiben (Readonly-Checkout, Rechteproblem) – Projektpfad und Berechtigungen prüfen.

## Prüfung 5: Konfiguration plausibel?

`.claude/settings.json` lesen: Sind `CLAUDE_CONTEXT_WINDOW` und `CLAUDE_MEMORY_STAGES` gesetzt (Pflicht seit memory-init v1.4.0)? Passt das Fenster zum genutzten Modell (200000 vs. 1000000)? Sind die Stages drei aufsteigende Werte zwischen 0 und 100? Fehlende Werte: `memory-init` (erneut) ausführen oder manuell eintragen.

## Prüfung 6: Funktioniert die komplette Hook-Kette? (Lebendtest)

Den Wächter einmal direkt mit synthetischem Payload aufrufen. **Wichtig: Den Payload NICHT per `echo` inline übergeben** – Shells zerlegen die JSON-Klammern und Anführungszeichen (Bash: Brace Expansion und Quote-Stripping; PowerShell: eigenes Parsing). Stattdessen: Payload als Datei schreiben, dann pipen.

1. Mit dem Write-Tool eine Datei `tmp/handoff/.doctor-payload.json` anlegen – Inhalt (Pfade einsetzen; `<PLUGIN_ROOT>` aus dem Base-directory-Hinweis, `<TRANSCRIPT>` ein existierendes Transcript, z. B. das jüngste unter `~/.claude/projects/<projekt-slug>/*.jsonl`):

```json
{"session_id":"doctor01","transcript_path":"<TRANSCRIPT>","cwd":"<PROJEKT>","hook_event_name":"Stop","stop_hook_active":false}
```

2. Die Datei an den Hook pipen – Bash/sh: `python "<PLUGIN_ROOT>/hooks/context_guard.py" < tmp/handoff/.doctor-payload.json` · PowerShell: `Get-Content tmp/handoff/.doctor-payload.json | python "<PLUGIN_ROOT>/hooks/context_guard.py"`

Erwartung: Exit 0, und danach existiert `tmp/handoff/.state-doctor01.json` (Payload- und State-Datei anschließend wieder löschen). Entsteht der Marker nicht, obwohl Python läuft: Transcript-Format-Problem (Claude-Code-Update könnte die JSONL-Struktur geändert haben) – das ist die bekannte Wartungs-Hypothek, Issue im Plugin-Repo aufmachen.

## Prüfung 7: Betriebsregeln in der Übergabe & Reichweite des Symptom-Hooks

Einen Befehl ausführen, Ausgabe übernehmen – Bash/sh: `python "<PLUGIN_ROOT>/hooks/doctor_checks.py" "<PROJEKT>"` · PowerShell identisch. Er liefert zwei Zeilen:

1. **Betriebsregeln:** Zählt im jüngsten Übergabedokument die Listenzeilen (`- ` / `* `), die mit „nie", „niemals" oder „immer" beginnen (optional „nicht" + Verb). Mehr als 15 davon → ✗ mit Hinweis: Das Dokument trägt dauerhafte Regeln statt Zustand; die gehören in die projektweite `CLAUDE.md` unter `## Betriebsregeln` (Konvention siehe README und `memory-init`), die Übergabe nur den Stand. Dem User anbieten, die Regelzeilen in die CLAUDE.md zu verschieben – mit Diff, nicht ungefragt. „nur" und „keine" zählen bewusst nicht (Zustandssätze wie „Keine Änderungen heute" wären Fehlalarme).
2. **Symptom-Hook:** Wie viele Zeilen der Lookup-Tabelle eine Backtick-Suchphrase tragen. Nur diese Zeilen kann der Symptom-Treffer-Hook (PostToolUse) überhaupt erkennen – Zeilen mit rein beschreibendem Text sind für ihn unsichtbar. Liegt die Abdeckung deutlich unter 100 %, dem User vorschlagen, bei den betroffenen Zeilen den wörtlichen Fehlertext in Backticks nachzutragen.

## Prüfung 8: Bestandsübersicht (Info, kein Fehler)

Kurz auflisten: Anzahl Handoffs in `tmp/handoff/`, `.init-done` vorhanden?, Learnings-Datenbank gefunden (welcher Kandidaten-Pfad, wie viele Einträge)?, heutige Changelog-Datei vorhanden?, Symptom-Marker `.symptoms-*.json` vorhanden (zeigt, dass der Symptom-Hook in dieser oder einer früheren Session mindestens einmal getroffen hat – ohne Treffer entsteht keiner, das ist kein Fehler)?

## Befund

Tabelle: Prüfung | Ergebnis (✓ / ✗ / –) | Abhilfe bei ✗. Danach EIN Satz Gesamtdiagnose („Wächter voll funktionsfähig" oder „Wächter inaktiv, Ursache: …"). Bei allem ✓: erwähnen, dass der nächste automatische Beweis die `.state`-Datei nach der nächsten Antwort ist.
