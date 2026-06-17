# Audit Guide — Human Feedback Processing

The wiki supports **two feedback surfaces**. Both are processed by `audit_review.py`.

---

## Surface 1: `audit/` Directory (Structured Feedback)

One file per feedback item, YAML frontmatter + markdown body. Produced by the
Obsidian plugin or the web viewer. Consumed by the AI during the `audit` op.

### Directory layout

```
<wiki-root>/audit/
├── 20260409-143022-claude-code-size.md    ← open feedback
├── 20260409-150110-rag-definition.md      ← open feedback
└── resolved/
    ├── 20260408-110505-typo-gemma.md      ← processed, with resolution
    └── 20260407-180012-rejected-scope.md  ← rejected, with rationale
```

### File format

Filename: `YYYYMMDD-HHMMSS-<short-slug>.md`

```markdown
---
id: 20260409-143022-a1b2
target: wiki/concepts/claude-code.md
target_lines: [45, 52]
anchor_before: "## Overview\n\n| Dimension | Detail |\n"
anchor_text: "| **Scale** | ~1,900 files, 512,000+ lines |"
anchor_after: "\n| **Language** | TypeScript (strict) |"
severity: warn
author: lewis
source: obsidian-plugin
created: 2026-04-09T14:30:22+08:00
status: open
---

# Comment

The actual count should be ~1,800 files based on commit abc123.

# Resolution

<!-- Filled in when the audit is processed and moved to resolved/ -->
```

### Frontmatter fields

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | `YYYYMMDD-HHMMSS-<4hex>` |
| `target` | string | yes | Path relative to wiki root |
| `target_lines` | `[int, int]` | yes | 1-indexed line range (may drift) |
| `anchor_before` | string | yes | ~80 chars before selection |
| `anchor_text` | string | yes | Exact selected text |
| `anchor_after` | string | yes | ~80 chars after selection |
| `severity` | enum | yes | `info`, `suggest`, `warn`, `error` |
| `author` | string | yes | Free text |
| `source` | enum | yes | `obsidian-plugin`, `web-viewer`, `manual` |
| `created` | ISO 8601 | yes | Timestamp with timezone |
| `status` | enum | yes | `open` or `resolved` |

### Severity semantics

- **error** — factual mistake, broken link, wrong attribution
- **warn** — stale number, ambiguous sentence
- **suggest** — reword, reorganize
- **info** — additional context, not wrong

Process `error` and `warn` first, then `suggest`, then `info`.

---

## Surface 2: Inline `<!-- FIX: ... -->` Comments

Users can write corrections directly in wiki markdown files:

```markdown
The model uses approximately 175 billion parameters.
<!-- FIX: The actual number is 175B per the paper, but this should be quoted verbatim -->
```

`audit_review.py` scans all `wiki/**/*.md` files for these tags and extracts:
- File path
- Line number
- The user's comment text

### FIX comment format

```
<!-- FIX: <your correction or comment here> -->
```

The comment must be on its own line. Multi-line comments are supported:

```
<!-- FIX:
This section incorrectly states X.
The actual value is Y per source Z.
Please update and cite properly.
-->
```

---

## Anchor Strategy

Line numbers alone are fragile. So audit files carry a **text-based anchor
window** alongside the line numbers.

**On write** (plugin / web viewer):
1. Capture `target_lines` from the selection range
2. Extract `anchor_text` = exact selected characters
3. Extract `anchor_before` = up to 80 chars before selection
4. Extract `anchor_after` = up to 80 chars after selection

**On read** (AI during `audit`):
1. Try `target_lines` — check if text at those lines contains `anchor_text`
2. If not, search the whole file for `anchor_text`. If exactly one match, use it.
3. If multiple matches, use `anchor_before + anchor_text + anchor_after` as combined key
4. If no match: anchor is **stale** — ask user to re-anchor or archive

---

## Processing Workflow (the `audit` op)

1. Run `python3 scripts/audit_review.py <wiki-root> --open` to get grouped list
2. For each open item:
   - Read the file/comment, locate the anchor in the target
   - Decide: **accept** / **partial** / **reject** / **defer**
   - Apply edits to the target file (smallest edit that fixes the issue)
3. For audit/ files:
   - Append a `# Resolution` section
   - Flip `status: open` → `status: resolved` in frontmatter
   - Move file to `audit/resolved/`
4. For inline FIX comments:
   - Apply the correction
   - Remove the `<!-- FIX: ... -->` comment
5. Log each resolution: `## [HH:MM] audit | resolved <id> — <one-liner>`

### Resolution section format

```markdown
# Resolution

2026-04-10 · accepted.
Fixed the file count (was "~1,900", corrected to "~1,800" per commit abc123).
Updated: wiki/concepts/claude-code.md lines 47–48.
```

Fields: Date · decision (`accepted`, `partial`, `rejected`, `deferred`) · what changed · files touched.

For **rejected** audits: explain why. Rejected files still move to `resolved/`.

For **deferred** audits: leave in `audit/`, add question to `CLAUDE.md` research questions.

---

## Tooling

- `scripts/lint_wiki.py` — validates audit file shape and target existence
- `scripts/audit_review.py` — lists, groups, and reports audit feedback
- `plugins/obsidian-audit/` — writes audit files from Obsidian
- `web/` — writes audit files from the web viewer
- `audit-shared/` — shared TypeScript library for schema, anchors, serialization
