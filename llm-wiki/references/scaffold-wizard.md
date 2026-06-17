# Scaffold Wizard — First-Time Setup Interview

Run this interview when `CLAUDE.md` does not yet exist. Ask these three questions,
collect answers, then run the scaffold script.

---

## Question 1 — Knowledge Domains

> "What knowledge domains do you want this wiki to cover? Examples:
> Economics · Finance · Technology · AI/ML · Science · Medicine · Law · History
> · General (for everything). Feel free to type your own."

---

## Question 2 — Second Language

> "Would you like bilingual annotations for technical terms?
> Options: No (English only) · Chinese · Japanese · Other (specify)"

---

## Question 3 — Private Zone (optional)

> "Do you need a private zone? That's a folder the agent will NEVER read directly —
> for sensitive material (clinical/PHI, personal journals, confidential records). It is
> kept out of ingest and never enters the wiki; to use a file you redact it into `raw/`
> first. Recommended for anything regulated or private.
> Options: No · Yes — give a folder name, e.g. `private` or `private,raw/journal`"

---

## After collecting answers — run scaffold

```bash
python3 .claude/skills/llm-wiki/scripts/scaffold.py <wiki-root> "<Topic>" \
  --domains "<answer1>" --lang <answer2> --private-zones "<answer3, or empty for none>"
```

Always pass `--private-zones` (use `""` for none) so the script doesn't stop to prompt.
For a hard guarantee on a private zone, also add a `Read(...)` deny for those paths to
`.claude/settings.json` — the `update-config` skill can do it.

Add `--search qmd` to enable semantic search (off by default — needs qmd installed; the
collection name is auto-derived from the title). It writes a `## Search` block to CLAUDE.md.
