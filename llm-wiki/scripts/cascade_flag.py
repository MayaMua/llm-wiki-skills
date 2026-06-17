#!/usr/bin/env python3
"""
cascade_flag.py — Propagate FIX comments when raw source files change.

When lint_wiki.py reports SHA-256 mismatches, the wiki pages that cite those
sources contain stale citations. This script finds all affected lines and
inserts <!-- FIX: --> comments so the audit operation can address them.

Usage:
    python3 cascade_flag.py <wiki-root>
    python3 cascade_flag.py <wiki-root> --dry-run   # Show what would change
    python3 cascade_flag.py <wiki-root> --file raw/articles/paper.md  # One file

Example:
    python3 cascade_flag.py ~/wikis/ai-research
"""

from __future__ import annotations  # PEP 604 `X | None` in signatures → lazy, works on py3.9

import hashlib
import re
import sys
import argparse
from pathlib import Path


CITATION_LINE_RE = re.compile(r"\((raw/[^,)]+),")
FIX_TAG = "<!-- FIX: raw source changed (sha256 mismatch) — re-verify this claim -->"


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_modified_sources(wiki_root: Path) -> set[str]:
    """Return set of raw_file paths (relative to wiki_root) with sha256 mismatches."""
    modified: set[str] = set()
    sources_dir = wiki_root / "wiki" / "sources"
    if not sources_dir.exists():
        return modified
    for stub in sources_dir.glob("*.md"):
        try:
            text = stub.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        raw_file = ""
        stored_sha = ""
        for line in text.splitlines():
            if line.strip().startswith("raw_file:"):
                raw_file = line.split(":", 1)[1].strip().strip("\"'")
            elif line.strip().startswith("raw_sha256:"):
                stored_sha = line.split(":", 1)[1].strip().strip("\"'")
        if not raw_file or not stored_sha:
            continue
        raw_path = wiki_root / raw_file
        if not raw_path.exists():
            continue
        if compute_sha256(raw_path) != stored_sha:
            modified.add(raw_file)
    return modified


def flag_citations_in_file(wiki_file: Path, modified_sources: set[str],
                            dry_run: bool = False) -> int:
    """Add FIX comments to lines that cite a modified source. Returns count added."""
    try:
        original = wiki_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0

    lines = original.splitlines(keepends=True)
    new_lines: list[str] = []
    added = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if this line cites a raw file that has changed
        match = CITATION_LINE_RE.search(line)
        if match:
            cited_raw = match.group(1).strip()  # e.g. "raw/articles/bert-paper.md"
            if cited_raw in modified_sources:
                # Check that we haven't already added a FIX comment on the next line
                next_line = lines[i + 1] if i + 1 < len(lines) else ""
                if FIX_TAG not in next_line and FIX_TAG not in line:
                    new_lines.append(line)
                    eol = "\n" if not line.endswith("\n") else ""
                    new_lines.append(FIX_TAG + eol + "\n")
                    added += 1
                    i += 1
                    continue
        new_lines.append(line)
        i += 1

    if added > 0 and not dry_run:
        wiki_file.write_text("".join(new_lines), encoding="utf-8")

    return added


def cascade_flag(root: str, target_file: str | None = None,
                 dry_run: bool = False) -> int:
    root_path = Path(root).resolve()
    wiki_path = root_path / "wiki"

    if not wiki_path.exists():
        print(f"ERROR: wiki/ directory not found at {wiki_path}", file=sys.stderr)
        return 1

    # Find all modified sources
    if target_file:
        modified = {target_file}
        print(f"Flagging citations to: {target_file}")
    else:
        modified = find_modified_sources(root_path)
        if not modified:
            print("✓ No modified source files found. Nothing to flag.")
            return 0
        print(f"Found {len(modified)} modified source file(s):")
        for src in sorted(modified):
            print(f"  {src}")

    if dry_run:
        print("\nDRY RUN — no files will be modified\n")

    # Scan all wiki pages for citations to modified sources
    total_flags = 0
    flagged_files = 0

    wiki_md_files = [
        f for f in wiki_path.rglob("*.md")
        if "templates" not in f.parts
        and f.name not in {"index.md", "overview.md", "QUESTIONS.md"}
    ]

    for wiki_file in sorted(wiki_md_files):
        count = flag_citations_in_file(wiki_file, modified, dry_run=dry_run)
        if count > 0:
            total_flags += count
            flagged_files += 1
            action = "would flag" if dry_run else "flagged"
            print(f"  {action} {count} citation(s): {wiki_file.relative_to(root_path)}")

    if total_flags == 0:
        print("✓ No citations to modified sources found in wiki pages.")
        return 0

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
    print(f"  Wiki pages affected : {flagged_files}")
    print(f"  FIX comments added  : {total_flags}")
    if not dry_run:
        print(f"\nNext step: run audit to process the FIX comments:")
        print(f"  python3 scripts/audit_review.py {root} --open")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Propagate FIX comments when raw source files change.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--file", default=None,
                        help="Only flag citations to this specific raw file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without modifying files")

    args = parser.parse_args()
    sys.exit(cascade_flag(args.wiki_root, target_file=args.file, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
