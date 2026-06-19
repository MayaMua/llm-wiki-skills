#!/usr/bin/env bash
#
# sync-skill.sh — push the ground-truth llm-wiki skill into vault bundled copies.
#
# The repo's llm-wiki/ directory is the single source of truth. The global install
# (~/.claude/skills/llm-wiki) is a SYMLINK to it, so it tracks changes automatically.
# Vaults, however, carry their own *real copies* of the skill (so each vault stays
# self-contained / portable) — those copies must be re-synced after a skill update.
# This script does that.
#
# Usage:
#   ./sync-skill.sh                 # sync to every vault copy auto-discovered under $OBSIDIAN_ROOT
#   ./sync-skill.sh --dry-run       # show what WOULD change, write nothing
#   ./sync-skill.sh /path/to/vault  # sync to specific vault root(s) (a dir containing .claude/skills/llm-wiki)
#   OBSIDIAN_ROOT=/some/dir ./sync-skill.sh   # override the discovery root (default: /Workspace/Obsidian)
#
# Safety:
#   - Targets that are SYMLINKS are skipped (never write through the global symlink).
#   - A target resolving to the source itself is skipped.
#   - rsync --delete keeps the copy an exact mirror; __pycache__ and .git are excluded.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/llm-wiki"
OBSIDIAN_ROOT="${OBSIDIAN_ROOT:-/Workspace/Obsidian}"

DRY_RUN=0
EXPLICIT_TARGETS=()
for arg in "$@"; do
  case "$arg" in
    --dry-run|-n) DRY_RUN=1 ;;
    -h|--help)    sed -n '2,24p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *)            EXPLICIT_TARGETS+=("$arg") ;;
  esac
done

if [[ ! -f "$SOURCE/SKILL.md" ]]; then
  echo "ERROR: source skill not found at $SOURCE/SKILL.md" >&2
  exit 1
fi
SOURCE_REAL="$(realpath "$SOURCE")"

# ── Collect target skill directories ──────────────────────────────────────────
targets=()
if (( ${#EXPLICIT_TARGETS[@]} )); then
  for t in "${EXPLICIT_TARGETS[@]}"; do
    # Accept either a vault root or a direct skill dir.
    if [[ -d "$t/.claude/skills/llm-wiki" ]]; then
      targets+=("$t/.claude/skills/llm-wiki")
    elif [[ "$(basename "$t")" == "llm-wiki" ]]; then
      targets+=("$t")
    else
      echo "WARN: no .claude/skills/llm-wiki under '$t' — skipping" >&2
    fi
  done
else
  if [[ -d "$OBSIDIAN_ROOT" ]]; then
    while IFS= read -r d; do targets+=("$d"); done < <(
      find "$OBSIDIAN_ROOT" -maxdepth 4 -type d -path '*/.claude/skills/llm-wiki' 2>/dev/null | sort
    )
  fi
fi

if (( ${#targets[@]} == 0 )); then
  echo "No vault skill copies found (searched: ${EXPLICIT_TARGETS[*]:-$OBSIDIAN_ROOT})."
  exit 0
fi

RSYNC_FLAGS=(-a --delete --exclude='__pycache__' --exclude='.git')
(( DRY_RUN )) && RSYNC_FLAGS+=(-ni)

echo "Source : $SOURCE_REAL"
echo "Mode   : $([[ $DRY_RUN == 1 ]] && echo 'DRY RUN (no writes)' || echo 'apply')"
echo

synced=0; skipped=0
for tgt in "${targets[@]}"; do
  if [[ -L "$tgt" ]]; then
    echo "↪ skip (symlink): $tgt"; skipped=$((skipped+1)); continue
  fi
  if [[ "$(realpath "$tgt")" == "$SOURCE_REAL" ]]; then
    echo "↪ skip (is source): $tgt"; skipped=$((skipped+1)); continue
  fi
  echo "→ $tgt"
  if (( DRY_RUN )); then
    out="$(rsync "${RSYNC_FLAGS[@]}" "$SOURCE/" "$tgt/" || true)"
    if [[ -n "$out" ]]; then echo "$out" | sed 's/^/    /'; else echo "    (already up to date)"; fi
  else
    rsync "${RSYNC_FLAGS[@]}" "$SOURCE/" "$tgt/"
    echo "    ✓ synced"
  fi
  synced=$((synced+1))
done

echo
echo "Done: $synced target(s) processed, $skipped skipped."
