#!/usr/bin/env python3
"""
batch_ingest.py — Batch ingest multiple files into an LLM Wiki.

Usage:
    python3 batch_ingest.py <wiki-root> [--dir raw/articles] [--ext .md .pdf]
    python3 batch_ingest.py <wiki-root> --dir raw/pdfs --ext .pdf --pdf
    python3 batch_ingest.py <wiki-root> --dry-run

Options:
    --dir DIR       Directory to scan (relative to wiki-root). Default: raw/
    --ext EXT...    File extensions to include. Default: .md .txt
    --pdf           Auto-convert PDF files via pdf_to_md.py before ingest
    --dry-run       Show what would be processed without creating any stubs
    --force         Re-ingest files even if a stub already exists

Example:
    python3 batch_ingest.py ~/wikis/ai-research --dir raw/articles
    python3 batch_ingest.py ~/wikis/ai-research --dir raw/pdfs --ext .pdf --pdf
"""

from __future__ import annotations  # PEP 604 `X | None` in signatures → lazy, works on py3.9

import hashlib
import os
import subprocess
import sys
import argparse
from pathlib import Path


def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_known_hashes(wiki_root: Path) -> set[str]:
    """Collect all raw_sha256 values from existing source stubs."""
    known: set[str] = set()
    sources_dir = wiki_root / "wiki" / "sources"
    if not sources_dir.exists():
        return known
    for stub in sources_dir.rglob("*.md"):
        try:
            text = stub.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if line.strip().startswith("raw_sha256:"):
                    sha = line.split(":", 1)[1].strip().strip("\"'")
                    if sha:
                        known.add(sha)
        except OSError:
            pass
    return known


def convert_pdf(pdf_path: Path, wiki_root: Path, out_dir: Path) -> Path | None:
    """Convert a PDF to markdown using pdf_to_md.py. Returns the output path."""
    converter = wiki_root / ".claude" / "skills" / "pdf-ingest" / "scripts" / "pdf_to_md.py"
    if not converter.exists():
        print(f"  ⚠️  pdf_to_md.py not found at {converter}. Enable pdf-ingest skill.")
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(converter), str(pdf_path), "--out", str(out_dir)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ✗ PDF conversion failed: {pdf_path.name}")
        print(f"    {result.stderr.strip()}")
        return None
    # Find the output file
    stem = pdf_path.stem.lower()
    for f in out_dir.glob("*.md"):
        if stem in f.stem.lower():
            return f
    return None


def batch_ingest(root: str, scan_dir: str = "raw", extensions: list[str] | None = None,
                 pdf_mode: bool = False, dry_run: bool = False,
                 force: bool = False) -> int:
    root_path = Path(root).resolve()
    scan_path = root_path / scan_dir
    fast_ingest = root_path / ".claude" / "skills" / "llm-wiki" / "scripts" / "fast_ingest.py"

    if not fast_ingest.exists():
        fast_ingest = root_path / "scripts" / "fast_ingest.py"

    if not fast_ingest.exists():
        print(f"ERROR: fast_ingest.py not found under {root_path}", file=sys.stderr)
        return 1

    if not scan_path.exists():
        print(f"ERROR: Scan directory not found: {scan_path}", file=sys.stderr)
        return 1

    if extensions is None:
        extensions = [".md", ".txt"]
    extensions = [e if e.startswith(".") else f".{e}" for e in extensions]

    print(f"Scanning: {scan_path}")
    print(f"Extensions: {extensions}")
    if dry_run:
        print("DRY RUN — no stubs will be created\n")

    # Collect known hashes to skip already-ingested files
    known_hashes = collect_known_hashes(root_path) if not force else set()

    # Find candidate files
    candidates: list[Path] = []
    for ext in extensions:
        candidates.extend(sorted(scan_path.rglob(f"*{ext}")))

    if not candidates:
        print("No files found matching the specified extensions.")
        return 0

    new_count = 0
    skip_count = 0
    error_count = 0

    for raw_file in candidates:
        sha = compute_sha256(raw_file)

        if sha in known_hashes and not force:
            skip_count += 1
            print(f"  ↷ already ingested: {raw_file.relative_to(root_path)}")
            continue

        # PDF conversion mode
        ingest_target = raw_file
        if pdf_mode and raw_file.suffix.lower() == ".pdf":
            if dry_run:
                print(f"  [DRY] would convert PDF: {raw_file.relative_to(root_path)}")
                new_count += 1
                continue
            out_dir = root_path / "raw" / "articles"
            converted = convert_pdf(raw_file, root_path, out_dir)
            if converted is None:
                error_count += 1
                continue
            ingest_target = converted
            print(f"  ✓ converted PDF → {converted.relative_to(root_path)}")

        if dry_run:
            print(f"  [DRY] would ingest: {raw_file.relative_to(root_path)}")
            new_count += 1
            continue

        # Run fast_ingest.py
        result = subprocess.run(
            [sys.executable, str(fast_ingest), str(root_path), str(ingest_target)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  ✗ ingest failed: {raw_file.name}")
            if result.stderr:
                print(f"    {result.stderr.strip()[:200]}")
            error_count += 1
        else:
            new_count += 1
            # Show just the slug line from stdout
            for line in result.stdout.splitlines():
                if "Stub created" in line or "Slug:" in line:
                    print(f"  ✓ {line.strip()}")
                    break

    print(f"\n{'DRY RUN ' if dry_run else ''}Summary:")
    print(f"  New stubs created : {new_count}")
    print(f"  Already ingested  : {skip_count}")
    print(f"  Errors            : {error_count}")

    if new_count > 0 and not dry_run:
        print(f"\nNext steps:")
        print(f"  1. Fill in each new stub in wiki/sources/")
        print(f"  2. Run: python3 scripts/build_index.py {root}")
        print(f"     (rebuilds wiki/index.md and domain catalogs)")

    return 0 if error_count == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch ingest multiple files into an LLM Wiki.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--dir", default="raw",
                        help="Directory to scan (relative to wiki-root)")
    parser.add_argument("--ext", nargs="+", default=[".md", ".txt"],
                        help="File extensions to include (default: .md .txt)")
    parser.add_argument("--pdf", action="store_true",
                        help="Auto-convert PDF files before ingest")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be processed without creating stubs")
    parser.add_argument("--force", action="store_true",
                        help="Re-ingest files even if a stub already exists")

    args = parser.parse_args()
    sys.exit(batch_ingest(
        args.wiki_root,
        scan_dir=args.dir,
        extensions=args.ext,
        pdf_mode=args.pdf,
        dry_run=args.dry_run,
        force=args.force,
    ))


if __name__ == "__main__":
    main()
