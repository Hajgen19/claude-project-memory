# Release-Checkliste

Vor jedem Push einer neuen Version diese fünf Schritte durchlaufen – zusammen unter zwei Minuten. Hintergrund: v1.4.0 ging mit einem Ladefehler live (redundante `hooks`-Referenz im Manifest), den genau dieser Selbsttest gefangen hätte.

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

Erwartung: `Skills (3)`, `Hooks (2) Stop, SessionStart`, korrekte Versionsnummer.

## 4. End-to-End: Feuert der Wächter und handelt das Modell?

Frisches Testverzeichnis, `.claude/settings.json` mit `{"env": {"CLAUDE_CONTEXT_WINDOW": "1"}}` (Mini-Fenster erzwingt sofortiges Zünden), dann:

```
cd <testverzeichnis>
claude -p "Sag nur: ok" --model haiku --permission-mode acceptEdits
```

Erwartung danach im Testverzeichnis: `tmp/handoff/` existiert mit `.state-*.json`, `.gitignore` (Inhalt `*`), `README.md` und einem geschriebenen `handoff-*.md`. Fehlt der Handoff, ist die Kette gerissen – wegen des Fail-silent-Designs gibt es keinen anderen Ort, an dem das sichtbar würde.

## 5. Aufräumen und von GitHub neu installieren

Nach dem Push: lokalen Test-Marketplace entfernen, einmal `marketplace add Hajgen19/claude-project-memory` + `install` von GitHub – prüft, dass auch der veröffentlichte Stand lädt (Schritt, der v1.4.0 gerettet hätte).

## Merkregeln

- **Debug-Artefakte sofort zurückbauen.** Jede Zeile, die nur zum Ausprobieren eingebaut wurde, wird direkt nach dem Experiment entfernt oder bewusst zum Feature erklärt – nie stehen gelassen.
- `hooks/hooks.json` ist der Default-Ort und braucht KEINE Referenz im Manifest – ein zusätzliches `"hooks"`-Feld in `plugin.json` erzeugt eine doppelte Registrierung und damit einen Ladefehler.
- Fail-silent heißt: Fehler zeigen sich nur in aktiven Tests, nie im Betrieb. Deshalb ist der Selbsttest Pflicht, nicht Kür.
