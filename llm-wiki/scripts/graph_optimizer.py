#!/usr/bin/env python3
"""
graph_optimizer.py — Analyze the wikilink graph to find structural weaknesses
and propose targeted fixes for the `optimize` operation.

Detects three classes of problems:

  1. Orphans / near-orphans  — pages with 0 or 1 inbound wikilinks.
     These are "dead ends" that qmd can't surface through graph traversal.

  2. Missing aliases  — a concept's human-readable title (or slug tokens)
     appear as plain text in other pages, but without a [[wikilink]] and without
     being listed in the concept's `aliases:` frontmatter field.
     qmd will miss these implicit references on semantic search.

  3. Missing domain tags  — a concept page is referenced by source pages from
     domains it doesn't declare. Cross-domain concepts should carry all their
     domain tags so domain-index queries return them.

All suggestions are proposals only. The agent presents them to the user and
applies batch frontmatter updates only after confirmation.

Usage:
  python3 graph_optimizer.py <wiki-root>
  python3 graph_optimizer.py <wiki-root> --pretty
  python3 graph_optimizer.py <wiki-root> --min-alias-occurrences 3
"""

from __future__ import annotations

import json
import re
import sys
import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path


# ─── Reused patterns (same as lint_wiki.py) ───────────────────────────────────
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?]]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    """Return (frontmatter_dict, body_text)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"').strip("'")
    body = text[m.end():]
    return fm, body


def _parse_aliases(path: Path) -> list[str]:
    """Extract items from the `aliases:` YAML list field."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return []
    end = text.find("\n---", 3)
    if end == -1:
        return []
    aliases: list[str] = []
    in_aliases = False
    for line in text[3:end].splitlines():
        stripped = line.strip()
        if re.match(r'^aliases\s*:', stripped):
            in_aliases = True
            # Handle inline list: aliases: [a, b]
            inline = re.search(r'\[(.+)\]', stripped)
            if inline:
                for item in inline.group(1).split(","):
                    aliases.append(item.strip().strip('"').strip("'"))
                in_aliases = False
            continue
        if in_aliases:
            if stripped.startswith("- "):
                aliases.append(stripped[2:].strip().strip('"').strip("'"))
            elif stripped and not stripped.startswith("#"):
                in_aliases = False
    return [a.lower() for a in aliases if a]


def _wikilinks_in(text: str) -> list[str]:
    """Return all wikilink targets from body text, normalised to lowercase."""
    return [t.strip().lower() for t in WIKILINK_RE.findall(text)]


def _slug_variants(slug: str, title: str) -> set[str]:
    """Generate plain-text variants of a concept that might appear without [[linking]]."""
    variants: set[str] = set()
    # slug itself: "model-context-protocol" → "model context protocol"
    variants.add(slug.replace("-", " ").lower())
    # title from frontmatter
    if title:
        variants.add(title.lower())
    # remove common prefixes for concept slugs that live in subdirs: "concepts/foo" → "foo"
    bare = slug.split("/")[-1]
    variants.add(bare.replace("-", " ").lower())
    # acronym: first letter of each word
    words = bare.replace("-", " ").split()
    if len(words) >= 2:
        acronym = "".join(w[0] for w in words if w).lower()
        if len(acronym) >= 2:
            variants.add(acronym)
    # strip trailing "s" for plurals
    for v in list(variants):
        if v.endswith("s") and len(v) > 4:
            variants.add(v[:-1])
    return {v for v in variants if len(v) >= 3}


def _collect_wiki_pages(wiki_dir: Path) -> list[Path]:
    """Return all non-system wiki markdown files."""
    system_names = {"index.md", "overview.md", "QUESTIONS.md"}
    system_dirs = {"index", "templates"}
    result = []
    for p in wiki_dir.rglob("*.md"):
        if p.name.startswith(".") or p.name in system_names:
            continue
        if any(part in system_dirs for part in p.parts):
            continue
        result.append(p)
    return result


# ─── 1. Build wikilink graph ──────────────────────────────────────────────────

def build_link_graph(
    wiki_dir: Path, root: Path
) -> tuple[dict[str, set[str]], dict[str, int]]:
    """
    Returns:
      outbound: page_rel → set of target slugs it links to
      inbound_count: page_rel → number of pages that link to it
    """
    pages = _collect_wiki_pages(wiki_dir)
    outbound: dict[str, set[str]] = {}
    inbound_count: dict[str, int] = defaultdict(int)

    for p in pages:
        rel = str(p.relative_to(root))
        _, body = _parse_frontmatter(p)
        links = set(_wikilinks_in(body))
        outbound[rel] = links
        for link in links:
            # Normalise: strip leading category prefix if present
            bare = link.split("/")[-1]
            inbound_count[bare] += 1

    # Ensure every page has an entry
    for p in pages:
        bare = p.stem.lower()
        if bare not in inbound_count:
            inbound_count[bare] = 0

    return outbound, dict(inbound_count)


# ─── 2. Orphan detection ─────────────────────────────────────────────────────

def find_orphans(
    wiki_dir: Path, root: Path, inbound_count: dict[str, int]
) -> tuple[list[dict], list[dict]]:
    """Return (orphans, near_orphans) — pages with 0 and 1 inbound links."""
    concept_dir = wiki_dir / "concepts"
    entity_dir = wiki_dir / "entities"

    orphans, near_orphans = [], []
    for category_dir in [concept_dir, entity_dir]:
        if not category_dir.is_dir():
            continue
        for p in sorted(category_dir.rglob("*.md")):
            if p.name.startswith("."):
                continue
            bare = p.stem.lower()
            count = inbound_count.get(bare, 0)
            entry = {
                "page": str(p.relative_to(root)),
                "slug": bare,
                "inbound_links": count,
            }
            if count == 0:
                orphans.append(entry)
            elif count == 1:
                near_orphans.append(entry)

    return orphans, near_orphans


# ─── 3. Missing alias detection ───────────────────────────────────────────────

def find_missing_aliases(
    wiki_dir: Path,
    root: Path,
    outbound: dict[str, set[str]],
    min_occurrences: int = 2,
) -> list[dict]:
    """
    For each concept page, check whether its title/slug variants appear as
    plain text in other wiki pages without being wikilinked or aliased.
    """
    concept_dir = wiki_dir / "concepts"
    if not concept_dir.is_dir():
        return []

    # Build map: page_rel → (body_text, linked_targets)
    all_pages = _collect_wiki_pages(wiki_dir)
    page_bodies: dict[str, str] = {}
    for p in all_pages:
        _, body = _parse_frontmatter(p)
        page_bodies[str(p.relative_to(root))] = body.lower()

    suggestions = []

    for concept_page in sorted(concept_dir.rglob("*.md")):
        if concept_page.name.startswith("."):
            continue

        fm, _ = _parse_frontmatter(concept_page)
        concept_rel = str(concept_page.relative_to(root))
        slug = concept_page.stem.lower()
        title = fm.get("title", "").lower()
        current_aliases = _parse_aliases(concept_page)

        variants = _slug_variants(slug, title)
        # Remove variants already in aliases or that are the slug itself
        known = current_aliases | {slug, slug.replace("-", " ")}
        candidates = {v for v in variants if v not in known and len(v) >= 3}

        if not candidates:
            continue

        alias_evidence: dict[str, list[dict]] = defaultdict(list)

        for page_rel, body_lower in page_bodies.items():
            if page_rel == concept_rel:
                continue
            linked = outbound.get(page_rel, set())
            # Skip if page already wikilinks to this concept
            if slug in linked or concept_rel.replace("wiki/", "") in linked:
                continue

            for variant in candidates:
                # Word-boundary match (avoid partial word hits)
                pattern = r'(?<![a-z])' + re.escape(variant) + r'(?![a-z])'
                matches = re.findall(pattern, body_lower)
                if matches:
                    # Extract a short snippet for evidence
                    m = re.search(pattern, body_lower)
                    if m:
                        start = max(0, m.start() - 40)
                        snippet = "..." + body_lower[start: m.end() + 40].replace("\n", " ") + "..."
                        alias_evidence[variant].append({
                            "found_in": page_rel,
                            "occurrences": len(matches),
                            "snippet": snippet[:120],
                        })

        # Keep only variants with enough evidence
        actionable: list[dict] = []
        for variant, evidence in alias_evidence.items():
            total = sum(e["occurrences"] for e in evidence)
            if total >= min_occurrences:
                actionable.append({
                    "variant": variant,
                    "total_occurrences": total,
                    "evidence": evidence[:3],
                })

        if actionable:
            actionable.sort(key=lambda x: -x["total_occurrences"])
            suggestions.append({
                "page": concept_rel,
                "slug": slug,
                "current_aliases": current_aliases,
                "suggested_aliases": [a["variant"] for a in actionable],
                "evidence": actionable,
            })

    return suggestions


# ─── 4. Missing domain tag detection ─────────────────────────────────────────

def find_missing_domains(
    wiki_dir: Path, root: Path, outbound: dict[str, set[str]]
) -> list[dict]:
    """
    For each concept page, look at which source pages reference it.
    If those sources span domains the concept doesn't declare, suggest adding them.
    """
    concept_dir = wiki_dir / "concepts"
    source_dir = wiki_dir / "sources"
    if not concept_dir.is_dir() or not source_dir.is_dir():
        return []

    # Build source → domain map
    source_domains: dict[str, str] = {}
    for sp in source_dir.rglob("*.md"):
        if sp.name.startswith("."):
            continue
        fm, _ = _parse_frontmatter(sp)
        domain = fm.get("domain", "").strip()
        if domain:
            source_domains[str(sp.relative_to(root))] = domain

    # Build concept slug → its declared domains
    concept_domains: dict[str, list[str]] = {}
    concept_paths: dict[str, Path] = {}
    for cp in concept_dir.rglob("*.md"):
        if cp.name.startswith("."):
            continue
        fm, _ = _parse_frontmatter(cp)
        slug = cp.stem.lower()
        raw_domain = fm.get("domain", fm.get("domains", ""))
        domains = [d.strip() for d in raw_domain.split(",") if d.strip()]
        concept_domains[slug] = domains
        concept_paths[slug] = cp

    # For each source, find which concepts it links to and accumulate domains
    concept_referenced_by_domains: dict[str, set[str]] = defaultdict(set)
    for page_rel, links in outbound.items():
        if not page_rel.startswith("wiki/sources/"):
            continue
        source_domain = source_domains.get(page_rel, "")
        if not source_domain:
            continue
        for link in links:
            bare = link.split("/")[-1]
            if bare in concept_domains:
                concept_referenced_by_domains[bare].add(source_domain)

    suggestions = []
    for slug, referenced_domains in concept_referenced_by_domains.items():
        declared = set(concept_domains.get(slug, []))
        missing = referenced_domains - declared
        if missing:
            cp = concept_paths.get(slug)
            suggestions.append({
                "page": str(cp.relative_to(root)) if cp else f"wiki/concepts/{slug}.md",
                "slug": slug,
                "current_domains": sorted(declared),
                "suggested_domains": sorted(missing),
                "referenced_by_domains": sorted(referenced_domains),
            })

    return suggestions


# ─── Main ─────────────────────────────────────────────────────────────────────

def analyze(root_str: str, min_alias_occurrences: int = 2,
            pretty: bool = False) -> int:
    root = Path(root_str).resolve()
    if not (root / "CLAUDE.md").is_file():
        print(f"Error: {root} is not a valid llm-wiki vault (no CLAUDE.md).",
              file=sys.stderr)
        return 1

    wiki_dir = root / "wiki"
    if not wiki_dir.is_dir():
        print(f"Error: wiki/ directory not found at {wiki_dir}", file=sys.stderr)
        return 1

    pages = _collect_wiki_pages(wiki_dir)
    outbound, inbound_count = build_link_graph(wiki_dir, root)
    orphans, near_orphans = find_orphans(wiki_dir, root, inbound_count)
    alias_suggestions = find_missing_aliases(
        wiki_dir, root, outbound, min_occurrences=min_alias_occurrences
    )
    domain_suggestions = find_missing_domains(wiki_dir, root, outbound)

    actionable_aliases = len(alias_suggestions)
    actionable_domains = len(domain_suggestions)
    total_links = sum(len(v) for v in outbound.values())

    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "wiki_root": str(root),
        "graph_stats": {
            "total_pages": len(pages),
            "total_links": total_links,
            "orphan_pages": orphans,
            "near_orphan_pages": near_orphans,
        },
        "alias_suggestions": alias_suggestions,
        "domain_suggestions": domain_suggestions,
        "summary": {
            "orphan_count": len(orphans),
            "near_orphan_count": len(near_orphans),
            "alias_suggestions_count": actionable_aliases,
            "domain_suggestions_count": actionable_domains,
            "actionable_suggestions": len(orphans) + actionable_aliases + actionable_domains,
        },
    }

    if pretty:
        _print_pretty(report)
    else:
        print(json.dumps(report, indent=2))

    return 0


def _print_pretty(report: dict) -> None:
    gs = report["graph_stats"]
    s = report["summary"]
    print("=" * 60)
    print("LLM-Wiki Graph Optimizer Report")
    print(f"Generated: {report['generated']}")
    print(f"Pages: {gs['total_pages']}  |  Links: {gs['total_links']}")
    print("=" * 60)

    print(f"\n── Orphan Pages ({s['orphan_count']}) ────────────────────────────")
    if gs["orphan_pages"]:
        for p in gs["orphan_pages"]:
            print(f"  {p['page']}")
    else:
        print("  None ✓")

    print(f"\n── Near-Orphan Pages ({s['near_orphan_count']}) ─────────────────")
    if gs["near_orphan_pages"]:
        for p in gs["near_orphan_pages"]:
            print(f"  {p['page']}  (1 inbound link)")
    else:
        print("  None ✓")

    print(f"\n── Missing Aliases ({s['alias_suggestions_count']}) ─────────────")
    for s_ in report["alias_suggestions"]:
        print(f"\n  {s_['page']}")
        print(f"    Current aliases: {s_['current_aliases'] or '(none)'}")
        print(f"    Suggest adding:  {s_['suggested_aliases']}")
        for ev in s_["evidence"][:2]:
            print(f"    Found in: {ev['found_in']}  ({ev['total_occurrences']}×)")
            print(f"    Snippet:  {ev['snippet']}")
    if not report["alias_suggestions"]:
        print("  None ✓")

    print(f"\n── Missing Domain Tags ({s['domain_suggestions_count']}) ─────────")
    for d in report["domain_suggestions"]:
        print(f"\n  {d['page']}")
        print(f"    Current domains:  {d['current_domains'] or '(none)'}")
        print(f"    Suggested add:    {d['suggested_domains']}")
        print(f"    Referenced from:  {d['referenced_by_domains']}")
    if not report["domain_suggestions"]:
        print("  None ✓")

    print(f"\n── Summary ──────────────────────────────────────────────────────")
    print(f"  Orphans:             {s['orphan_count']}")
    print(f"  Near-orphans:        {s['near_orphan_count']}")
    print(f"  Alias suggestions:   {s['alias_suggestions_count']}")
    print(f"  Domain suggestions:  {s['domain_suggestions_count']}")
    print(f"  Total actionable:    {s['actionable_suggestions']}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze wikilink graph structure and propose alias/domain fixes."
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--pretty", action="store_true",
                        help="Human-readable output instead of JSON")
    parser.add_argument("--min-alias-occurrences", type=int, default=2, metavar="N",
                        help="Minimum occurrences of a variant to suggest as alias (default: 2)")
    args = parser.parse_args()
    sys.exit(analyze(args.wiki_root,
                     min_alias_occurrences=args.min_alias_occurrences,
                     pretty=args.pretty))


if __name__ == "__main__":
    main()
