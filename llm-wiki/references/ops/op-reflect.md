# Operation: reflect

Cross-source synthesis to discover patterns, validate conclusions, and find knowledge gaps.
Suggested frequency: monthly, or after every 10 new sources.

---

## Stage 0 — Reverse validation (mandatory before any synthesis write)

Before writing any synthesis conclusion, actively search for contradicting evidence:

```bash
qmd query "counter-arguments to <candidate conclusion>" -c <qmd_collection> -n 5
```

If qmd is not configured: manually scan concept pages' Contradictions sections.

If no contradicting sources found, add to the synthesis page Limitations section:
```
⚠ Echo chamber risk: no contradicting sources found — conclusions may have confirmation bias
```

---

## Stage 1 — Pattern scan (read-only, no writes yet)

Use qmd to identify cross-source patterns, hidden associations, and potential contradictions:

```bash
qmd query "<candidate pattern>" -c <qmd_collection> -n 10
```

If qmd is not configured: scan `wiki/index.md` and domain indexes manually.

Identify candidates for synthesis — do not write anything at this stage.

---

## Stage 2 — Deep synthesis

For evidence-backed candidates, write `wiki/synthesis/<topic>-synthesis.md`
using `wiki/templates/synthesis-template.md`.

Apply Stage 0 reverse validation to each conclusion before writing.

---

## Stage 3 — Gap Analysis → `outputs/gap-report-YYYY-MM-DD.md`

Report:
- Pages with `source_count: 1` created >30 days ago (isolated concepts needing more sources)
- Concepts mentioned in 2+ sources but no dedicated wiki page (hidden blind spots)
- Domain areas with <3 concept pages (sparse coverage)

---

## After all stages

- Update `wiki/overview.md` Health Dashboard
- Run `python3 .claude/skills/llm-wiki/scripts/build_index.py <wiki-root>`
- Log: `## [HH:MM] reflect | N patterns found, M synthesis pages written, K gaps identified`
