---
name: llm-wiki
description: >-
  Build and maintain a self-compiling Markdown wiki / knowledge base (the
  "Karpathy-style LLM wiki" pattern): an agent ingests raw sources into a vault,
  compiles persistent cross-linked source / concept / entity / comparison /
  synthesis pages with line-level citations, splits large topics into
  divide-and-conquer folder hierarchies, and answers questions grounded in the
  compiled vault instead of re-reading raw docs each time — so knowledge
  compounds across sessions instead of being rediscovered. Eight logged
  operations: scaffold, ingest, batch_ingest, query, lint, audit, reflect,
  compile. Use whenever someone works against their wiki, knowledge
  base, vault, or "second brain" — even casually: ingesting or adding a
  paper/article/note ("fold this into the wiki"), scaffolding a new knowledge
  base, querying it ("based on my wiki, what do we know about X"),
  batch-ingesting a folder of files, running a lint or health check (dead links,
  orphans, stale pages), processing audit feedback or inline FIX comments,
  splitting or restructuring an overgrown page, comparing two things from the
  notes, or finding patterns across everything ingested (reflect).
---

## Core idea

Rather than re-retrieving raw docs on every query (RAG), the LLM **compiles** raw
sources into a persistent, cross-linked Markdown wiki and answers from it. The
compile cost is paid once at ingest and amortized across every later query, so
knowledge compounds instead of being rediscovered.

Two cross-cutting principles run through every operation:
- **Divide-and-conquer** — split big things into small, linkable pieces so the
  wiki stays navigable as it grows (see § Divide-and-conquer).
- **Compile vs. verify-fresh** — summarize concepts into the wiki, but re-check
  specifics (numbers, dates, quotes) against `raw/`, since a faithful summary can
  still drop precision (see § Compile vs. verify-fresh).

- **You** own: sourcing raw material, asking questions, steering direction,
  filing feedback on anything the AI got wrong.
- **LLM** owns: all writing, cross-referencing, filing, bookkeeping, and
  acting on your feedback.
- **Python scripts** own: deterministic work — hashing, file creation,
  health checks, index building, audit scanning. The LLM calls them and reads
  their output.

## Session start routine

Execute in this order at the start of every session:

1. **Read `CLAUDE.md`** — the single config + schema file: wiki scope/domains,
   language, naming conventions, and current article list (plus any vault-specific
   rules the vault's `CLAUDE.md` defines).
2. **Skills are auto-discovered** — Claude Code loads every skill in
   `.claude/skills/` natively (progressive disclosure: each skill's `description`
   is always in context; the body loads when a task matches). You do **not**
   manually read or "enable" skills. To add one, drop its folder in
   `.claude/skills/<name>/` — nothing else. When two skills overlap, the
   preference lives in each skill's own `description` (and `CLAUDE.md` for
   safety-critical routing). Stable user preferences and
   learned rules live in `CLAUDE.md` (§ Notes for the LLM).
3. **Read `wiki/index.md`** — current state of the knowledge base.
4. **Read last entry of `log/`** — `ls log/ | tail -1`, then read the file.
5. **Check `audit/`** — if any `*.md` files exist (not `.gitkeep`), note the
   count and mention it to the user.
6. **Staleness alert** — run:
   ```bash
   python3 .claude/skills/llm-wiki/scripts/lint_wiki.py <wiki-root> --stale-only
   ```
   If any pages are returned, show the list and ask: "These concept pages
   haven't been reviewed recently — want me to add them to the freshen queue?"
7. **qmd status** (only if `search_tool: qmd` in `CLAUDE.md` `## Search`; off by default):
   ```bash
   qmd status
   ```
   Report indexed file count. If indexed count < actual wiki page count,
   suggest: "qmd index appears stale — run `qmd embed` to sync."
   If qmd is not configured, skip silently.

If the wiki has not been scaffolded yet (no `CLAUDE.md`):
Read `references/scaffold-wizard.md` — run the three-question setup interview,
then execute the scaffold script as directed there.

## Directory layout

```
<wiki-root>/
├── CLAUDE.md              ← Single config + schema (scope/domains, conventions, articles)
├── log/                   ← Per-day operation log (one file per day)
│   └── YYYYMMDD.md
├── audit/                 ← Human feedback inbox (one file per comment)
│   └── resolved/          ← Processed feedback
├── raw/                   ← Immutable source documents (LLM reads, never writes)
│   ├── articles/
│   ├── papers/
│   ├── pdfs/              ← PDF source files
│   ├── notes/
│   ├── images/
│   ├── clippings/         ← Obsidian Web Clipper output
│   ├── personal/          ← Personal writing
│   └── refs/              ← Pointer files for large binaries
├── <private-zone>/        ← Optional (scaffold --private-zones). Sensitive data; agent NEVER reads directly
├── .claude/               ← Claude Code project config (hidden from Obsidian's graph)
│   ├── skills/            ← Skills Claude Code discovers natively
│   │   ├── llm-wiki/      ←   This skill — bundled into the vault at scaffold time
│   │   └── <domain-skill>/ ←  Any other skills you install (pdf, finance, research, …)
│   └── commands/          ← Slash-command wrappers (arg-parsing entry points)
├── wiki/                  ← LLM-generated knowledge (LLM writes, you read)
│   ├── index.md           ← Lightweight master catalog (domain anchors + top-5)
│   ├── index/             ← Full per-domain catalogs (auto-generated)
│   │   ├── <domain-a>.md
│   │   └── <domain-b>.md
│   ├── overview.md        ← Health dashboard
│   ├── QUESTIONS.md       ← Open questions queue
│   ├── sources/           ← Per-source summary pages
│   ├── concepts/          ← Concept/topic pages
│   ├── entities/          ← People, tools, papers, organizations
│   ├── comparisons/       ← Side-by-side analysis of two concepts, tools, or approaches
│   ├── synthesis/         ← Cross-source analysis (multi-source patterns, not pairwise)
│   └── templates/         ← Page templates
└── outputs/               ← All query answers and reports
    └── queries/
```

## System architecture

| Layer                        | Owner  | Rule                                                                          |
|------------------------------|--------|-------------------------------------------------------------------------------|
| `raw/`                       | Human  | IMMUTABLE. LLM reads only, never modifies.                                    |
| `<private-zone>/` (if any)   | Human  | NEVER read directly (`Read`/`cat`/etc.). Sensitive data; pipeline-only access. See `CLAUDE.md` § Private zones. |
| `wiki/`                      | LLM    | LLM fully owns. Human browses, does not edit.                                 |
| `outputs/`                   | LLM    | All answers persist here. Never lost in chat.                                 |
| `log/`                       | LLM    | Append-only operation log.                                                    |
| `audit/`                     | Shared | Human writes feedback; LLM processes it.                                      |
| `.claude/skills/`            | Shared | Skills auto-discovered by Claude Code. Drop a folder to add one.               |
| `CLAUDE.md`                  | Shared | Single config + schema. Human sets scope/domains/settings; LLM maintains articles. |

Skill dispatch is native (by each skill's `description`); cross-skill preferences and
safety-critical routing live in those descriptions and `CLAUDE.md`. Stable user
preferences and learned rules also live in `CLAUDE.md` (§ Notes for the LLM). A
multi-step procedure that recurs belongs in its own skill rather than bloating this one.

---

## Divide-and-conquer

Big things become small, linkable pieces — on the way in, in how the vault is
shaped, and on the way out. This is what keeps the wiki navigable as it grows: a
single flat index degrades past ~100–200 pages, so structure is split early
rather than patched later.

- **On ingest (large source).** Don't distill a 400-page document in one pass.
  First skim it into a short outline (sections + their line ranges), then distill
  one section at a time into focused pages, each linked back to the source.
  Scaffold before you summarize.
- **On structure (large topic).** When a concept page would pass its ~1200-word
  ceiling, split it into a folder: a short `index.md` (definition + map of
  sub-pages) plus one focused 400–1200 word page per aspect, shown as indented
  bullets in the master index. The master `wiki/index.md` stays light; full
  per-domain catalogs live in `wiki/index/<domain>.md`. Detail and signs-to-split
  are in `references/article-guide.md` § Length Targets & Divide-and-Conquer.
- **On query (broad question).** Decompose a wide question into sub-questions,
  answer each against its own slice of the vault, then synthesize — labeling the
  cross-cutting inferences `[synthesis]`.

The operations below implement this loop: `ingest` and `compile` split pages,
`build_index.py` maintains the hierarchical index, and `query` fans out then
re-synthesizes.

---

## Compile vs. verify-fresh (synthesis-time)

A compiled wiki page is a *summary*: the agent chose what to keep at **ingest
time** and stored the result. That is the point — it pays the synthesis cost once
and amortizes it across every later query — but it has one failure mode worth
designing against. A summary can be faithful yet lose precision: a page records
"net-30 with early-payment discounts" while the raw contract says "2% if paid
within 10 days." Once the summary is cited as authoritative the dropped detail is
invisible — `lint` checks page-to-page consistency, not page-to-source fidelity.

So split knowledge by *when* it should be synthesized:

- **Compile — trust the wiki.** Definitions, concepts, relationships, stable
  structure: things that summarize well and rarely change. This is the wiki's job,
  and why it compounds.
- **Verify fresh — trust `raw/`.** Specific numbers, dates, percentages,
  thresholds, exact quotes, legal/financial terms. The wiki page may *point* to
  these, but the raw source stays authoritative — re-read it at query time instead
  of trusting the compiled value.

A vault's `CLAUDE.md` can make the routing explicit, declaring source types that
are raw-only and never compiled (contracts, logs, live tables). Three mechanisms
keep the layers honest: `ingest` records every specific as
`claims_requiring_verification`; `query` re-checks specifics against `raw/`; and
`lint`'s deep-lint and check 13 re-verify stored claims against their source.
Compile concepts, verify specifics fresh.

---

## The eight operations

Every action on the wiki is one of these eight. Each appends an entry to the
current day's log file (`log/YYYYMMDD.md`). See `references/log-guide.md`.

### 1. `scaffold`

Bootstrap a new wiki. Run:

```bash
python3 .claude/skills/llm-wiki/scripts/scaffold.py <wiki-root> "<Topic Title>" \
  --domains "AI,Finance" --primary-lang zh --lang en --private-zones ""
```

The setup interview (see `references/scaffold-wizard.md`) asks five things: **domains**;
the **primary language** (it leads in titles/headings); an optional **secondary
language** (annotated in parens — this makes the vault bilingual; pass `--lang no` for
monolingual); whether to enable **semantic search**; and whether you need a **private
zone**. The primary/secondary answers are recorded in `CLAUDE.md` — the `## Notes →
Language` line *and* a generated `### Bilingual format` block under Naming conventions
that states which language leads and shows a worked example. **The skill itself stays
language-agnostic and reads the order from `CLAUDE.md`; nothing about Chinese-vs-English
is hardcoded in the skill or templates.**

`--private-zones "<folder[,folder]>"` creates each folder under the wiki root and writes
a MANDATORY `## Private zones` + `## Strict workflow rules` block into `CLAUDE.md`. A
private zone is a path the agent must **NEVER read directly** (`Read`, `Bash(cat …)`,
etc.) — it holds sensitive data (PHI, personal info, confidential records) reachable only
through a designated pipeline. The folder lives outside `wiki/`, so it is never indexed,
linted, or queried. Pass `""` for none. In non-interactive/agent runs always pass
`--primary-lang`, `--lang`, and `--private-zones` so the script doesn't stop to prompt.

Creates the full directory tree, `CLAUDE.md` (the single config + schema file),
`wiki/index.md`, all templates, and the first log entry. It also **bundles the llm-wiki skill into
the new vault** (`<wiki-root>/.claude/skills/llm-wiki/` — SKILL.md + references/ +
scripts/), so the vault is self-contained: its documented
`.claude/skills/llm-wiki/scripts/...` commands resolve locally and you can move or
share the vault without a separate install. See the script's docstring for details.

After scaffolding:
1. Review and customize `CLAUDE.md` — define scope, naming conventions.
2. Start ingesting sources.

### 2. `ingest`

**Trigger words:** ingest, process this, add this source

Add a new source to the knowledge base.

**Step 1 — Run the bookkeeping script:**
```bash
python3 .claude/skills/llm-wiki/scripts/fast_ingest.py <wiki-root> <raw-file-path>
```

This is the **default ingest**: the agent reads the raw source **directly** — no
preprocessing skill in front of it — and compiles it into wiki pages. For a large source, scaffold first (see § Divide-and-conquer): outline the sections, then distill each. `fast_ingest.py` only does bookkeeping (hash, slug, stub); it does not transform the source. If the vault's `CLAUDE.md` requires a preprocessing or safety step for a source type, that overrides this default — follow it first.

The script:
- Computes SHA-256 hash
- Generates a URL-friendly slug
- Detects source type (personal-writing vs external)
- Creates a stub file at `wiki/sources/<slug>.md` with pre-filled YAML frontmatter
- Prints instructions telling you what to do next

If the stub already exists, the script will warn — delete it first to re-ingest.

**Step 2 — Read the raw file and fill in the stub:**
- Write the Summary section (2-4 sentences, every claim cited)
- Write Key Points (each with line citation)
- Extract concepts and entities
- If source `date` is more than 2 years before today, set `possibly_outdated: true` in frontmatter
- If source contains **any number, date, percentage, or threshold**, populate
  `claims_requiring_verification` with each one verbatim:
  ```yaml
  claims_requiring_verification:
    - "2% discount if paid within 10 days" (raw/contracts/vendor.md, L14)
    - "deadline: 2026-03-31" (raw/contracts/vendor.md, L22)
  ```
  lint check 13 will verify each string exists in the raw file at every lint run.

**Step 3 — Concept alignment (mandatory before creating any concept page):**
- Map each concept to an English lowercase-hyphen slug (map a Chinese-only name to its
  English slug, e.g. `第一性原理` → `first-principles-thinking`)
- Search `wiki/concepts/` for that slug
- Scan existing concept pages' `aliases` fields for a match in **either language**
  (Chinese↔Chinese, English↔English, Chinese↔English) — the idea may already live under
  a different-language alias or synonym
- If match found (slug OR any alias): UPDATE existing page, do not create a near-duplicate
- If no match: CREATE new page using `wiki/templates/concept-template.md`, filling
  `aliases` with **both the Chinese and English names** (+ synonyms)

**Step 4 — For each concept (create or update):**
- Set `title:` to the **primary-language name** (whichever language `CLAUDE.md`
  § Bilingual format names as primary); the `# H1` / first line leads with the primary
  language and annotates the secondary in `（）` (Chinese-primary vault: `中文名（English Name）`)
- Add source to Sources section
- Append to Evolution Log: `YYYY-MM-DD (N sources): 强化/修正/新增分歧 — <one-liner>`
- Update `source_count`, `last_reviewed`, `updated`; keep `aliases` complete & bilingual
- Apply bilingual term annotation on a term's first appearance — `primary（secondary）`,
  e.g. `中文（English）` in a Chinese-primary vault — per article-guide
- Apply line citations to every factual claim

**Step 5 — For each entity:** same logic as concepts.

**Step 5b — Comparisons (create when source explicitly compares two things):**

Create `wiki/comparisons/<a>-vs-<b>.md` (using `wiki/templates/comparison-template.md`) when:
- The source performs a direct pairwise comparison (two methods, two tools, two approaches)
- A query answer synthesizes a comparison worth reusing across future queries
- The difference is too structural to fit in either concept's Contradictions section

Use `[[comparisons/<a>-vs-<b>]]` wikilinks in both concept pages so the graph stays connected.
Do NOT create a comparisons page for general multi-source synthesis — that goes in `wiki/synthesis/`.

**Step 6 — Rebuild index:**
```bash
python3 .claude/skills/llm-wiki/scripts/build_index.py <wiki-root>
```
This regenerates `wiki/index.md` and `wiki/index/<domain>.md` automatically.
You do NOT manually update `wiki/index.md` after this step.

**Step 7 — Update search index** (only if `search_tool: qmd` in CLAUDE.md `## Search`):
```bash
qmd embed
```
This rebuilds vector embeddings so the new source is immediately queryable.

**Step 8 — Check wiki/QUESTIONS.md:** if this source answers an open question, notify user.

**Step 9 — Log:** append to `log/YYYYMMDD.md`:
```
## [HH:MM] ingest | <slug> — <one-line description> (touched N pages)
```

**Personal Writing Flow** (detected automatically by `fast_ingest.py`):
- Skip Summary section — no objective summary of your own writing
- Extract core argument → write into concept pages' "My Position"
- Do NOT increment `source_count` (no self-citation bias)
- SHA-256 still recorded

### 3. `batch_ingest`

**Trigger words:** batch ingest, ingest folder, process multiple files,
ingest all PDFs, process everything in raw/, bulk add

```bash
python3 .claude/skills/llm-wiki/scripts/batch_ingest.py <wiki-root> [--dir raw/articles] [--ext .md .pdf]
```

Default: each source is read directly, same as single `ingest`. Skips files already
ingested (SHA-256 match). After the script runs, fill each stub following `ingest`
Steps 2–5, then rebuild the index once all stubs are complete.

> The script also exposes a `--pdf` flag (auto-convert via a PDF skill before
> ingest) — **off by default**. Use it only if this vault's `CLAUDE.md` calls for a
> preprocessing step.

**After batch ingest — compile immediately (MANDATORY).** When you process 3+
sources in one batch, each source will independently extract concepts. This
produces shallow one-line stubs with no cross-source synthesis. Before creating
individual concept pages:
1. Read ALL source stubs first. Identify concepts that appear in 2+ sources —
   these are the highest-value targets.
2. Merge related low-overlap concepts into broader umbrella pages (e.g.,
   `short-squeeze` + `options-volatility` → `options-market-mechanics`).
3. Flesh out the merged pages with cross-source synthesis, Evolution Log,
   and line citations from every contributing source.
4. Only then create standalone pages for genuinely unique concepts.
5. Delete absorbed stubs; update source page wikilinks to point to new merged
   concepts; rebuild index.

Rule of thumb: a batch of N related sources should produce roughly N–2N fleshed-out
concept pages, not 5N one-line stubs. A concept page without an Evolution Log or
cross-source synthesis is an ingest TODO, not a finished page.

Log: `## [HH:MM] batch_ingest | N files processed, M already ingested`

### 4. `query`

**Trigger words:** direct question, "based on my knowledge base", "what does the wiki say"

Answer a question **grounded in the wiki**, not general knowledge.

**Index navigation — try in order, stop at first success:**

**Path A — qmd** (only if `search_tool: qmd` in CLAUDE.md `## Search`; off by default):
```bash
qmd query "<question>" -c <qmd_collection> -n 5   # qmd_collection: read from CLAUDE.md ## Search
```
Read returned pages in full; follow one level of wikilinks.
Also check `wiki/comparisons/` for relevant pairwise analysis.
If qmd is unreachable → fall through to Path B immediately.

**Path B — Index scanning** (default fallback):
- **Small wiki** (page count < `search_tool_threshold`, default 50):
  Read `wiki/index.md` directly. Scan for relevant pages.
- **Large wiki** (≥ threshold):
  Read `wiki/index.md` → identify relevant domain → read `wiki/index/<domain>.md` → navigate to pages.

Steps:
1. Navigate via index (Path A or B above)
2. Read identified pages in full; follow one level of wikilinks.
   Also check `wiki/comparisons/` for any relevant pairwise analysis.
3. If the wiki doesn't have enough material, say so. Suggest what to ingest.
4. Synthesize answer. Every claim traces to a specific source page.
5. Save to `outputs/queries/YYYY-MM-DD-<question-slug>.md`.
6. If answer has reuse value → promote to `wiki/concepts/`, add to `index.md`.
7. Log: `## [HH:MM] query | <question-slug>`

**Synthesis-time routing.** For any answer that turns on a specific number, date,
percentage, threshold, exact quote, or legal/financial term, verify against the
cited `raw/` source rather than trusting the compiled value — see § Compile vs.
verify-fresh.

Note confidence level. Explicitly flag conflicts between sources.
End with **Confidence Notes** listing all low/medium-confidence citations.

**Output format:**
- General → Markdown prose
- Comparison → Markdown table
- Presentation → Marp slides (`marp: true` in frontmatter)
- Data/trends → Python matplotlib code block
- List → Structured bullet list

### 5. `lint`

**Trigger words:** lint, health check, check wiki

```bash
python3 .claude/skills/llm-wiki/scripts/lint_wiki.py <wiki-root>
```

The script runs 12+ checks. Output: `outputs/lint-YYYY-MM-DD.md`.

**Flags:**
- `--stale-only` — only report stale pages (fast; used by session-start routine)
- `--structural` — skip uncited-claims check (faster for large wikis)

After running:
1. Show the user the summary (errors / warnings / suggestions count).
2. If `ERROR: sha256` errors exist, ask whether to propagate FIX comments:
   ```bash
   python3 .claude/skills/llm-wiki/scripts/cascade_flag.py <wiki-root>
   ```
   This writes `<!-- FIX: raw source changed — re-verify -->` on all citation
   lines in wiki pages that reference a modified source file.
3. If `broken-links` errors or warnings exist, run the maintainer (deterministic repair):
   ```bash
   python3 .claude/skills/llm-wiki/scripts/fix_links.py <wiki-root>               # dry run — preview
   python3 .claude/skills/llm-wiki/scripts/fix_links.py <wiki-root> --apply --stub  # repair + stub missing targets
   ```
   `fix_links.py` is the repair counterpart to lint's detection. It auto-fixes wrong-category and
   wrong-slug links (normalising both the link's category and slug to the target page's real filename
   turns a near-miss into an exact match), and with `--stub` creates minimal placeholder pages for genuinely missing targets so
   the link resolves and the page is flagged for filling. It reports anything ambiguous as `UNRESOLVED`
   for you to decide, and quarantines template-placeholder tokens. Re-run `lint_wiki.py` after to confirm
   `broken-links` is clear. (Trigger words: fix links, repair links, maintain.)
4. Ask whether to fix other flagged issues.
5. If `search_tool: qmd` in CLAUDE.md `## Search`, re-sync the search index:
   ```bash
   qmd update
   ```
6. Log: `## [HH:MM] lint | N issues found, M fixed`

**Deep Lint** (trigger: "deep lint" — monthly):
1. Randomly select 5 source summary pages from `wiki/sources/`.
2. Read each alongside its `raw_file`.
3. Compare every factual claim sentence-by-sentence against the raw source.
4. Report deviations. Fix immediately.
5. Log: `## [HH:MM] lint | deep-lint — N deviations found in 5 pages`

### 6. `audit`

**Trigger words:** audit, process feedback, check comments, fix errors

Process human feedback from two surfaces:

```bash
python3 .claude/skills/llm-wiki/scripts/audit_review.py <wiki-root> --open
```

The script scans:
- `audit/*.md` — YAML-anchored feedback files
- `wiki/**/*.md` — inline `<!-- FIX: ... -->` comments (including those written
  by `cascade_flag.py`)

For each piece of feedback:
1. Read the file. Locate the anchor/comment in the target.
2. Decide: **accept** / **partial** / **reject** / **defer**.
3. Apply edits to the target file (smallest edit that fixes the issue).
4. For audit files: append `# Resolution`, move to `audit/resolved/`.
5. For inline FIX comments: remove the comment after applying the fix.
6. Log: `## [HH:MM] audit | resolved <id> — <one-liner>`

### 7. `reflect`

**Trigger words:** reflect, 综合分析, 发现规律

Cross-source synthesis — discover patterns, validate conclusions, identify gaps.
Suggested: monthly, or after every 10 new sources.

Read `references/ops/op-reflect.md` for the full procedure:
Stage 0 (reverse validation) → Stage 1 (pattern scan) → Stage 2 (synthesis) → Stage 3 (gap report).

After all stages: update `wiki/overview.md`, rebuild index, log.

### 8. `compile`

**Trigger words:** compile, restructure, clean up the wiki, split, merge

(Re)structure wiki content. Always two phases — never skip Phase 1.

**Phase 1 — Inventory (read-only):** list all pages, identify split/merge/promote candidates,
present the full plan, **wait for user confirmation** before any writes.

**Phase 2 — Restructuring:** execute splits (create sub-pages, update wikilinks), merges
(single canonical page, keep old slug as redirect), rebuild index.

```bash
python3 .claude/skills/llm-wiki/scripts/build_index.py <wiki-root>
```

Log: `## [HH:MM] compile | <what you did>`

> Config lives in `CLAUDE.md` (the single config + schema file) — edit it directly;
> there is no separate config file or sync step. After changing the domain list,
> re-run `build_index.py` so the per-domain catalogs match. To update a vault's
> bundled skill copy, copy the skill folder over (`cp -R`).

---


## Anti-hallucination rules (MANDATORY)

**Rule 1 — Line-Level Source Annotation**
Every factual claim ends with: `(raw/articles/filename.md, L14-22)`
If line not identifiable: `(raw/filename.md, location unknown)` — flag in lint.
The citation points to the **raw file path**, NEVER to a `[[sources/...]]` page
wikilink — a compiled source page is not verifiable evidence. The source-page
wikilink belongs only in the page's `## Sources` section, listed **once**.
- WRONG: `... bond issuance. ([[sources/nvda-bonds]], L10)`
- RIGHT: `... bond issuance. (raw/clippings/nvda-bonds.md, L10)`
lint checks 9 and 14 enforce this.

**Rule 2 — Verbatim Numbers and Quotes**
Never paraphrase numeric data.
- WRONG: "The model has approximately 175 billion parameters."
- RIGHT: The model has "175 billion parameters" (raw/articles/gpt3.md, L8).

**Rule 3 — Label All Synthesis**
Cross-source inferences: prefix with `[synthesis]`. No line citation needed.

**Rule 4 — Self-Check Before Saving**
Every factual sentence must have `(raw/..., Lxx)` or `[synthesis]` before saving.

**Rule 5 — Mermaid for Diagrams**
Any flow, sequence, hierarchy, or state diagram must be mermaid. No ASCII art.

**Rule 6 — KaTeX for Formulas**
Any formula must be KaTeX: inline `$...$` or block `$$...$$`.

**Rule 7 — PDF Citation Format**
For PDF sources, cite by page: `(raw/pdfs/filename.pdf → raw/articles/slug.md, p.14)`

---

## Confidence gating

| Sources                        | Confidence       | How set                                  |
|--------------------------------|------------------|------------------------------------------|
| 1                              | `low`            | Auto                                     |
| 3+                             | `medium`         | Auto                                     |
| 5+ no major conflicts          | candidate `high` | LLM shows definition + sources to user   |
| User replies "confirm" or "ok" | `high`           | Only then                                |

Personal writing does NOT count toward `source_count`.
`confidence: high` = user's active endorsement. **Never automatic.**

---

## Bilingual naming & secondary language

When `CLAUDE.md` (§ Notes for the LLM) sets a language order, the **first-named language
is primary and leads; the second is annotated in parentheses**. For a `Chinese (primary)
+ English` vault, titles/headings read `中文名（English Name）` (e.g. `经济（Economy）`), the
`title:` frontmatter is the Chinese name, `aliases` holds both languages, and slugs/wikilinks
stay English. Full rules in `references/article-guide.md` § Bilingual Naming & Term Annotation.

---

## Reading the user

| User says                | You do                                              |
|--------------------------|-----------------------------------------------------|
| ingest raw/...           | INGEST (script + steps; default reads source directly) |
| ingest *.pdf             | INGEST — default direct read; vault `CLAUDE.md` may mandate a preprocess step |
| batch / multiple files   | BATCH_INGEST (batch_ingest.py)                      |
| Direct question          | QUERY — check wiki first                            |
| lint / health check      | LINT script                                         |
| deep lint                | Deep Lint (5 pages vs raw source)                   |
| compile / clean up       | COMPILE — Phase 1 inventory → confirm → Phase 2 writes |
| audit / fix errors       | AUDIT (script + process feedback)                   |
| I want to understand X   | ADD-QUESTION → `wiki/QUESTIONS.md`                  |
| merge / deduplicate      | COMPILE → merge flow                                |
| reflect / find patterns  | REFLECT — Stage 0 → 1 → 2 → 3                      |
| compare X vs Y / X and Y | COMPARISONS → `wiki/comparisons/<x>-vs-<y>.md`     |
| freshen / stale pages    | LINT --stale-only → list stale pages                |
| fix links / repair links / maintain | fix_links.py → repair broken links + stub missing targets, then lint to confirm |
| add a skill | Drop its folder in `.claude/skills/` — auto-discovered, no install step |
| edited CLAUDE.md / added a domain | Config lives in `CLAUDE.md` (no separate file, no sync step). If the domain list changed, re-run `build_index.py` so per-domain catalogs match. |

When user asks a question without specifying wiki, still check wiki first.
If wiki has no relevant content, say so explicitly, then answer from general
knowledge — clearly distinguishing between the two.

---

## Quality checklist (before saving any wiki edit)

**Anti-hallucination:**
- [ ] Every factual sentence: `(raw/filename.md, L42-45)` or `(raw/pdfs/..., p.N)`
- [ ] Every number/statistic: verbatim quote from source
- [ ] Every cross-source inference: labeled `[synthesis]`

**Anti-drift:**
- [ ] Evolution Log updated if definition changed
- [ ] Contradictions section updated if sources conflict
- [ ] `last_reviewed` date updated

**Format:**
- [ ] All frontmatter fields present
- [ ] Bilingual: `title:` is the primary-language name; `# H1`/first line leads with the primary language, secondary in `（）` (order per CLAUDE.md § Bilingual format); `aliases` has all languages
- [ ] Wikilinks: `[[category/english-lowercase-slug]]` (English slug, never Chinese)
- [ ] System files: `graph-excluded: true`
- [ ] Source pages: `raw_sha256` computed

**Confidence:**
- [ ] `source_count` = external sources only
- [ ] `confidence: high` NOT set without explicit user "confirm"

---

## References

- `references/schema-guide.md` — CLAUDE.md structure (single config + schema), YAML frontmatter specs, hierarchical index layout
- `references/article-guide.md` — line-level tracing, confidence gating, divide-and-conquer, extraction rules, secondary language annotation
- `references/log-guide.md` — log/ folder convention, allowed operations
- `references/audit-guide.md` — audit file format, anchor strategy, inline FIX comments, processing workflow
- `references/tooling-tips.md` — qmd setup, Obsidian config, web viewer
- `references/scaffold-wizard.md` — first-time setup interview (Questions 1–4: domains, primary language, secondary language, semantic search + scaffold command)
- `references/ops/op-reflect.md` — full reflect procedure (Stage 0–3)
- `.claude/skills/<name>/SKILL.md` — auto-discovered by Claude Code; cross-skill preferences live in each skill's `description`
