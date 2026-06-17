# Log Guide — the `log/` Folder

The wiki's operation log is a **folder**, not a single file. One file per day,
named `log/YYYYMMDD.md`. This keeps individual files small, makes daily activity
easy to scan, and plays well with git diffs.

## File naming

- Filename: `log/YYYYMMDD.md` (e.g., `log/20260409.md`)
- Regex: `^\d{8}\.md$`
- No other files allowed at the top of `log/`. `lint_wiki.py` flags stray files.

## File format

```markdown
# 2026-04-09

## [09:15] ingest | google-gemma-4-article
- Source: raw/articles/google-gemma-4.md
- Touched: 5 wiki pages
  - sources/google-gemma-4 (new)
  - concepts/gemma (updated)
  - entities/google (updated)
  - index.md (updated)

## [14:30] audit | resolved 20260409-143022-a1b2
- Target: concepts/claude-code.md
- Change: corrected file count from ~1,900 to ~1,800

## [15:05] lint | 2 dead links found, 2 fixed
- [[claude-code-architecture]] → [[concepts/claude-code/architecture]] in 2 files
```

**Rules:**
- One H1 per file, matching the filename date in ISO format (`YYYY-MM-DD`).
- One H2 per operation: `## [HH:MM] <op> | <one-line description>`
- Time is local time, 24h.
- Body is a short bullet list summarising what changed.

## Allowed operations

| Op | When | Example |
|---|---|---|
| `scaffold` | Initial wiki setup | `## [08:00] scaffold \| Initialized wiki` |
| `ingest` | New source added | `## [09:15] ingest \| google-gemma-4` |
| `compile` | Structural edits, splits, merges | `## [10:00] compile \| split page into 7 sub-pages` |
| `query` | Question answered | `## [11:20] query \| rag-vs-wiki-tradeoffs` |
| `promote` | Output promoted to wiki/ | `## [11:35] promote \| RAG vs Wiki (from query)` |
| `lint` | Health check run | `## [15:05] lint \| 2 dead links, 2 fixed` |
| `audit` | Feedback processed | `## [14:30] audit \| resolved 20260409-143022-a1b2` |
| `split` | Page split into folder | `## [10:00] split \| claude-code → claude-code/` |
| `optimize` | Self-optimization run | `## [16:00] optimize \| 3 patterns → 2 rules proposed, 1 accepted` |

## Quick grep

```bash
# All operations on a day
cat log/20260409.md

# Recent activity across all days
grep -rh "^## \[" log/ | sort | tail -20

# All audit resolutions
grep -rh "^## \[.*\] audit" log/

# Activity on a specific file
grep -rl "claude-code" log/
```

## What NOT to put in the log

- **Content**: don't copy-paste article chunks. The log is a pointer.
- **Long rationale**: put design decisions in `CLAUDE.md`, not the log.
- **Secrets / credentials**: never.
- **Audit file bodies**: only the audit ID and a one-liner.

## Migration from single-file `log.md`

If you have an existing `wiki/log.md` (from the v1/v2 system):

1. Parse each `YYYY-MM-DD HH:MM | op | description` entry.
2. Group entries by date.
3. For each date, create `log/YYYYMMDD.md` with H1 date and H2 per entry.
4. Delete the old `wiki/log.md`.
