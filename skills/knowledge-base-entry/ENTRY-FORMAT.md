# Eintrag-Format — Schema-Detail

Detaillierte Spezifikation eines einzelnen Wissensdatenbank-Eintrags. Wird von `SKILL.md` referenziert, wenn dort Detail-Klärungen nötig sind.

## Gesamtstruktur

Ein Eintrag ist eine eigenständige Markdown-Section, beginnt mit `## ` als Section-Header und endet mit einem `---`-Trenner (drei Bindestriche, eigene Zeile).

## Section-Header

Format:
```
## {präfix}{nummer} — {titel}
```

- **Präfix:** kurzes Kürzel + Bindestrich, durchgängig in der Datei (Beispiele: `E-`, `L-`, `K-`, `BUG-`)
- **Nummer:** mindestens drei Stellen, mit führenden Nullen (`001`, `042`, `123`)
- **Trenner:** Em-Dash `—` (U+2014) zwischen Nummer und Titel — nicht Hyphen, nicht Doppel-Hyphen
- **Titel:** Eine knappe Zeile, beschreibt das Problem in 3–8 Wörtern

Beispiele:
- `## E-039 — GA4: Crash-Loop bei Refresh-Failure`
- `## L-007 — Datenbank-Index fehlt bei häufiger Query`
- `## BUG-042 — Login-Form verliert State bei Validation-Fehler`

## Felder

Jeder Eintrag enthält bis zu sieben Felder. Pflicht sind Symptom, Kontext/Plattform, Root Cause, Fix und Tags; Diagnose-Befehl und Lesson sind optional.

### 1. Symptom (Pflicht)

Was sieht/erlebt der Nutzer? **Exakter Wortlaut** der Fehlermeldung, oder beobachtbares Verhalten.

```markdown
**Symptom:** {beschreibung}
```

Für mehrzeilige Fehlermeldungen einen Code-Block verwenden:

```markdown
**Symptom:**
```
HTTP/1.1 500 Internal Server Error
{"error": "connection_timeout"}
```
```

**Wichtig:** Wortlaut-Treue ist entscheidend, weil Volltext-Suche der Hauptzugriffsweg auf die Wissensdatenbank ist.

### 2. Kontext / Plattform (Pflicht)

Wo trat das Problem auf? Welche Plattform, welcher Service, welche Version?

```markdown
**Kontext / Plattform:** {beschreibung}
```

Beispiele:
- `**Kontext / Plattform:** Google Ads MCP-Server, Python 3.12, nach Re-Auth via Auth-Helper`
- `**Kontext / Plattform:** Frontend (React 18) bei Form-Submission`
- `**Kontext / Plattform:** Production-Datenbank (Postgres 16), Last >1000 RPS`

### 3. Root Cause (Pflicht)

Technische Ursache. Was war wirklich los — nicht das Symptom, sondern der Mechanismus dahinter.

```markdown
**Root Cause:** {erklärung}
```

Bei komplexen Ursachen mehrere Absätze oder Aufzählungen erlaubt:

```markdown
**Root Cause:** Refresh-Token wurde für Scope X ausgestellt, Code fordert aber Scope Y an. Google rejected den Refresh, weil:

1. Token-Aussteller-Scope ist subset des angeforderten
2. OAuth-Library macht keinen automatischen Scope-Downgrade
3. Daher wird die ganze Anfrage abgelehnt mit `invalid_grant`
```

### 4. Fix (Pflicht)

Konkrete Lösungsschritte. Idealerweise Befehle / Code-Snippets, die direkt anwendbar sind.

```markdown
**Fix:** {schritte}
```

Mit Code-Block bei Befehlen:

````markdown
**Fix:** Scope in beiden Stellen angleichen:

```python
# auth-helper/server.py
"gsc": {
    "scopes": ["https://www.googleapis.com/auth/webmasters"],
    ...
}
```

Danach Container neu bauen + starten.
````

### 5. Diagnose-Befehl (optional)

Ein Shell-Befehl oder ähnliches, der das Symptom verifiziert. Wenn vorhanden:

````markdown
**Diagnose-Befehl:**
```bash
docker compose logs mcp-gsc | grep "OAuth authentication failed"
```
````

Wenn nicht angegeben: Feld komplett weglassen, nicht leer lassen.

### 6. Lesson (optional)

Eine generelle Lehre oder ein übertragbares Pattern, das man aus dem Fix mitnehmen kann. Sinnvoll, wenn das konkrete Problem ein Symptom einer breiteren Klasse ist und der Fix-Pattern bei ähnlichen Fällen auch greift.

```markdown
**Lesson:** {ein Satz, max. ein kurzer Absatz}
```

Beispiele:
- `**Lesson:** Bei externen Webhook-Payloads nie annehmen, dass Optional-Felder immer mitkommen. Defensive Zugriffe (\`?.\`) sind in Code-Nodes Standard, nicht Ausnahme.`
- `**Lesson:** \`restart: always\` in Compose und \`systemctl enable docker\` sind zwei separate Schichten — beide müssen gesetzt sein, damit Container reboot-fest sind.`

**Wann weglassen:** Wenn der Fix sehr spezifisch ist und keine generelle Lehre erkennbar ist (z. B. ein Tippfehler in einer Config-Datei). Lieber weglassen als banale Allgemeinheiten zu schreiben.

### 7. Tags (Pflicht)

Kategorisierung. Eine Zeile, Tags durch Leerzeichen getrennt, jeder Tag mit `#` und in Backticks.

```markdown
**Tags:** `#oauth` `#mcp-server` `#auth-helper`
```

**Tag-Konventionen:**
- Lowercase, Bindestriche statt Spaces (`#mcp-server`, nicht `#MCP Server`)
- Erst Domain (`#oauth`, `#network`), dann Plattform-Tag (`#mcp-server`, `#nginx`), dann Spezifika (`#refresh-token`)
- 2–5 Tags pro Eintrag — zu wenig macht's unauffindbar, zu viele verwässern

Falls die Wissensdatenbank einen Tag-Index hat: neue Tags dort mit Bedeutung ergänzen.

## Vollständiges Beispiel

````markdown
## E-037 — Scope-Mismatch im Token vs. MCP-Server-Code

**Symptom:** Re-Auth war erfolgreich, Container wurde restartet, erste ~60 Min funktionieren MCP-Calls. Dann plötzlich in den Container-Logs:
```
Processing request of type CallToolRequest
OAuth authentication failed: Error
```

**Kontext / Plattform:** MCP-Server (Python und Node) hinter Auth-Helper. Tritt bei jedem Service auf, dessen `SCOPES` im Code nicht mit den im Auth-Helper konfigurierten Scopes übereinstimmen.

**Root Cause:** Die ersten ~60 Min nach Re-Auth nutzt der Code den Access-Token direkt (kein Round-Trip zu Google). Sobald der Access-Token abläuft, ruft der Code `creds.refresh(Request())` auf. google-auth schickt den Refresh-Token an Google mit dem Code-Scope. Wenn dieser Scope breiter ist als der Scope, mit dem der Refresh-Token ausgestellt wurde, lehnt Google den Refresh ab.

**Fix:** Beide Stellen auf identischen Scope bringen — entweder Code-Scope schmälern oder Auth-Helper-Scope verbreitern. Nach Anpassung: Auth-Helper rebuilden, Re-Auth via UI, Container restart.

**Diagnose-Befehl:**
```bash
# Code-Scopes auf dem Server
grep -n "SCOPES\s*=" /opt/n8n/mcps-pseudo/*/oauth/google_auth.py
# Auth-Helper-Scopes
grep -A1 '"scopes"' /opt/n8n/mcps-pseudo/auth-helper/server.py
```

**Tags:** `#mcp-server` `#auth-helper` `#oauth-flow`

---
````

## Anker-Slug-Konvention (für Lookup-Tabellen-Links)

**Wichtig:** Markdown-Renderer (GitHub, GitLab, MkDocs, VSCode-Vorschau) erzeugen aus identischen Section-Headern leicht unterschiedliche Anker. Das hat in der Praxis zwei „Lager":

| Stil | Beispiel-Anker für `## E-039 — GA4: Crash-Loop bei Refresh-Failure` |
|---|---|
| **Einzel-Bindestrich** (kollabiert mehrfache Bindestriche) | `#e-039-ga4-crash-loop-bei-refresh-failure` |
| **Doppel-Bindestrich** (strikt GitHub-konform, ` — ` → `--`) | `#e-039--ga4-crash-loop-bei-refresh-failure` |

**Praxis-Regel: Schau auf die bestehende DB.** Wenn dort Anker mit Einzel-Bindestrich gepflegt werden, nutze Einzel-Bindestrich. Wenn Doppel-Bindestrich — den. Konsistenz innerhalb der Datei schlägt strikte Spec-Treue.

**Wenn die DB noch keine Anker-Links hat** (frische TEMPLATE.md): nimm **Einzel-Bindestrich** als Default — er ist mit mehr Renderern kompatibel und produziert keine doppelten Bindestriche, die manche Tools kosmetisch zu einem zusammenziehen.

### Slug-Bildung (Schritt für Schritt)

1. **Section-Header lowercase**
2. **Em-Dash `—` entfernen** (oder zu Bindestrich, je nach Lager)
3. **Sonderzeichen entfernen** (`!`, `?`, `:`, `"`, `(`, `)`, `/`, `\`, `'`)
4. **Spaces zu Bindestrichen**
5. **Im Einzel-Bindestrich-Lager:** mehrfache Bindestriche zu einem zusammenfassen
   **Im Doppel-Bindestrich-Lager:** mehrfache Bindestriche unangetastet lassen

Weitere Beispiele:

| Section-Header | Einzel-Stil | Doppel-Stil |
|---|---|---|
| `## E-039 — GA4: Crash-Loop` | `#e-039-ga4-crash-loop` | `#e-039--ga4-crash-loop` |
| `## L-007 — Datenbank-Index fehlt` | `#l-007-datenbank-index-fehlt` | `#l-007--datenbank-index-fehlt` |
| `## BUG-042 — Login-Form verliert State` | `#bug-042-login-form-verliert-state` | `#bug-042--login-form-verliert-state` |

## Häufige Fehler beim Einfügen

- **Em-Dash vergessen:** Statt `—` ein normales Minus `-` benutzt. Macht Section-Anchor inkonsistent.
- **Symptom nicht wortwörtlich:** Wenn das Symptom paraphrasiert wird, findet niemand den Eintrag bei Volltext-Suche nach der echten Fehlermeldung.
- **Trenner-`---` fehlt:** Macht den Eintrag visuell mit dem nächsten verschmolzen.
- **Falsche Eintrag-Position:** Eintrag soll vor Hilfssektionen wie „Verfahren" oder „Anhang" stehen, nicht ganz am Ende.
- **Tag-Index nicht gepflegt:** Neue Tags ohne Erklärung im Index → niemand weiß, was sie bedeuten sollen.
