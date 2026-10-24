# claude-project-memory

Projektgedächtnis für jedes Claude-Code-Projekt – als Plugin, das sich an **bestehende** Projekte andockt, egal ob Code, Content oder Beratung. Es sichert den Arbeitsstand, *bevor* er im Kontextfenster verloren geht, und speist ihn in neue Sessions zurück.

Das Kernproblem, das es löst: Das Kontextfenster ist das begrenzte Arbeitsgedächtnis des Modells. Läuft es voll, ersetzt Claude Code die bisherige Konversation automatisch durch eine Zusammenfassung („Kompaktierung") – dabei gehen Details verloren: Entscheidungen, verworfene Ansätze, der aktuelle Zwischenstand. Dieses Plugin misst den **echten Tokenverbrauch** aus dem Session-Transcript und rettet den Stand rechtzeitig in Dateien, die jede Kompaktierung und jede Session-Grenze überleben.

## Das Vier-Ebenen-Modell

| Ablage | Beantwortet | Lebensdauer | Im Repo? |
|---|---|---|---|
| `changelog/YYYY-MM-DD.md` | Was wurde wann getan? | permanent, append-only | ja |
| `tmp/handoff/` | Wo steht die Arbeit gerade? | eine Session-Grenze | nein (gitignored) |
| `docs/LEARNINGS.md` * | Dieses Symptom gab es schon – was war die Ursache? | permanent, Nachschlagewerk | nein (gitignored) |
| CLAUDE.md-Sektion (optional) | Konventionen und Betriebsregeln, die das Modell proaktiv kennt | permanent | ja |

\* oder eine der anderen Pfad-Varianten, die der `knowledge-base-entry`-Skill erkennt (`LEARNINGS-CLAUDE-PROJECT.md`, `LEARNINGS.md`, `KNOWLEDGE.md`, `KNOWLEDGE-BASE.md`, in `docs/` und im Root).

Faustregel: **Interessiert es in einem Jahr noch jemanden → Changelog. Interessiert es nur die nächste Session → Handoff. Ist es ein gelöstes technisches Problem → Learnings. Ist es eine dauerhafte Regel → CLAUDE.md.**

Zur letzten Regel eine Konvention, die sich im Einsatz als nötig erwiesen hat: **Die Übergabe trägt Zustand, keine Regeln.** Dauerhafte Imperative („nie `git add -A`", „Builder-Testdateien nie committen") gehören in die projektweite `CLAUDE.md` unter `## Betriebsregeln`, wo sie in jedem Turn gelten – in einem Handoff verfallen sie an der nächsten Session-Grenze oder werden so lange mitgeschleppt, bis das Dokument aus Regeln statt aus Stand besteht. Das Plugin erzwingt hier nichts Neues: `memory-init` legt die Sektion in der CLAUDE.md-Vorlage an, der `handoff`-Skill kennt die Trennung, und der `doctor`-Skill warnt, wenn eine Übergabe mehr als 15 Listenzeilen mit „nie", „niemals" oder „immer" enthält.

## Wie es arbeitet

Die drei Automatiken sind **Hooks** – kleine Python-Skripte, die Claude Code selbst bei bestimmten Ereignissen ausführt: eins nach jeder Antwort (Stop), eins beim Sessionstart, eins nach jeder Werkzeugausgabe (PostToolUse).

**Kontext-Wächter** (Stop-Hook): Misst nach jeder Antwort die tatsächliche Kontextfüllung (input + cache-read + cache-creation aus dem Transcript – gemessen, nicht geschätzt) und stößt gestuft an, je einmal pro Session und Stufe:

| Schwelle | Auftrag |
|---|---|
| **25 %** | Learning-Frühprüfung – immer; dazu der Changelog-Check, falls die heutige Tagesdatei in dieser Session noch unberührt ist |
| **60 %** | Übergabedokument schreiben + Changelog nachziehen + Learnings prüfen (zweites Netz) |
| **85 %** | Übergabedokument auf den letzten Stand bringen + letzte Learnings-Prüfung – kurz bevor kompaktiert wird |

**Wer führt die Aufträge aus?** Der Wächter unterbricht kurz das Antwort-Ende und gibt Claude den Auftrag als Anweisung mit – Claude schreibt Changelog und Übergabedokument dann selbst, für dich sichtbar im Chat. Du musst nichts tun, kannst aber jederzeit eingreifen. Ein Zwischenruf sieht so aus:

> *[project-memory · Kontext-Wächter] Diese Session hat 62 % des Kontextfensters erreicht (124.000 von 200.000 Tokens). Sichere jetzt den Stand, bevor du weiterarbeitest: 1. HANDOFF: …*

Nach einer Kompaktierung sind alle Stufen automatisch wieder scharf (neuer Zyklus, erkannt am compact-Event und zusätzlich am Token-Einbruch).

**Warum unterbricht der Wächter, statt sanft zu erinnern?** Bewusste Design-Entscheidung: Der Zwischenruf nutzt den Block-Mechanismus des Stop-Hooks, weil nur er einen *sofortigen* Arbeitsschritt erzwingt. Eine sanfte Kontext-Notiz würde erst beim nächsten User-Prompt wirken – der vielleicht nie kommt (Session einfach geschlossen) oder erst nach der Kompaktierung, also genau zu spät. Ein Wächter, der höflich wartet, bis jemand wieder etwas sagt, ist keiner.

**Sessionstart-Hook**: Lädt beim Start, bei `resume`/`fork`, nach `/clear` und nach jeder Kompaktierung das jüngste Übergabedokument (nach Kompaktierung bevorzugt das der eigenen Session – parallele Sessions im selben Projekt kommen sich nicht in die Quere) und die Symptom-Kurzübersicht der Learnings-Datenbank in den frischen Kontext. Die neue Session weiß sofort, wo die letzte aufgehört hat und welche Probleme schon gelöst wurden. Wurde `memory-init` im Projekt noch nie ausgeführt, erinnert der Hook außerdem einmal pro Session daran.

**Symptom-Treffer** (PostToolUse-Hook, v1.6): Die Lookup-Tabelle beim Sessionstart hilft nur, wenn das Modell beim passenden Symptom *selbst* nachschlägt – und genau das unterbleibt in der Praxis, obwohl der Fehlertext wörtlich durch die Werkzeugausgabe läuft (in zwei Monaten Einsatz wurde dieselbe dokumentierte Falle zweimal betreten, der Eintrag stand seit Wochen in der Tabelle). Dieser Hook übernimmt das Nachschlagen: Nach jeder Ausgabe von `Bash`, `Read`, `Grep` und `Agent` prüft er, ob ein in **Backticks** gesetzter Fehlertext aus der Spalte „Was du siehst" wörtlich darin vorkommt (Groß-/Kleinschreibung und Mehrfach-Leerzeichen egal) – und spielt bei Treffer den **vollständigen Eintrag** ein, bevor das Modell weiterarbeitet:

> *[project-memory · Symptom-Treffer] Die Werkzeugausgabe enthält das Symptom von E-011. Lies den Eintrag, bevor du weiterarbeitest:*
>
> *## E-011 — Builder-Testdateien*
> *\*\*Symptom:\*\* `Existing tests are immutable` …*
> *\*\*Root Cause:\*\* Vom Menschen committete Testdateien sind für den Builder unveränderlich. …*

Spielregeln, damit das kein Rauschen wird: höchstens ein Eintrag je Werkzeugaufruf (der längste Treffer gewinnt), jeder Eintrag je Session nur einmal (Marker `tmp/handoff/.symptoms-<session>.json`), und wenn die Ausgabe selbst Learnings enthält (ein `## E-nnn`-Header, die Lookup-Kopfzeile, der eigene Banner – also etwa `cat LEARNINGS.md`), schweigt der Hook. Nur Backtick-Inhalte zählen als Suchphrase: Beschreibender Text wie „Deploy kopiert alte Version" taucht nie wörtlich in einer Ausgabe auf, hätte aber Fehlalarmpotenzial. **Wer einen Eintrag automatisch finden lassen will, trägt sein Symptom wörtlich und in Backticks in die Lookup-Tabelle ein** – der `doctor`-Skill zeigt, wie viele Zeilen das bereits erfüllen. Kein Embedding, kein externer Dienst, nur Substring-Suche in der Standardbibliothek: Der Abgleich dauert bei 500 Einträgen unter 10 ms; der eigentliche Preis ist der Python-Start je Werkzeugaufruf (≈ 30–50 ms), bewusst in Kauf genommen. Abschalten jederzeit per `"CLAUDE_MEMORY_SYMPTOMS": "0"` im `env`-Block der Projekt-`settings.json`. Am Dateiformat ändert sich nichts – bestehende Datenbanken funktionieren ohne Migration.

**Skills:**

| Skill | Aufruf | Zweck |
|---|---|---|
| `memory-init` | `/project-memory:memory-init` | Das Andock-Ritual: `.gitignore` absichern, `changelog/` starten, Wächter-Konfiguration eintragen, optional CLAUDE.md-Sektion. Einmal pro Projekt. |
| `doctor` | `/project-memory:doctor` | Funktions-Diagnose auf Zuruf: prüft Python, Hook-Registrierung, Marker, Schreibrechte, Konfiguration, die komplette Hook-Kette, Betriebsregeln in der Übergabe und die Reichweite des Symptom-Hooks. Die Antwort auf das Fail-silent-Design – jederzeit, ändert nichts. |
| `handoff` | `/project-memory:handoff` | Manuelle Session-Übergabe nach `tmp/handoff/`, jederzeit. |
| `knowledge-base-entry` | `/project-memory:knowledge-base-entry` oder „neues Learning" | Strukturierter Eintrag in die Wissensdatenbank (Symptom → Root Cause → Fix → Tags), formaterhaltend, mit Volltext-Suche per Symptom-Wortlaut. |

## ⚠️ Voraussetzung: Python 3 – ohne läuft hier NICHTS

Beide Hooks sind Python-Skripte und rufen `python` auf. **Ohne erreichbares `python`-Kommando ist das Plugin vollständig stumm – empirisch verifiziert: kein Fehler, keine Warnung, keine Dateien.** Es sieht installiert aus (`/plugin list` zeigt es), aber Wächter und Sessionstart-Einspeisung existieren praktisch nicht. Du merkst es erst, wenn nach einer Kompaktierung der Stand fehlt – also genau im Schadensfall.

**Deshalb VOR der Installation einmal prüfen:**

```
python --version
```

Kommt `Python 3.x` zurück: alles gut. Kommt ein Fehler (häufig auf macOS/Linux, wo nur `python3` existiert): Alias oder Symlink `python` → `python3` anlegen, oder Homebrew-Python nutzen (liefert `python` mit). Der Selbsttest in `memory-init` prüft das später ebenfalls – aber der Ein-Sekunden-Check jetzt erspart dir einen stillen Blindflug.

## Installation

```
/plugin marketplace add Hajgen19/claude-project-memory
/plugin install project-memory@claude-project-memory
```

**Wichtig zu wissen:** Ab diesem Moment ist der Wächter in **jedem** deiner Projekte aktiv – er misst still mit und legt beim ersten Antwort-Ende den Ordner `tmp/handoff/` an (mit einer kleinen Statusdatei, dem „Marker", und einer eigenen `.gitignore`, die den Ordner komplett vor Commits schützt). Mehr passiert ohne dein Zutun nicht.

Danach im jeweiligen Projekt einmalig andocken:

```
/project-memory:memory-init
```

Der Init-Schritt ist wichtig: Er trägt die Learnings-Dateinamen in die `.gitignore` ein (sonst landet deine persönliche Wissensdatenbank im Repo), startet die Changelog-Konvention, prüft, ob die Hooks wirklich laufen, **schreibt Kontextfenster und Wächter-Schwellen explizit in die `.claude/settings.json` des Projekts** (damit du beide Stellschrauben siehst und jederzeit ändern kannst, statt auf unsichtbaren Defaults zu sitzen) und bietet an, die Konventionen in der CLAUDE.md zu verankern. Jeder Schritt zeigt vor dem Schreiben ein Diff – nichts wird ungefragt geändert. Vergisst du den Schritt, erinnert dich das Plugin beim nächsten Sessionstart daran.

## Voraussetzungen & Konfiguration

- **Python 3.x** – siehe den Voraussetzungs-Block oben: ohne `python`-Kommando ist das Plugin komplett stumm (nur Standardbibliothek, keine pip-Pakete nötig). Der Selbsttest in `memory-init` deckt einen stillen Ausfall nachträglich auf.
- **Kontextfenster – mit Auto-Erkennung (v1.1):** Der Wächter rechnet gegen `CLAUDE_CONTEXT_WINDOW` (Default `200000`; alle Snippets unten gehören in die Datei `.claude/settings.json` im Projekt) und korrigiert sich selbst: Übersteigen die *gemessenen* Tokens das angenommene Fenster, ist das Fenster beweisbar größer – der Wächter schaltet auf `1000000` um und merkt sich das für den Rest der Session (überlebt auch Kompaktierungen). Trägt die Modell-ID im Transcript eine `[1m]`-Kennung, greift die Umschaltung sofort. Der explizite Eintrag in der Projekt-`settings.json` bleibt trotzdem empfohlen (macht `memory-init` auf Wunsch), denn er stimmt von der ersten Antwort an – die Beweis-Erkennung greift naturgemäß erst, sobald 200k überschritten sind; bis dahin kämen die Zwischenrufe in einer 1M-Session zu früh:

```json
{
  "env": {
    "CLAUDE_CONTEXT_WINDOW": "1000000"
  }
}
```

- **Schwellen anpassen (v1.2):** Die drei Stufen behalten ihre feste Bedeutung (1 = Gedächtnis-Check, 2 = Erst-Handoff, 3 = Handoff-Update), aber ihre Prozentwerte sind über `CLAUDE_MEMORY_STAGES` frei wählbar – drei kommagetrennte Werte, aufsteigend:

```json
{
  "env": {
    "CLAUDE_MEMORY_STAGES": "20,50,80"
  }
}
```

Ungültige Angaben (falsche Anzahl, Werte außerhalb 0–100, doppelte Werte) fallen still auf die Defaults `25,60,85` zurück. Wer Stufe 3 näher an die Kompaktierung legt (z. B. `90`), riskiert, dass eine einzige lange Antwort darüber hinwegträgt und das letzte Update ausfällt – die 85 sind bewusst als Puffer gewählt.

- **Symptom-Treffer abschalten (v1.6):** `"CLAUDE_MEMORY_SYMPTOMS": "0"` im selben `env`-Block. Jeder andere Wert (oder keiner) lässt den Hook laufen.

- Die Hooks enden in **jedem** Fehlerfall mit Exit 0 – ein kaputter Wächter darf niemals die Session stören.

## Grenzen, ehrlich benannt

- **`memory-init` direkt nach der Installation ausführen.** Der Handoff-Ordner schützt sich zwar selbst vor Commits, aber die Learnings-Absicherung und die Konventions-Abstimmung kommen erst mit dem Init. Der Sessionstart-Reminder fängt Vergessliche auf.
- **Projekte, deren Build `tmp/` leert** (Clean-Tasks): Ein solcher Task löscht auch Übergabedokumente und Wächter-Marker. `memory-init` warnt in dem Fall; die Abhilfe ist, den Clean-Task `tmp/handoff/` verschonen zu lassen.
- **Sessions, die unter 25 % bleiben,** bekommen keinen automatischen Anstoß – dort trägt die Konvention aus der CLAUDE.md-Sektion (oder ein manuelles `/project-memory:handoff`).
- **Eigene Changelog-Konventionen werden respektiert:** Der Wächter verweist auf die Konvention der Projekt-CLAUDE.md und legt keine zweite Struktur an. Nutzt dein Projekt aber ein anderes Changelog-Format als `changelog/YYYY-MM-DD.md`, kann die 25-%-Stufe nicht erkennen, ob du schon eingetragen hast – sie erinnert dann einmal pro Session, auch wenn alles erledigt ist. Harmlos, nur redundant.
- **Der Symptom-Treffer findet nur, was wörtlich in Backticks steht.** Lookup-Zeilen mit rein beschreibendem Text sind für ihn unsichtbar – gewollt, denn Paraphrasen tauchen nie wörtlich in Ausgaben auf, würden aber Fehlalarme produzieren. Und er feuert nur auf Ausgaben, die durch `Bash`, `Read`, `Grep` oder `Agent` kommen; ein Symptom, das nur der User in den Chat schreibt, erreicht ihn nicht – dafür bleibt die Lookup-Tabelle vom Sessionstart zuständig.

## Was es bewusst NICHT tut

- Es ändert nie ungefragt **bestehende** Projektdateien (`CLAUDE.md`, deine `.gitignore`, deinen Code) – das macht nur `memory-init`, mit Diff und Bestätigung. Seine **eigenen** Ablagen (`tmp/handoff/` samt Marker; Changelog- und Handoff-Einträge, die Claude sichtbar im Chat schreibt) legt es dagegen automatisch an.
- Es sendet nichts nach außen. Alle Daten bleiben im Projektordner.
- Die Learnings-Datenbank wandert nie ins Repo – sie gehört dem jeweiligen Nutzer.
- Es ersetzt keine Projektdokumentation. Handoffs sind bewusst flüchtig; was dauerhaft zählt, gehört ins Changelog oder in die Doku.

## Credits

Der `handoff`-Skill basiert auf [Matt Pococks `handoff`](https://github.com/mattpocock/skills/tree/main/skills/productivity/handoff) – erweitert um den projekt-lokalen Speicherort, das automatische Wiedereinlesen per Sessionstart-Hook und die messbasierte Auslösung durch den Kontext-Wächter. Danke für die Grundidee, die dieses Plugin zu Ende denkt: Eine Session-Übergabe ist erst dann ein Gedächtnis, wenn niemand daran denken muss.

## Deaktivieren / Entfernen

```
/plugin disable project-memory@claude-project-memory   # temporär
/plugin uninstall project-memory@claude-project-memory # ganz
```

Die im Projekt angelegten Dateien (`changelog/`, `tmp/handoff/`, Learnings, CLAUDE.md-Sektion) bleiben erhalten – es sind deine Daten.
