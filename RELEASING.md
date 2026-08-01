# Release-Checkliste

Vor jedem Push einer neuen Version diese Schritte durchlaufen – zusammen unter drei Minuten. Hintergrund: v1.4.0 ging mit einem Ladefehler live (redundante `hooks`-Referenz im Manifest), den genau dieser Selbsttest gefangen hätte.

## 0. Manifest validieren + Test-Suite

```
claude plugin validate .
python -m unittest discover tests
```

Beides muss grün sein, bevor irgendetwas anderes passiert. (Die Suite läuft zusätzlich per GitHub Actions auf Windows/macOS/Linux – lokale Ausführung fängt Fehler trotzdem früher.)

## 1. Syntax

```
python -m py_compile hooks/context_guard.py hooks/session_start.py
```

## 2. Frisch installieren (der echte Nutzer-Weg, nicht `--plugin-dir`)

```
claude plugin uninstall project-memory@claude-project-memory
claude plugin marketplace remove claude-project-memory
claude plugin marketplace add <pfad-zum-lokalen-repo-clone>
claude plugin install project-memory@claude-project-memory
```

**Auf Ladefehler in der Ausgabe achten** – ein Plugin, das nicht lädt, meldet sich hier, nirgendwo sonst.

## 3. Inventar prüfen

```
claude plugin details project-memory@claude-project-memory
```

Erwartung: `Skills (4) doctor, handoff, knowledge-base-entry, memory-init`, `Hooks (2) Stop, SessionStart`, korrekte Versionsnummer.

## 4. End-to-End: Feuert der Wächter und handelt das Modell?

Frisches Testverzeichnis, `.claude/settings.json` mit `{"env": {"CLAUDE_MEMORY_STAGES": "1,2,3"}}` (Mini-Schwellen erzwingen sofortiges Zünden – NICHT `CLAUDE_CONTEXT_WINDOW: 1` verwenden: Das korrigiert die Beweis-Auto-Erkennung seit v1.1 selbst weg und nichts zündet), dann:

```
cd <testverzeichnis>
claude -p "Wir bauen ein Tool namens Alpha. Entscheidung: Python statt Node, wegen der Stdlib. Naechster Schritt: CLI-Skelett. Bestaetige kurz." --model haiku --permission-mode acceptEdits
```

(Der Prompt braucht Mini-Substanz – bei einem reinen „Sag ok" urteilt das Modell korrekt, dass es nichts zu sichern gibt, und schreibt keinen Handoff.)

**Erfolgskriterium (beides muss zutreffen):** (a) `tmp/handoff/` existiert mit `.state-*.json`, `.gitignore` (Inhalt `*`) und `README.md` – beweist, dass der Hook läuft und schreibt. (b) Die Modell-Antwort verarbeitet den Sicherungsauftrag erkennbar (erwähnt den Zwischenruf/das Plugin oder schreibt ein `handoff-*.md`) – beweist, dass der Block ankommt. Ob tatsächlich eine Handoff-Datei entsteht, entscheidet das Modell nach Substanz der Test-Session; bei Ein-Prompt-Sessions lehnt es zu Recht ab. Fehlt dagegen schon der Marker, ist die Kette gerissen – wegen des Fail-silent-Designs gibt es keinen anderen Ort, an dem das sichtbar würde.

## 5. Aufräumen und von GitHub neu installieren

Nach dem Push: lokalen Test-Marketplace entfernen, einmal `marketplace add Hajgen19/claude-project-memory` + `install` von GitHub – prüft, dass auch der veröffentlichte Stand lädt (Schritt, der v1.4.0 gerettet hätte).

## Merkregeln

- **Debug-Artefakte sofort zurückbauen.** Jede Zeile, die nur zum Ausprobieren eingebaut wurde, wird direkt nach dem Experiment entfernt oder bewusst zum Feature erklärt – nie stehen gelassen.
- `hooks/hooks.json` ist der Default-Ort und braucht KEINE Referenz im Manifest – ein zusätzliches `"hooks"`-Feld in `plugin.json` erzeugt eine doppelte Registrierung und damit einen Ladefehler.
- Fail-silent heißt: Fehler zeigen sich nur in aktiven Tests, nie im Betrieb. Deshalb ist der Selbsttest Pflicht, nicht Kür.
