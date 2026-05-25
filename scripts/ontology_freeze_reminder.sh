#!/bin/zsh
#
# ontology_freeze_reminder.sh — fires once a year on June 22 09:00 local
# via com.ibitlabs.ontology-freeze-reminder.plist.
#
# Why: claude-trader Phase B.1 shipped 2026-05-25 with a 30-day freeze on
# cognition_mode ontology growth — Claude may not introduce new modes
# beyond the starter 4 (Expansion / Compression / Regime Uncertain /
# Inventory Discovery) until 2026-06-25. The freeze ends on 6-25, but
# the SYMMETRIC PROPOSAL PROTOCOL (Claude proposes mode_proposal in
# framework reflection → operator ACCEPT/REJECT/REFINE via founder-notes)
# was deferred and needs to ship BEFORE 6-25 so that ontology growth has
# a discipline gate.
#
# This reminder fires June 22 (3 days before freeze ends). If the
# operator is still mid-other-work, the explicit ntfy with briefing is
# the lifeline that prevents "freeze quietly expires without protocol".
#
# Self-rate-limit: same-day duplicate fires write the same line to the
# marker file but only the first ntfy goes out.

set -u
set -o pipefail

NTFY_TOPIC="sol-sniper-bonny"
TODAY_ISO="$(date +%Y-%m-%d)"
STATE_DIR="$HOME/ibitlabs/state"
MARKER="$STATE_DIR/ontology_freeze_reminder_fired.txt"

mkdir -p "$STATE_DIR"

# Same-day idempotence
if [[ -f "$MARKER" ]] && grep -q "$TODAY_ISO" "$MARKER"; then
  echo "[$TODAY_ISO] ontology-freeze-reminder already fired today, skipping"
  exit 0
fi

# Briefing body — kept inline so the reminder is self-contained even if
# this script is read in isolation a year later.
read -r -d '' BODY <<'EOF' || true
Ontology freeze ends 2026-06-25. The symmetric proposal protocol must
ship before then.

The protocol (deferred at Phase B.1 ship, 2026-05-25):
  - Claude proposes a new cognition_mode via framework reflection
    (new field `mode_proposal`: definition + cadence_hint + entry/exit
    triggers + example regime episode that the existing 4 modes can't
    explain).
  - Operator ACCEPT / REJECT / REFINE via founder-notes channel.
  - Mode is NOT usable in state.json until accepted.
  - This makes ontology growth a two-sided epistemic protocol, not
    unilateral self-modification.

Reference docs:
  - ~/ibitlabs/docs/claude_trader_adaptive_cadence_design.md Section 9
  - memory: project_persistent_epistemic_organism_2026_05_25.md
  - memory: project_claude_trader_phase0_2026_05_25.md

Decision points:
  1. Does ontology growth need shipping NOW, or does freeze get
     extended (e.g. 90 days more) because existing 4 modes still feel
     sufficient?
  2. If shipping: schema for mode_proposal field, page rendering of
     proposal lineage, founder-notes response handling.
  3. If extending: simple SKILL edit + new reminder for the new date.

Don't let the freeze silently expire without explicit decision.
EOF

curl -s -o /dev/null --max-time 10 -X POST \
  -H "Title: [claude-trader] ontology freeze ends 6-25 — ship symmetric proposal protocol" \
  -H "Priority: high" \
  -H "Tags: warning,ontology" \
  -d "$BODY" \
  "https://ntfy.sh/$NTFY_TOPIC" \
  && echo "ntfy push sent" \
  || echo "ntfy push failed (non-fatal)"

# Record this fire
echo "$TODAY_ISO" >> "$MARKER"
echo "[$TODAY_ISO] ontology-freeze-reminder fired"
