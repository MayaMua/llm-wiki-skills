#!/usr/bin/env python3
"""
scaffold.py — Bootstrap a new LLM Wiki directory structure.

Usage:
    python3 scaffold.py <wiki-root> "<Topic Title>"
    python3 scaffold.py <wiki-root> "<Topic>" --domains "AI,Finance" --primary-lang zh --lang en
    python3 scaffold.py <wiki-root>                # interactive mode

Example:
    python3 scaffold.py ~/wikis/ai-research "AI Research" --domains "AI/ML,Technology" --primary-lang zh --lang en

Creates the full wiki directory tree including CLAUDE.md (the single config +
schema file), wiki/index.md, all templates, log/, audit/, and the first log entry.
"""

import os
import sys
import argparse
from datetime import date, datetime


def scaffold(root: str, title: str, domains: list[str], lang: str,
             primary_lang: str = "English", private_zones: list = None,
             search_tool: str = "none") -> None:
    """Create the full wiki directory tree and initial files."""
    today = date.today()
    today_iso = today.isoformat()
    today_compact = today.strftime("%Y%m%d")
    now_hm = datetime.now().strftime("%H:%M")

    # ── Create directories ────────────────────────────────────────────────────
    dirs = [
        "raw/articles",
        "raw/papers",
        "raw/notes",
        "raw/refs",
        "raw/images",
        "raw/pdfs",
        "raw/clippings",
        "raw/personal",
        "wiki/sources",
        "wiki/concepts",
        "wiki/entities",
        "wiki/comparisons",
        "wiki/synthesis",
        "wiki/templates",
        "wiki/index",
        "outputs/queries",
        "log",
        "audit",
        "audit/resolved",
    ]

    for d in dirs:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    print(f"✓ Created directory tree under {root}/")

    # .gitkeep for empty dirs
    for gk in ["audit/.gitkeep", "audit/resolved/.gitkeep"]:
        _write(root, gk, "")

    # ── Determine language config ─────────────────────────────────────────────
    primary_lang_display = primary_lang.capitalize() if primary_lang else "English"
    lang_display = "None" if lang.lower() in ("none", "no", "en", "english", "") else lang.capitalize()
    # ── CLAUDE.md (single config + schema file) ───────────────────────────────
    domains_bullets = "\n".join(f"- {d.strip()}" for d in domains)
    if lang_display != "None":
        lang_note = f"{primary_lang_display} + {lang_display} (bilingual)"
    else:
        lang_note = primary_lang_display

    # ── Private zones (optional) ──────────────────────────────────────────────
    private_zones = [z.strip().strip("/") for z in (private_zones or []) if z.strip()]
    for z in private_zones:
        os.makedirs(os.path.join(root, z), exist_ok=True)
        _write(root, f"{z}/.gitkeep", "")
    if private_zones:
        print(f"✓ Created private zone(s): {', '.join(private_zones)}")
        pz_bullets = "\n".join(f"- `{z}/`" for z in private_zones)
        private_zones_section = f"""## Private zones — MANDATORY, no exceptions

These paths hold sensitive material (clinical/PHI, personal, or confidential data).

**FORBIDDEN:** any direct read (`Read`, `Bash(cat ...)`, etc.) on these paths.
**REQUIRED:** to use a protected file, route it through a redaction / de-identification
step that writes a safe artifact into `raw/`, then ingest *that* — never the original.
These paths are excluded from ingest and never cited in `wiki/`.

{pz_bullets}

> For a hard guarantee (not just agent convention), also add a `Read(...)` deny rule
> for these paths to `.claude/settings.json` (the `update-config` skill can do this).

"""
    else:
        private_zones_section = ""

    # ── Search config (qmd is opt-in, off by default) ─────────────────────────
    search_tool = (search_tool or "none").strip().lower()
    if search_tool == "qmd":
        import re as _re
        qmd_collection = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "wiki"
        search_section = f"""## Search

- search_tool: qmd
- qmd_collection: {qmd_collection}

> Semantic search via qmd is ON. One-time setup:
> `qmd collection add wiki/ --name {qmd_collection}`, then `qmd embed` after each ingest.
> See `references/tooling-tips.md`. Set `search_tool: none` to turn it off.

"""
    else:
        search_section = """## Search

- search_tool: none      # set to `qmd` to enable semantic search (see references/tooling-tips.md)
- qmd_collection:        # collection name you pass to `qmd collection add wiki/ --name <name>`

"""

    claude_md = f"""# {title} Knowledge Base

> Schema document — read at the start of every session together with `wiki/index.md`.
> Update after every major compile, ingest batch, or structural change.

## Scope

What this wiki covers:
{domains_bullets}

What this wiki deliberately excludes:
- <define out-of-scope areas>

## Operations

This wiki follows the llm-wiki skill's eight operations:
`scaffold`, `ingest`, `batch_ingest`, `query`, `lint`, `audit`, `reflect`, `compile`.
Every operation appends an entry to `log/YYYYMMDD.md`.

## Naming conventions

### Pages
- **Source pages** (`wiki/sources/`): kebab-case slug.
- **Concept pages** (`wiki/concepts/`): kebab-case slug.
- **Entity pages** (`wiki/entities/`): kebab-case slug.
- **Comparison pages** (`wiki/comparisons/`): `<a>-vs-<b>` slug. Pairwise only.
- **Synthesis pages** (`wiki/synthesis/`): kebab-case slug. Multi-source patterns.

### Wikilinks
- Always `[[category/english-lowercase-slug]]`.

### Diagrams and formulas
- All diagrams are **mermaid**. No ASCII art.
- All formulas are **KaTeX** (inline `$...$` or block `$$...$$`).

### Raw file policy
- Small text sources → copy into `raw/<subfolder>/`.
- Large binaries → create `raw/refs/<slug>.md` pointer file.

## Current articles

### Concepts
*(none)*

### Entities
*(none)*

### Comparisons
*(none)*

### Sources
*(none)*

### Synthesis
*(none)*

## Open research questions
- <What do you want to understand better?>

## Research gaps
Sources to ingest:
- [ ] <URL or paper title> — why it's relevant

## Audit backlog
*(none — run `python3 .claude/skills/llm-wiki/scripts/audit_review.py {root} --open` to refresh)*

{private_zones_section}{search_section}## Notes for the LLM
- Language: {lang_note}
- Tone: neutral
- Depth: survey-level
- Handling contradictions: state both, cite each, add to Open Research Questions.
"""
    _write(root, "CLAUDE.md", claude_md)
    print("✓ Created CLAUDE.md")

    # ── wiki/index.md ─────────────────────────────────────────────────────────
    index_md = f"""---
type: system-index
graph-excluded: true
updated: {today_iso}
---

# Index — {title}

> Domains: {', '.join(d.strip() for d in domains)} | Articles: 0

## 🔖 Navigation
- [[#Concepts]] · [[#Entities]] · [[#Comparisons]] · [[#Sources]] · [[#Synthesis]] · [[#Open Questions]]

## Concepts
*(none yet)*

## Entities
*(none yet)*

## Comparisons
*(none yet)*

## Sources (Processed)
*(none yet)*

## Sources (Unprocessed)
*(none yet)*

## Synthesis
*(none yet)*

## Open Questions
- <First research question>

## Recent Outputs
*(none yet)*
"""
    _write(root, "wiki/index.md", index_md)
    print("✓ Created wiki/index.md")

    # ── wiki/overview.md ──────────────────────────────────────────────────────
    overview_md = f"""---
type: system-overview
graph-excluded: true
updated: {today_iso}
---

# Knowledge Base Overview

## Health Dashboard

| Metric                       | Count |
| ---------------------------- | ----- |
| Sources (processed)          | 0     |
| Sources (unprocessed)        | 0     |
| Concepts (high confidence)   | 0     |
| Concepts (medium confidence) | 0     |
| Concepts (low confidence)    | 0     |
| Entities                     | 0     |
| Synthesis pages              | 0     |
| Open questions               | 0     |
| Stale pages                  | 0     |
| Orphan pages                 | 0     |

## Domain Coverage

## Knowledge Gaps
"""
    _write(root, "wiki/overview.md", overview_md)
    print("✓ Created wiki/overview.md")

    # ── wiki/QUESTIONS.md ─────────────────────────────────────────────────────
    questions_md = """---
type: system-questions
graph-excluded: true
---

# Open Questions

## Unanswered

## Answered
"""
    _write(root, "wiki/QUESTIONS.md", questions_md)
    print("✓ Created wiki/QUESTIONS.md")

    # ── Templates ─────────────────────────────────────────────────────────────
    _write_templates(root, today_iso)
    print("✓ Created wiki/templates/ (6 templates, incl. comparison-template)")

    # ── log/<today>.md ────────────────────────────────────────────────────────
    pz_log = f"\n- Private zones: {', '.join(private_zones)}" if private_zones else ""
    log_md = f"""# {today_iso}

## [{now_hm}] scaffold | Initialized {title} knowledge base
- Created directory tree (raw/, wiki/, log/, audit/, outputs/)
- Created CLAUDE.md schema template (single config + schema file)
- Created wiki/index.md category skeleton
- Created 6 page templates (incl. comparison-template)
- Domains: {', '.join(d.strip() for d in domains)}
- Language: {lang_note}{pz_log}
"""
    _write(root, f"log/{today_compact}.md", log_md)
    print(f"✓ Created log/{today_compact}.md")

    # ── Bundle the llm-wiki skill into the vault (always) ─────────────────────
    _bundle_skill(root)
    script_prefix = ".claude/skills/llm-wiki/scripts"

    # ── Final summary ─────────────────────────────────────────────────────────
    pz_note = ""
    if private_zones:
        pz_note = (f"\n🔒 Private zone(s): {', '.join(private_zones)} — declared MANDATORY in CLAUDE.md "
                   f"(agent never reads them directly).\n"
                   f"   For hard enforcement, add a Read(...) deny for these to .claude/settings.json "
                   f"(the update-config skill can do it).\n")
    print(f"""
✅ Wiki scaffolded at: {root}/

The llm-wiki skill is bundled into this vault at .claude/skills/llm-wiki/, so the
vault is self-contained and portable — the commands below resolve locally.
{pz_note}
Next steps:
  1. Review and customize CLAUDE.md — define scope and naming conventions
  2. Add sources to raw/ (Obsidian Web Clipper for web; put PDFs in raw/pdfs/)
  3. Run ingest:       tell your LLM agent "ingest raw/<file>.md"
  4. For PDFs:         tell your agent "ingest raw/pdfs/<file>.pdf"
  5. Rebuild index:    python3 {script_prefix}/build_index.py {root}
  6. Ask questions:    "what does the wiki say about X?"
  7. Run lint:         python3 {script_prefix}/lint_wiki.py {root}
  8. Stale check:      python3 {script_prefix}/lint_wiki.py {root} --stale-only
  9. Process feedback: python3 {script_prefix}/audit_review.py {root} --open
""")


def _write_templates(root: str, today_iso: str) -> None:
    """Create all 5 page template files."""

    # Source template
    _write(root, "wiki/templates/source-template.md", f"""---
type: source-summary
title: ""
date: {today_iso}
source_url: ""
domain: ""
author: ""
tags: [wiki, wiki/source]
processed: true
raw_file: ""
raw_sha256: ""
last_verified: {today_iso}
possibly_outdated: false
language: "English"
canonical_source: ""
claims_requiring_verification: []
  # List verbatim strings for any number, date, percentage, or threshold in this source.
  # Format: "exact text from source" (raw/path/file.md, Lxx)
  # Example: "2% discount if paid within 10 days" (raw/contracts/vendor.md, L14)
  # lint_wiki.py check 13 verifies each string exists verbatim in the raw file.
---

# {{Title}}

## Summary

{{2-4 sentences. Every factual claim: (raw/articles/filename.md, L14-22)}}

## Key Points

- Point one. (raw/articles/filename.md, L45)

## Concepts Extracted

- [[concepts/concept-slug]]

## Entities Extracted

- [[entities/entity-slug]]

## Contradictions

## My Notes
""")

    # Personal writing template
    _write(root, "wiki/templates/personal-writing-template.md", f"""---
type: personal-writing
title: ""
date: {today_iso}
status: draft
topic_tags: []
confidence_at_writing: medium
superseded_by: ""
raw_file: ""
raw_sha256: ""
last_verified: {today_iso}
tags: [wiki, wiki/source]
processed: true
---

# {{Title}}

## Core Argument

## Key Claims

## Evidence Referenced

## Limitations
""")

    # Concept template
    _write(root, "wiki/templates/concept-template.md", f"""---
type: concept
title: ""
date: {today_iso}
updated: {today_iso}
tags: [wiki, wiki/concept]
source_count: 0
confidence: low
domain_volatility: medium
last_reviewed: {today_iso}
aliases: []
---

# {{Primary Name}}（{{Secondary Language Name}}）

## Definition

{{2-4 sentences. Every factual sentence: (raw/file.md, L14-22)}}

## Key Points

- Point with citation. (raw/articles/source.md, L45)
- [synthesis] Cross-source insight — labeled, no line citation needed.

## My Position

## Contradictions

## Sources

- [[sources/source-slug]]

## Evolution Log

- {today_iso} (1 source): Created from [[sources/first-source]].
""")

    # Entity template
    _write(root, "wiki/templates/entity-template.md", f"""---
type: entity
title: ""
date: {today_iso}
tags: [wiki, wiki/entity]
entity_type: person
aliases: []
---

# {{Name}}

## Description

## Key Contributions / Features

## Related Concepts

## Sources
""")

    # Synthesis template
    _write(root, "wiki/templates/synthesis-template.md", f"""---
type: synthesis
title: ""
date: {today_iso}
tags: [wiki, wiki/synthesis]
source_count: 0
confidence: low
---

# {{Synthesis Title}}

## Thesis

## Evidence

## Counter-Evidence

## Synthesis

## Confidence Notes

## Limitations

## Sources
""")

    # Comparison template
    _write(root, "wiki/templates/comparison-template.md", f"""---
type: comparison
title: ""
date: {today_iso}
updated: {today_iso}
tags: [wiki, wiki/comparison]
subjects: ["", ""]
confidence: low
---

# {{A}} vs {{B}}

## Summary

{{One sentence stating the key difference.}} [synthesis]

## Comparison Table

| Dimension | {{A}} | {{B}} |
|-----------|-------|-------|
| | | |

## {{A}} — Strengths

- Point with citation. (raw/articles/source.md, L45)

## {{B}} — Strengths

- Point with citation. (raw/articles/source.md, L67)

## When to use {{A}}

## When to use {{B}}

## Conflicts between sources

## Sources

- [[sources/source-slug]]

## Evolution Log

- {today_iso} (1 source): Created from [[sources/first-source]].
""")


def _bundle_skill(root: str) -> None:
    """Copy the entire llm-wiki skill into <root>/.claude/skills/llm-wiki/ so the new
    vault is self-contained: its documented `.claude/skills/llm-wiki/scripts/...`
    commands resolve locally and the vault stays portable (move/share/clone it and it
    works). Always runs at scaffold time.
    """
    import shutil
    from pathlib import Path

    skill_src = Path(__file__).resolve().parent.parent            # <skill-root>/scripts/ → <skill-root>
    skill_dst = Path(root).resolve() / ".claude" / "skills" / "llm-wiki"

    if skill_src == skill_dst:
        print("  → llm-wiki skill already lives at the vault path; not re-copying")
        return
    if skill_dst.is_relative_to(skill_src) or skill_src.is_relative_to(skill_dst):
        print("  ⚠ skill source and vault path overlap; skipping bundle to avoid recursion")
        return

    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        skill_src, skill_dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*-workspace", ".DS_Store"),
        dirs_exist_ok=True,
    )
    print("✓ Bundled llm-wiki skill → .claude/skills/llm-wiki/ (SKILL.md + references/ + scripts/)")


def _write(root: str, path: str, content: str) -> None:
    """Write content to a file, creating parent directories as needed."""
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap a new LLM Wiki directory structure.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("title", nargs="?", default=None,
                        help="Topic title for the wiki")
    parser.add_argument("--domains", type=str, default=None,
                        help='Comma-separated domains, e.g. "AI,Finance,Technology"')
    parser.add_argument("--primary-lang", type=str, default=None,
                        help='Primary language for wiki content: "English", "zh", "ja", etc.')
    parser.add_argument("--lang", type=str, default=None,
                        help='Secondary language for bilingual annotations: "zh", "ja", "none", etc.')
    parser.add_argument("--private-zones", type=str, default=None,
                        help='Comma-separated private-zone folder name(s) the agent must NEVER read '
                             'directly, e.g. "private" or "private,raw/journal". Blank/omit for none.')
    parser.add_argument("--search", type=str, default="none", choices=["none", "qmd"],
                        help='Search backend recorded in CLAUDE.md § Search. "none" (default, index '
                             'scanning) or "qmd" (semantic; needs qmd installed + a collection).')
    args = parser.parse_args()

    # ── Interactive fallback ──────────────────────────────────────────────────
    title = args.title
    if not title:
        title = input("What is the topic title for this wiki? ").strip()
        if not title:
            print("Error: Topic title is required.", file=sys.stderr)
            sys.exit(1)

    domains_str = args.domains
    if not domains_str:
        print("\nWhat knowledge domains do you want this wiki to cover?")
        print("Examples: Economics · Finance · Technology · AI/ML · Science")
        print('Type your domains separated by commas, or "General" for everything.')
        domains_str = input("> ").strip()
        if not domains_str:
            domains_str = "General"

    domains = [d.strip() for d in domains_str.split(",") if d.strip()]

    primary_lang = args.primary_lang
    if primary_lang is None:
        print("\nWhat is the primary language for wiki content?")
        print("Examples: English · Chinese · Japanese · French  (default: English)")
        primary_lang = input("> ").strip()
        if not primary_lang:
            primary_lang = "English"

    lang = args.lang
    if lang is None:
        print("\nWould you like a secondary language for bilingual term annotations?")
        print("Options: no · zh (Chinese) · ja (Japanese) · en (English) · other")
        lang = input("> ").strip()
        if not lang or lang.lower() in ("no", "n", "none"):
            lang = "None"

    # Private zones — ask only in an interactive terminal; never block a piped/agent run.
    private_zones_str = args.private_zones
    if private_zones_str is None:
        if sys.stdin.isatty():
            print("\nDo you need a private zone?")
            print("A private zone is a folder the agent NEVER reads directly — for sensitive material")
            print("(clinical/PHI, personal journals, confidential records). It is kept out of ingest and")
            print("never enters the wiki; to use a file you redact it into raw/ first. Recommended for")
            print("anything you would not want summarized into wiki pages.")
            print('Enter folder name(s), comma-separated (e.g. "private" or "private,raw/journal"),')
            print("or leave blank for none.")
            try:
                private_zones_str = input("> ").strip()
            except EOFError:        # piped / no real stdin → treat as "none"
                private_zones_str = ""
        else:
            private_zones_str = ""
    private_zones = [z.strip() for z in (private_zones_str or "").split(",") if z.strip()]

    scaffold(args.wiki_root, title, domains, lang, primary_lang=primary_lang,
             private_zones=private_zones, search_tool=args.search)


if __name__ == "__main__":
    main()
