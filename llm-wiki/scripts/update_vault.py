#!/usr/bin/env python3
"""
update_vault.py — Sync an existing vault's CLAUDE.md + config from wiki-config.md.

SAFETY: only touches these paths:
  wiki-config.md   CLAUDE.md   log/   .claude/config-checksum   .claude/settings.json

NEVER touches:
  raw/   wiki/   outputs/   audit/   .claude/skills/

Usage:
  python3 update_vault.py <wiki-root> [--dry-run]
  python3 update_vault.py <wiki-root> --check-config

This script does NOT copy skills into the vault — skills are discovered natively
by Claude Code. Adding a skill needs no install step: drop its folder in
.claude/skills/. Cross-skill preferences go in each skill's description.
"""

import os
import re
import sys
import json
import hashlib
import argparse
from datetime import date, datetime


CONFIG_CHECKSUM_PATH = ".claude/config-checksum"

# ── Known config keys that may be added by newer versions ──────────────────
# Only keys NOT already in the existing config are added.
NEW_CONFIG_KEYS = {
    "auto_flag_on_sha_change": "true",
}


# ─────────────────────────────────────────────────────────────────────────────
# Config MD helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_config_yaml(config_path: str) -> str:
    """Extract YAML content from the ```yaml block in wiki-config.md."""
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    m = re.search(r'```yaml\n(.*?)\n```', content, re.DOTALL)
    return m.group(1) if m else content


def _write_config_yaml(config_path: str, yaml_content: str) -> None:
    """Replace the ```yaml block content in wiki-config.md."""
    with open(config_path, "r", encoding="utf-8") as f:
        md = f.read()
    updated = re.sub(
        r'(```yaml\n)(.*?)(\n```)',
        lambda m: m.group(1) + yaml_content + m.group(3),
        md, flags=re.DOTALL
    )
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(updated)


# ─────────────────────────────────────────────────────────────────────────────
# Mode 1: Standard update
# ─────────────────────────────────────────────────────────────────────────────

def update(root: str, dry_run: bool = False) -> None:
    """Update an existing vault in-place."""
    now = datetime.now()
    today_compact = now.strftime("%Y%m%d")
    now_hm = now.strftime("%H:%M")

    # ── Validate vault ─────────────────────────────────────────────────────
    config_path = os.path.join(root, "wiki-config.md")
    if not os.path.isfile(config_path):
        # Bootstrap: create a default wiki-config.md for uninitialized vault
        default_yaml = """\
# wiki-config.md
# Central configuration. Edit to change system behavior.
# After editing, tell the agent: "please reload config".

# ── Identity ──────────────────────────────────────────────────────────────────
domains:
  - "General"

primary_language: "English"

secondary_language: "None"
  # Annotates NEW technical terms on first occurrence per article.
  # Set to "None" to disable.

# ── Anti-Hallucination ────────────────────────────────────────────────────────
require_line_citations: true
require_verbatim_numbers: true

# ── Confidence Gating ─────────────────────────────────────────────────────────
confidence_high_requires_user: true
confidence_medium_threshold: 3
confidence_high_candidate: 5

# ── Search ────────────────────────────────────────────────────────────────────
search_tool: qmd
qmd_collection: "general"
search_tool_threshold: 50

# ── Staleness Thresholds ──────────────────────────────────────────────────────
staleness_thresholds:
  high: 90
  medium: 180
  low: 365

# ── Article Length ────────────────────────────────────────────────────────────
article_max_words: 1200

# ── Source Integrity ──────────────────────────────────────────────────────────
auto_flag_on_sha_change: true

# ── Maintenance Schedule ──────────────────────────────────────────────────────
lint_frequency: "every 10 sources, or weekly"
deep_lint_frequency: "monthly"

"""
        config_md = f"""\
---
type: wiki-config
graph-excluded: true
---

# Wiki Configuration

> Central configuration for this wiki vault.
> Edit the YAML block below to change system behavior.
> After changes, tell the agent: **"please reload config"**.

```yaml
{default_yaml}
```
"""
        if not dry_run:
            os.makedirs(root, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(config_md)
        print(f"{'[DRY RUN] ' if dry_run else ''}Created wiki-config.md with default configuration.")
        print("")
        print("Please review and edit wiki-config.md — especially the 'domains:' field.")
        print("Run this script again after reviewing the config.")
        sys.exit(0)

    if dry_run:
        print(f"[DRY RUN] Would update vault at: {root}/\n")

    # ── 1. Merge new keys into wiki-config.md (non-destructive) ─────────────
    if not dry_run:
        added = _merge_config(config_path)
        if added:
            for key in added:
                print(f"✓ Added config key: {key}")
        else:
            print("✓ wiki-config.md is up to date")
        normalized = _normalize_mcp_config(config_path)
        if normalized:
            print("✓ Normalized MCP config to new format (mcp: llm-wiki-compiler)")
    else:
        print("[DRY RUN] Would merge new config keys into wiki-config.md")
        print("[DRY RUN] Would normalize old MCP config format if present")

    # ── 1b. Create .claude/settings.json if MCP is enabled ──────────────────
    mcp_enabled = _mcp_is_enabled(config_path)
    if mcp_enabled:
        _ensure_claude_settings(root, dry_run)
        if not dry_run:
            print("✓ Ensured .claude/settings.json (MCP server config)")

    # ── 2. Update CLAUDE.md path references ────────────────────────────────
    if not dry_run:
        _update_claude_md(root)
    print(f"{'[DRY RUN] ' if dry_run else ''}✓ Updated CLAUDE.md path references")

    # ── 2b. Sync domains from wiki-config.md → CLAUDE.md § Scope ────────────
    domains_changed = False
    if not dry_run:
        domains_changed = _sync_domains_to_claude_md(root, config_path)
        if domains_changed:
            print(f"✓ Synced domains → CLAUDE.md § Scope")
            print(f"  ⚠  Domains changed — rebuild the index:")
            print(f"     python3 .claude/skills/llm-wiki/scripts/build_index.py {root}")
        else:
            print(f"✓ CLAUDE.md § Scope already matches wiki-config.md domains")
    else:
        print("[DRY RUN] Would sync domains from wiki-config.md → CLAUDE.md § Scope")

    # ── 2c. Sync private paths → CLAUDE.md § Private zones ──────────────────
    private_changed = False
    if not dry_run:
        private_changed = _sync_private_to_claude_md(root, config_path)
        if private_changed:
            print(f"✓ Synced private paths → CLAUDE.md § Private zones")
        else:
            print(f"✓ CLAUDE.md § Private zones already matches wiki-config.md")
    else:
        print("[DRY RUN] Would sync private paths → CLAUDE.md § Private zones")

    # ── 3. Append log entry ────────────────────────────────────────────────
    log_entry = (
        f"\n## [{now_hm}] update_vault | Synced CLAUDE.md + config from wiki-config.md\n"
        f"- Merged new config keys into wiki-config.md\n"
        f"- Updated CLAUDE.md path references\n"
        + (f"- Synced domains → CLAUDE.md § Scope\n" if domains_changed else "")
        + (f"- Synced private paths → CLAUDE.md § Private zones\n" if private_changed else "")
    )
    if not dry_run:
        log_path = os.path.join(root, "log", f"{today_compact}.md")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
    print(f"{'[DRY RUN] ' if dry_run else ''}✓ Appended log/{today_compact}.md")

    # ── 4. Write config checksum ───────────────────────────────────────────
    if not dry_run:
        _write_config_checksum(root, config_path)
        print(f"✓ Saved config checksum → {CONFIG_CHECKSUM_PATH}")
    else:
        print(f"[DRY RUN] Would save config checksum → {CONFIG_CHECKSUM_PATH}")

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'[DRY RUN] ' if dry_run else '✅'} Vault updated: {root}/\n")
    if dry_run:
        print("Run without --dry-run to apply changes.")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — config management
# ─────────────────────────────────────────────────────────────────────────────

def _merge_config(config_path: str):
    """Add new config keys that don't exist in the current config. Returns list of added keys."""
    content = _read_config_yaml(config_path)

    added = []
    for key, value in NEW_CONFIG_KEYS.items():
        if key not in content:
            if "skills:" in content:
                insert_line = f"{key}: {value}\n"
                content = content.replace("skills:", f"{insert_line}skills:", 1)
            else:
                content += f"\n{key}: {value}\n"
            added.append(key)

    if added:
        _write_config_yaml(config_path, content)

    return added


def _update_claude_md(root: str) -> None:
    """Update path references in CLAUDE.md to point to the vault's own root."""
    claude_path = os.path.join(root, "CLAUDE.md")
    if not os.path.isfile(claude_path):
        return

    with open(claude_path, "r", encoding="utf-8") as f:
        content = f.read()

    updated = False
    old_audit_line = f"python3 scripts/audit_review.py {root} --open"
    new_audit_line = f"python3 .claude/skills/llm-wiki/scripts/audit_review.py {root} --open"
    if old_audit_line in content:
        content = content.replace(old_audit_line, new_audit_line)
        updated = True

    if updated:
        with open(claude_path, "w", encoding="utf-8") as f:
            f.write(content)


def _sync_domains_to_claude_md(root: str, config_path: str) -> bool:
    """Sync domains list from wiki-config.md into CLAUDE.md § Scope.
    Returns True if CLAUDE.md was updated."""
    claude_path = os.path.join(root, "CLAUDE.md")
    if not os.path.isfile(claude_path):
        return False

    config = _read_config_yaml(config_path)

    domain_block = re.search(r'^domains:\s*\n((?:[ \t]+-[^\n]+\n)+)', config, re.MULTILINE)
    if not domain_block:
        return False

    domains = []
    for line in domain_block.group(1).strip().split("\n"):
        stripped = line.strip().lstrip("- ").strip().strip('"')
        if stripped:
            domains.append(stripped)

    if not domains:
        return False

    with open(claude_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_bullets = "\n".join(f"- {d}" for d in domains)
    updated = re.sub(
        r'(What this wiki covers:\n)\n?(?:[ \t]*-[^\n]*\n)*',
        f"What this wiki covers:\n\n{new_bullets}\n",
        content,
    )

    if updated == content:
        return False

    with open(claude_path, "w", encoding="utf-8") as f:
        f.write(updated)
    return True


def _sync_private_to_claude_md(root: str, config_path: str) -> bool:
    """Sync private: paths from wiki-config.md into CLAUDE.md § Private zones.
    Creates the section if absent; updates it if paths changed.
    Returns True if CLAUDE.md was updated."""
    claude_path = os.path.join(root, "CLAUDE.md")
    if not os.path.isfile(claude_path):
        return False

    config = _read_config_yaml(config_path)

    private_block = re.search(
        r'^private:\s*\n((?:[ \t]+-[^\n]+\n)+)', config, re.MULTILINE
    )
    if not private_block:
        return False

    paths = []
    for line in private_block.group(1).strip().split("\n"):
        p = line.strip().lstrip("- ").strip().strip('"\'')
        p = re.sub(r'\s+#.*$', '', p).strip()   # strip inline YAML comments
        if p:
            paths.append(p)

    if not paths:
        return False

    with open(claude_path, "r", encoding="utf-8") as f:
        content = f.read()

    bullet_lines = "\n".join(f"- `{p}/`" for p in paths)
    new_section = (
        "## Private zones\n\n"
        "Paths containing sensitive data (PHI, personal information, confidential records, etc.).\n"
        "**NEVER read files here directly** — always use the designated pipeline.\n"
        "See `## Strict workflow rules` for the required command.\n\n"
        f"{bullet_lines}\n"
    )

    if re.search(r'^## Private zones', content, re.MULTILINE):
        # Replace existing section (up to the next ## heading or end of file)
        updated = re.sub(
            r'^## Private zones\n.*?(?=\n^## |\Z)',
            new_section,
            content,
            flags=re.DOTALL | re.MULTILINE,
        )
    else:
        # Insert before "## Strict workflow rules" or "## Notes for the LLM"
        for anchor in ["## Strict workflow rules", "## Notes for the LLM"]:
            if anchor in content:
                updated = content.replace(anchor, new_section + "\n" + anchor, 1)
                break
        else:
            updated = content.rstrip() + "\n\n" + new_section

    if updated == content:
        return False

    with open(claude_path, "w", encoding="utf-8") as f:
        f.write(updated)
    return True


def _normalize_mcp_config(config_path: str) -> bool:
    """Convert old `mcp:\\n  enabled: true` format to `mcp: llm-wiki-compiler`."""
    content = _read_config_yaml(config_path)

    old_pattern = r'^mcp:\s*\n\s+enabled:\s*true'
    if not re.search(old_pattern, content, re.MULTILINE):
        return False

    content = re.sub(old_pattern, 'mcp: llm-wiki-compiler', content)
    _write_config_yaml(config_path, content)
    return True


def _mcp_is_enabled(config_path: str) -> bool:
    """Check if MCP is enabled in wiki-config.md (new format only)."""
    content = _read_config_yaml(config_path)
    m = re.search(r'^mcp:\s*(.+)$', content, re.MULTILINE)
    if not m:
        return False
    return m.group(1).strip() == "llm-wiki-compiler"


def _ensure_claude_settings(root: str, dry_run: bool) -> None:
    """Create a placeholder .claude/settings.json if it doesn't exist.
    MCP server integration is reserved for future use — mcpServers is empty."""
    claude_dir = os.path.join(root, ".claude")
    settings_path = os.path.join(claude_dir, "settings.json")
    if dry_run:
        if not os.path.isfile(settings_path):
            print("[DRY RUN] Would create .claude/settings.json (placeholder)")
        return
    if os.path.isfile(settings_path):
        return
    os.makedirs(claude_dir, exist_ok=True)
    claude_settings = {
        "mcpServers": {}
    }
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(claude_settings, f, indent=2)
        f.write("\n")


# ─────────────────────────────────────────────────────────────────────────────
# Config checksum helpers + check_config mode
# ─────────────────────────────────────────────────────────────────────────────

def _compute_config_hash(config_path: str) -> str:
    with open(config_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _write_config_checksum(root: str, config_path: str) -> None:
    checksum_path = os.path.join(root, CONFIG_CHECKSUM_PATH)
    os.makedirs(os.path.dirname(checksum_path), exist_ok=True)
    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write(_compute_config_hash(config_path) + "\n")


def check_config(root: str) -> None:
    """Check if wiki-config.md has changed since the last update run.
    Exits 0 if unchanged, 1 if changed or no baseline exists."""
    config_path = os.path.join(root, "wiki-config.md")
    if not os.path.isfile(config_path):
        print(f"Error: {root} is not a valid llm-wiki vault (no wiki-config.md).",
              file=sys.stderr)
        sys.exit(1)

    checksum_path = os.path.join(root, CONFIG_CHECKSUM_PATH)
    if not os.path.isfile(checksum_path):
        print("⚠  No config checksum found — run update_vault.py to establish a baseline.")
        sys.exit(1)

    with open(checksum_path, encoding="utf-8") as f:
        stored = f.read().strip()

    current = _compute_config_hash(config_path)
    if current != stored:
        print("⚠  wiki-config.md has changed since last update.")
        print(f"   Run: python3 .claude/skills/llm-wiki/scripts/update_vault.py {root}")
        sys.exit(1)

    print("✓ wiki-config.md unchanged since last update.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh the vault's bundled llm-wiki skill and sync config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("wiki_root", help="Path to the wiki root directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be changed without making changes")
    parser.add_argument("--check-config", action="store_true",
                        help="Check if wiki-config.md changed since last update (exit 1 if yes)")

    args = parser.parse_args()
    root = os.path.abspath(args.wiki_root)

    if args.check_config:
        check_config(root)
    else:
        update(root, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
