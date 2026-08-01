# {{ Projekt-Name }} — Wissensdatenbank

Wissensdatenbank für **{{ Projekt-Kurzbeschreibung }}**. Jeder Eintrag ist eine eigenständige Diagnose im Format: **Symptom → Kontext/Plattform → Root Cause → Fix → Diagnose-Befehl (optional) → Lesson (optional) → Tags**.

Diese Datei ist als **Single-Source-of-Truth für Fehler-Lookups** gedacht. Volltext-Suche nach exakten Fehlermeldungen wird unterstützt.

## Wie zu lesen

- **Volltext-Suche nach Fehlermeldung** funktioniert: alle Symptome sind im exakten Wortlaut hinterlegt
- **Tags** am Ende jedes Eintrags klassifizieren das Problem-Domain
- **Diagnose-Befehl** (sofern angegeben) ist der eine Shell-Befehl, der das Symptom verifiziert
- **Reihenfolge:** chronologisch der Erstaufnahme (E-001 zuerst eingetragen, höchste Nummer zuletzt)

## Tag-Index

| Tag | Bedeutung |
|---|---|
<!-- Tags hier ergänzen, sobald sie in Einträgen erstmals verwendet werden -->

## Schnell-Lookup nach Symptom / Fehlermeldung

| Was du siehst | Springe zu |
|---|---|
<!-- Pro Eintrag eine Zeile: kurzes Symptom + Anker-Link auf den Eintrag -->

---

<!-- Einträge ab hier — neue Einträge VOR der "Pflege"-Sektion einfügen -->

## Pflege dieser Datei

- **Neuer Eintrag = neues `E-XYZ`-Label**, fortlaufend nummeriert (oder anderer Präfix, je nach Projekt-Konvention)
- **Format strikt einhalten:** Symptom / Kontext / Root Cause / Fix / Diagnose-Befehl (optional) / Lesson (optional) / Tags
- **Symptom-Text wortwörtlich** vom Original übernehmen — Volltext-Suche ist der Hauptzugriffsweg
- **Schnell-Lookup-Tabelle** oben aktualisieren, wenn ein neuer Fehler ein eindeutiges Symptom hat
- **Tag-Index** ergänzen, wenn neue Domain-Tags entstehen
- Bei größeren Setup-Changes: stattdessen in der jeweiligen Setup-/Architektur-Doku festhalten — diese Datei ist nur Lookup
- Tipp: Mit dem `knowledge-base-entry`-Skill (siehe Claude Code / claude.ai Skills) werden neue Einträge automatisch im richtigen Format eingefügt
