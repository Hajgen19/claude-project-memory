---
name: knowledge-base-entry
description: Fügt strukturierte Einträge in eine projektspezifische Wissensdatenbank hinzu. Sucht automatisch nach existierenden LEARNINGS.md, KNOWLEDGE.md oder LEARNINGS-CLAUDE-PROJECT.md Dateien im Projekt. Erkennt das vorhandene Format (Eintrag-Präfix wie E-XYZ oder L-XYZ, Hilfstabellen wie Tag-Index oder Schnell-Lookup) und führt die Nummerierung fort. Aktualisiert Lookup-Tabelle, Tag-Index und Plattform-Übersicht, falls in der Datei vorhanden. Legt eine neue Wissensdatenbank aus TEMPLATE.md an, falls noch keine existiert. Trigger-Phrasen sind unter anderem "neues Learning", "neuer DB-Eintrag", "in die Wissensbasis", "knowledge base entry", "neuer Lerneintrag", "DB-Entry".
---

# Knowledge Base Entry

Erstellt einen neuen strukturierten Eintrag in einer projektspezifischen Wissensdatenbank. Format-erhaltend: liest die existierende Datenbank, erkennt das vorhandene Schema (Präfix, Felder, Hilfstabellen) und führt es fort. Keine Annahmen über Tag-System oder Plattform-Tags — alles wird aus der existierenden Datei abgeleitet.

## Vorgehen

### 1. Wissensdatenbank im Projekt finden

Suche mit `Glob` nach existierenden Wissensdatenbank-Dateien. Pfad-Reihenfolge (höchste Priorität zuerst):

1. `docs/LEARNINGS-CLAUDE-PROJECT.md`
2. `docs/LEARNINGS.md`
3. `docs/KNOWLEDGE.md`
4. `docs/KNOWLEDGE-BASE.md`
5. `LEARNINGS-CLAUDE-PROJECT.md` (Projekt-Root)
6. `LEARNINGS.md`
7. `KNOWLEDGE.md`
8. `KNOWLEDGE-BASE.md`

**Bei mehreren Treffern:** User fragen, welche Datei gemeint ist.

**Bei keinem Treffer:**
- User fragen, ob neue Wissensdatenbank angelegt werden soll
- Default-Pfad vorschlagen: `docs/LEARNINGS.md` (falls `docs/` existiert) oder `LEARNINGS.md` im Root
- Inhalt aus [TEMPLATE.md](TEMPLATE.md) (im Skill-Ordner) kopieren als Startpunkt

### 2. Existierendes Format erkennen

Lies die Datei und ermittle drei Eigenschaften:

**a) Eintrag-Präfix**

Suche per Regex `^## ([A-Z]+)-\d+ — ` nach allen Section-Überschriften. Häufige Präfixe: `E-`, `L-`, `K-`, `BUG-`, `ENTRY-`. Nimm den am häufigsten verwendeten. Wenn noch keine Einträge existieren: Default `E-`.

**b) Höchste Eintrag-Nummer**

Suche das numerisch höchste Vorkommen des Präfixes (z. B. `E-039`, `E-040`, ... → `040` ist höchste). Nächste Nummer = höchstes + 1, gleich viele Stellen wie höchstes (z. B. `040` → `041`, drei Stellen). Wenn keine Einträge: Start bei `001`.

**c) Hilfstabellen identifizieren**

Suche per Grep nach Section-Headern. Folgende Strukturen werden mitgepflegt — nur wenn sie existieren:

- `## Tag-Index` (auch Varianten: `## Tags`, `## Tag-Übersicht`)
- `## Schnell-Lookup` (auch: `## Lookup`, `## Quick-Lookup`, `## Symptom-Lookup`)
- `## Übersicht nach Plattform` (auch: `## Plattform-Übersicht`, `## Platform Overview`)

Wenn keine dieser Sections existiert: Skill ergänzt nur den Eintrag selbst und keine Hilfstabellen.

### 3. Eintragsdaten beim User erfragen

Stelle folgende Fragen in dieser Reihenfolge, knapp, eine pro Zeile:

1. **Titel** (eine Zeile, kommt nach dem Präfix-XYZ — in die Section-Überschrift)
2. **Symptom** — exakter Wortlaut der Fehlermeldung oder beobachtbares Verhalten. **Wortwörtlich übernehmen** für Volltext-Suche!
3. **Kontext / Plattform** — wo trat das auf
4. **Root Cause** — die technische Ursache
5. **Fix** — konkrete Lösungsschritte
6. **Diagnose-Befehl** (optional) — ein Shell-Befehl, der das Symptom verifiziert. Leere Antwort = weglassen.
7. **Lesson** (optional) — die generelle Lehre / Take-away. Sinnvoll, wenn der Fix selbst ein übertragbares Pattern enthält (z. B. „Bei externen Webhooks immer Optional-Chaining nutzen", „Auth-Layer immer als Map-Direktive, nicht hardcoded"). Leere Antwort = weglassen.
8. **Tags** — kommagetrennt, mit `#`-Präfix (z. B. `#oauth, #nginx, #server`)

### 4. Einfügeort bestimmen

Setze den Eintrag VOR die erste Section, die kein Eintrag ist. Erkennung: nicht-Eintrag-Section beginnt mit `## ` aber matcht NICHT das `^## {präfix}-\d+ —`-Pattern.

Typische Beispiele für solche Trenner-Sections:
- `## Verfahren / Vorgehensweisen`
- `## Anhang`
- `## Pflege dieser Datei`

Falls keine solche Section existiert (alle Sections sind Einträge): ans Ende der Datei anhängen.

### 5. Eintrag generieren

Format des Eintrags (Details siehe [ENTRY-FORMAT.md](ENTRY-FORMAT.md)):

````markdown
## {präfix}{nummer} — {titel}

**Symptom:** {symptom-text wortwörtlich}

**Kontext / Plattform:** {kontext}

**Root Cause:** {root cause}

**Fix:** {fix}

**Diagnose-Befehl:**
```bash
{diagnose-befehl}
```

**Lesson:** {generelle Lehre, falls vorhanden}

**Tags:** `#tag1` `#tag2` `#tag3`

---
````

**Wenn Diagnose-Befehl leer:** den ganzen Block `**Diagnose-Befehl:** ...` weglassen.
**Wenn Lesson leer:** den `**Lesson:**`-Block weglassen.

**Verbose ist OK — User-Details bewahren:**

Wenn der User-Prompt detailreiche Hinweise enthält (Zusatz-Tipps, Konfig-Snippets, Edge-Case-Hinweise wie „falls `ulimit -n` zu niedrig…", „bei mehr als N Items zusätzlich…"), übernimm sie **vollständig** in den Eintrag. **Nicht zusammenfassen, nicht kürzen.** Die Wissensdatenbank wird Wochen oder Monate später gelesen — da hilft mehr Kontext, nicht weniger. Lieber ein 30-Zeilen-Eintrag, der bei späterem Lookup alle Antworten enthält, als ein knapper 10-Zeilen-Eintrag, bei dem man weitere Recherche braucht.

### 6. Hilfstabellen pflegen (nur wenn vorhanden)

**Tag-Index** (falls existiert):
- Für jeden Tag im neuen Eintrag: prüfen, ob er schon im Index steht
- Falls nicht: neue Zeile `| #tagname | {Kurzerklärung} |`
- Kurzerklärung mit User abklären, wenn der Tag neu und nicht selbsterklärend ist

**Schnell-Lookup** (falls existiert):
- Neue Zeile am Ende der Tabelle anfügen
- Spalten anhand der existierenden Tabellen-Header ableiten
- Häufige Spalten: Plattform-Emoji + Symptom-Kurzfassung + Anker-Link

**Anker-Slug-Generierung — wichtiger Konsistenz-Check:**

Verschiedene Markdown-Renderer (GitHub, GitLab, MkDocs, VSCode-Vorschau) erzeugen aus dem Section-Header leicht unterschiedliche Anker. Damit Lookup-Links zuverlässig zielen, **richte dich nach der bestehenden DB** — nicht nach einer abstrakten Spec:

1. Schau dir 2–3 existierende Anker-Links in der Lookup-Tabelle der gleichen Datei an (z. B. `[E-039](#e-039-...)`).
2. Erkenne die Konvention:
   - **Einzel-Bindestrich nach E-Nummer** (`#e-039-ga4-crash-loop-...`) — häufig, manche Renderer kollabieren mehrfache Bindestriche
   - **Doppel-Bindestrich nach Em-Dash** (`#e-039--ga4-crash-loop-...`) — strikter GitHub-Style mit Em-Dash entfernt + zwei umgebenden Spaces zu zwei Bindestrichen
3. Generiere den neuen Anker im **gleichen Stil** wie die bestehenden — Konsistenz innerhalb der DB ist wichtiger als Spec-Treue.
4. Falls noch keine Anker-Links existieren (frische DB): Default ist **Einzel-Bindestrich** (kompatibel mit den meisten Renderern, weniger Fehlerquellen).

Beispiel:
- Section-Header: `## E-040 — Fehler bei "OAuth-Refresh"`
- Bei Einzel-Bindestrich-DB: `#e-040-fehler-bei-oauth-refresh`
- Bei Doppel-Bindestrich-DB: `#e-040--fehler-bei-oauth-refresh`

**Plattform-Übersicht** (falls existiert):
- User nach passender Kategorie fragen (anhand der existierenden Zeilen der Tabelle)
- Neue Eintragsnummer in der entsprechenden Zeile ergänzen (durch Komma getrennt zu bestehenden)

### 7. Diff zeigen und bestätigen

Zeige dem User kompakt, was geändert wird:

```
Geplante Änderungen an {dateipfad}:

→ Neuer Eintrag: {präfix}{nummer} — {titel}
  Position: vor "## Verfahren / Vorgehensweisen" (Zeile {N})

→ Lookup-Tabelle: +1 Zeile (Zeile {M})
→ Tag-Index: +{X} neue Tags (Zeile {P})
→ Plattform-Übersicht: Kategorie "{kategorie}" um {präfix}{nummer} erweitert

Speichern? (j/n)
```

Warte auf Bestätigung, bevor du `Edit` ausführst.

### 8. Schreiben und abschließen

Nach Bestätigung: `Edit`-Calls durchführen. Reihenfolge:
1. Erst Hilfstabellen (Tag-Index, Lookup, Plattform-Übersicht — falls vorhanden)
2. Dann Haupteintrag

Abschluss-Meldung an User:
```
✓ Eintrag {präfix}{nummer} angelegt in {pfad}
  Lookup-Tabelle: aktualisiert
  Tag-Index: {X} neue Tags
```

## Sonderfall: Neue Wissensdatenbank anlegen

Wenn keine bestehende Datei gefunden wurde:

1. User-Bestätigung einholen: „Soll ich eine neue Wissensdatenbank anlegen unter `{pfad}`?"
2. Inhalt aus [TEMPLATE.md](TEMPLATE.md) (im Skill-Ordner) lesen
3. Datei am Zielpfad anlegen via `Write`
4. Mit Schritt 3 (Eintragsdaten erfragen) fortfahren — Eintrag wird `{präfix}001` sein

## Prinzipien

- **Format-Erhaltung absolut:** Niemals Strukturen ändern, die schon da sind — nur ergänzen, was passt
- **Auto-Erkennung statt Hardcoding:** Keine Annahmen über Tag-System, Präfix-Schema, Plattform-Tags. Alles wird aus der vorhandenen Datei abgeleitet
- **Bestätigung vor Edit:** Immer Diff zeigen, dann erst speichern
- **Wortlaut-Treue:** Symptom-Texte exakt übernehmen — sie sind für Volltext-Suche entscheidend
- **Sparsam mit Auxiliary-Updates:** Hilfstabellen werden nur gepflegt, wenn sie schon existieren — nicht neu erfunden

## Tool-Übersicht

Welche Tools dieser Skill verwendet:

- **Glob**: Wissensdatenbank-Dateien im Projekt finden
- **Grep**: Eintrag-Präfix erkennen, höchste Nummer ermitteln, Hilfstabellen lokalisieren
- **Read**: Datei-Inhalt einlesen für Format-Analyse
- **Edit**: Eintrag einfügen, Hilfstabellen pflegen
- **Write**: Nur wenn neue Datei aus [TEMPLATE.md](TEMPLATE.md) angelegt werden muss

## Weiterführende Dateien im Skill-Ordner

- **[TEMPLATE.md](TEMPLATE.md)** — Skelett für neue Wissensdatenbanken
- **[ENTRY-FORMAT.md](ENTRY-FORMAT.md)** — Detaillierte Schema-Beschreibung eines Eintrags inkl. Beispielen
