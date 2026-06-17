#!/usr/bin/env python3
"""
audit_review.py — List and group audit feedback by target file.

Scans TWO feedback surfaces:
  1. audit/*.md — YAML-anchored feedback files from Obsidian plugin / web viewer
  2. wiki/**/*.md — inline <!-- FIX: ... --> comments from direct editing

Usage:
    python3 audit_review.py <wiki-root> [--open|--resolved|--all] [--json]

Examples:
    python3 audit_review.py ~/wikis/ai-research --open
    python3 audit_review.py ~/wikis/ai-research --all --json
    python3 audit_review.py ~/wikis/ai-research --resolved

Exit codes:
  0 — done (always, regardless of audit count)
"""

from __future__ import annotations  # PEP 604 `X | None` in signatures → lazy, works on py3.9

import json
import os
import re
import sys
import argparse
from collections import defaultdict
from pathlib import Path


# ── Regex patterns ────────────────────────────────────────────────────────────

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Matches single-line: <!-- FIX: some text -->
# and multi-line: <!-- FIX:\nsome text\nmore text\n-->
FIX_COMMENT_RE = re.compile(
    r"<!--\s*FIX:\s*(.*?)\s*-->",
    re.DOTALL
)

SEVERITY_ORDER = {"error": 0, "warn": 1, "suggest": 2, "info": 3}


# ── Frontmatter parsing ──────────────────────────────────────────────────────

def parse_frontmatter(text: str) -> dict | None:
    """Minimal YAML frontmatter parser."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    body = m.group(1)
    result: dict = {}
    for line in body.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        val = rest.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            result[key] = [
                p.strip().strip("\"'")
                for p in inner.split(",") if p.strip()
            ]
        elif val.startswith('"') and val.endswith('"'):
            result[key] = val[1:-1].replace("\\n", "\n").replace('\\"', '"')
        elif val.startswith("'") and val.endswith("'"):
            result[key] = val[1:-1]
        else:
            result[key] = val
    return result


def extract_comment_one_line(text: str) -> str:
    """Pull the first non-empty line of the # Comment section."""
    in_comment = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("# comment"):
            in_comment = True
            continue
        if not in_comment:
            continue
        if not stripped:
            continue
        if stripped.startswith("#"):
            break
        return stripped[:100]
    return "(no comment body)"


# ── Scan audit/ directory ─────────────────────────────────────────────────────

def scan_audit_files(root: Path, mode: str) -> list[dict]:
    """Scan audit/*.md and audit/resolved/*.md for feedback files."""
    audit_dir = root / "audit"
    if not audit_dir.exists():
        return []

    files: list[Path] = []
    if mode in ("open", "all"):
        files.extend(sorted(
            p for p in audit_dir.glob("*.md") if p.name != ".gitkeep"
        ))
    if mode in ("resolved", "all"):
        resolved = audit_dir / "resolved"
        if resolved.exists():
            files.extend(sorted(
                p for p in resolved.glob("*.md") if p.name != ".gitkeep"
            ))

    entries: list[dict] = []
    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)
        if fm is None:
            print(f"⚠️  {p.relative_to(root)} — missing frontmatter",
                  file=sys.stderr)
            continue

        entry = {
            "type": "audit-file",
            "id": fm.get("id", p.stem),
            "target": fm.get("target", "(no-target)"),
            "target_lines": fm.get("target_lines", []),
            "severity": fm.get("severity", "info"),
            "author": fm.get("author", "unknown"),
            "source": fm.get("source", "manual"),
            "created": fm.get("created", ""),
            "status": fm.get("status", "open"),
            "comment": extract_comment_one_line(text),
            "file_path": str(p.relative_to(root)),
            "anchor_text": fm.get("anchor_text", ""),
        }
        entries.append(entry)

    return entries


# ── Scan inline FIX comments ─────────────────────────────────────────────────

def scan_fix_comments(root: Path) -> list[dict]:
    """Scan wiki/**/*.md for inline <!-- FIX: ... --> comments."""
    wiki_dir = root / "wiki"
    if not wiki_dir.exists():
        return []

    entries: list[dict] = []
    for md_file in wiki_dir.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for match in FIX_COMMENT_RE.finditer(text):
            comment = match.group(1).strip()
            if not comment:
                continue

            # Calculate line number
            line_start = text[:match.start()].count("\n") + 1

            rel_path = str(md_file.relative_to(root))
            entry = {
                "type": "inline-fix",
                "id": f"fix-{md_file.stem}-L{line_start}",
                "target": rel_path,
                "target_lines": [line_start, line_start],
                "severity": "warn",
                "author": "human",
                "source": "inline",
                "created": "",
                "status": "open",
                "comment": comment[:200],
                "file_path": rel_path,
                "anchor_text": "",
            }
            entries.append(entry)

    return entries


# ── Main ──────────────────────────────────────────────────────────────────────

def main(root: str, mode: str, output_json: bool = False) -> int:
    root_path = Path(root)

    # Gather entries from both surfaces
    audit_entries = scan_audit_files(root_path, mode)
    fix_entries = []
    if mode in ("open", "all"):
        fix_entries = scan_fix_comments(root_path)

    all_entries = audit_entries + fix_entries

    if not all_entries:
        if output_json:
            print("[]")
        else:
            print(f"No {mode} feedback found.")
        return 0

    # ── JSON output ───────────────────────────────────────────────────────────
    if output_json:
        print(json.dumps(all_entries, indent=2, ensure_ascii=False))
        return 0

    # ── Human-readable output ─────────────────────────────────────────────────
    grouped: dict[str, list[dict]] = defaultdict(list)
    for entry in all_entries:
        grouped[entry["target"]].append(entry)

    total = len(all_entries)
    audit_count = len(audit_entries)
    fix_count = len(fix_entries)

    print(f"Feedback summary ({mode.upper()}):")
    print(f"  audit/ files: {audit_count}")
    print(f"  inline FIX:   {fix_count}")
    print(f"  total:        {total} across {len(grouped)} target files\n")

    for target in sorted(grouped.keys()):
        entries = grouped[target]
        entries.sort(key=lambda e: (
            SEVERITY_ORDER.get(e.get("severity", "info"), 99),
            e.get("created", ""),
        ))

        print(f"{target}  ({len(entries)} items)")
        for e in entries:
            sev = e.get("severity", "?")
            eid = e.get("id", "?")
            etype = e.get("type", "?")
            comment = e.get("comment", "")
            source = e.get("source", "?")

            if etype == "inline-fix":
                lines = e.get("target_lines", [])
                line_info = f"L{lines[0]}" if lines else "?"
                print(f"   [{eid}] {sev}: {comment}  —  inline @ {line_info}")
            else:
                author = e.get("author", "?")
                created = e.get("created", "?")[:10]
                print(f"   [{eid}] {sev}: {comment}  —  {author}, {created} ({source})")
        print()

    return 0


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="List and group audit feedback by target file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--open", dest="mode", action="store_const",
                        const="open", help="Show open feedback (default)")
    parser.add_argument("--resolved", dest="mode", action="store_const",
                        const="resolved", help="Show resolved feedback")
    parser.add_argument("--all", dest="mode", action="store_const",
                        const="all", help="Show all feedback")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON (for LLM consumption)")
    parser.set_defaults(mode="open")

    args = parser.parse_args()
    sys.exit(main(args.wiki_root, args.mode, args.json))


if __name__ == "__main__":
    cli()
