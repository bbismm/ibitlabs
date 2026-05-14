#!/usr/bin/env bash
#
# install_pre_commit_hook.sh — wire harness/scripts/pre-commit-freeze into
# .git/hooks/pre-commit as a symlink (idempotent).
#
# If a non-symlink pre-commit hook already exists, it gets backed up first.
# Re-running this installer just refreshes the symlink.
#
# Uninstall: rm .git/hooks/pre-commit
#
set -eu

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
    echo "error: not inside a git repository" >&2
    exit 1
fi

HOOK_SOURCE="$REPO_ROOT/harness/scripts/pre-commit-freeze"
HOOK_TARGET="$REPO_ROOT/.git/hooks/pre-commit"

if [ ! -f "$HOOK_SOURCE" ]; then
    echo "error: $HOOK_SOURCE not found" >&2
    exit 1
fi

chmod +x "$HOOK_SOURCE"

if [ -e "$HOOK_TARGET" ] && [ ! -L "$HOOK_TARGET" ]; then
    BACKUP="$HOOK_TARGET.backup-$(date +%Y%m%d-%H%M%S)"
    echo "existing non-symlink pre-commit hook found; backing up to:"
    echo "  $BACKUP"
    mv "$HOOK_TARGET" "$BACKUP"
fi

ln -sf "$HOOK_SOURCE" "$HOOK_TARGET"

echo "installed: $HOOK_TARGET"
echo "       ->  $HOOK_SOURCE"
echo ""
echo "verify:    python3 $REPO_ROOT/harness/bin/freeze_status.py"
echo "test:      HARNESS_FREEZE_TEST_NOW=2026-05-31 bash $HOOK_SOURCE"
