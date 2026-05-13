#!/usr/bin/env bash
# Refresh ~/ibitlabs/receipt-viewer/ from ~/Documents/receipt/viewer/.
#
# Run this after editing dashboard.html / monitor.html / index.html / score.js
# (or any other static asset under viewer/) so the launchd-served viewer at
# http://127.0.0.1:8090/ picks up your changes.
#
# Why we need this: macOS TCC blocks launchd-spawned processes from reading
# ~/Documents/. So we mirror viewer files to ~/ibitlabs/receipt-viewer/
# (TCC-free) and serve from there via com.ibitlabs.receipt-viewer launchd job.
# Running this script from Terminal works because Terminal has Documents
# access; the mirrored copy in ~/ibitlabs/ is what launchd serves.
#
# Safe to re-run idempotently. Uses rsync --delete so files removed from
# the source disappear from the mirror.

set -e

SOURCE="$HOME/Documents/receipt/viewer"
TARGET="$HOME/ibitlabs/receipt-viewer"

# Live-chain symlinks managed here, NOT rsync'd from source. Parallel
# indexed arrays because macOS bash 3.2 lacks associative arrays.
LINK_NAMES=(
    "shadow-chain.jsonl"
    "rule-engine-chain.jsonl"
)
LINK_TARGETS=(
    "$HOME/ibitlabs/audit_export/sniper-v5.1-shadow.realtime.receipt.jsonl"
    "$HOME/ibitlabs/audit_export/rule-engine.realtime.receipt.jsonl"
)

if [ ! -d "$SOURCE" ]; then
    echo "✗ Source not found: $SOURCE" >&2
    echo "  Is the receipt repo at ~/Documents/receipt/?" >&2
    exit 1
fi

mkdir -p "$TARGET"

# Build rsync excludes for each symlinked filename so we don't clobber
# the live symlinks with stale snapshots from the source.
RSYNC_EXCLUDES=()
for fn in "${LINK_NAMES[@]}"; do
    RSYNC_EXCLUDES+=(--exclude="$fn")
done

rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$SOURCE/" "$TARGET/"

# (Re)create each live symlink.
for i in "${!LINK_NAMES[@]}"; do
    fn="${LINK_NAMES[$i]}"
    link_path="$TARGET/$fn"
    link_target="${LINK_TARGETS[$i]}"
    if [ ! -L "$link_path" ] || [ "$(readlink "$link_path")" != "$link_target" ]; then
        rm -f "$link_path"
        ln -s "$link_target" "$link_path"
    fi
done

echo "✓ Synced ~/Documents/receipt/viewer/ → ~/ibitlabs/receipt-viewer/"
echo "  http://127.0.0.1:8090/ now reflects your edits."
echo "  Live chain symlinks preserved:"
for i in "${!LINK_NAMES[@]}"; do
    echo "    ${LINK_NAMES[$i]} → ${LINK_TARGETS[$i]}"
done
