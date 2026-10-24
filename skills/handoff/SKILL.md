---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
argument-hint: "What will the next session be used for?"
disable-model-invocation: true
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save it to `tmp/handoff/handoff-<YYYY-MM-DD>-<short-topic>.md` inside the project (create the folder if needed, including a `.gitignore` file containing `*` inside it). A SessionStart hook automatically reads the newest handoff into the next session; after a compaction it prefers documents written during the current session.

Include a "suggested skills" section in the document, which suggests skills that the agent should invoke.

Do not duplicate content already captured in other artifacts (specs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

A handoff carries state, not rules. Standing imperatives ("never `git add -A`", "never commit builder test files") belong in the project's `CLAUDE.md` under `## Betriebsregeln`, where they apply in every turn; in a handoff they expire at the next session boundary. If the conversation produced such a rule, suggest adding it to `CLAUDE.md` instead of writing it into the handoff.

Redact any sensitive information, such as API keys, passwords, or personally identifiable information.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
