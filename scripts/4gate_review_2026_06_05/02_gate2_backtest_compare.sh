#!/bin/bash
# Gate 2: Direct backtest comparison with lever decomposition.
#
# Prep doc lines 83-86: re-run backtest_live_vs_shadow.py with shadow's
# exact params (grid ON + trailing 0.4%/0.5%) over the v5.1 baseline
# 120d window. Decompose: which lever is responsible — grid? trailing?
# combined?
#
# Decision rule (codified for op review on 06-05):
#   combined PF >= baseline PF + 0.10 → PROMOTE candidate
#   combined PF <  baseline PF        → DEFER, do not promote
#   only one lever beats baseline     → promote that lever, drop the other

set -euo pipefail
cd ~/ibitlabs

WINDOW_DAYS=120
BASELINE_PF_LIVE=1.32  # cf. project_v52_spec_phase_a.md
OUT_DIR=~/ibitlabs/logs/4gate_2026-06-05
mkdir -p "$OUT_DIR"

# Confirm the backtest script exists before we start
if [ ! -f backtest_live_vs_shadow.py ]; then
    echo "FATAL: backtest_live_vs_shadow.py missing. Adjust path or restore."
    exit 1
fi

echo "=== Gate 2: backtest decomposition over ${WINDOW_DAYS}d ==="
echo "Baseline PF (live, --no-grid): ${BASELINE_PF_LIVE}"
echo ""

# 4 variants. The flag set for each MUST match what the live process would
# run if promoted — otherwise the comparison is meaningless.
declare -A VARIANTS=(
    [baseline]="--no-grid"
    [grid_only]=""
    [trail_only]="--no-grid --trailing-activate 0.004 --trailing-stop 0.005"
    [combined]="--trailing-activate 0.004 --trailing-stop 0.005"
)

for variant in baseline grid_only trail_only combined; do
    echo "--- variant: $variant ---"
    flags="${VARIANTS[$variant]}"
    out_file="${OUT_DIR}/gate2_${variant}.out"
    # NOTE 2026-06-05: backtest_live_vs_shadow.py CLI surface may have
    # drifted; if it doesn't accept --days or one of the flags above,
    # fix the variant flags HERE before re-running. Don't silently
    # work around — a broken backtest produces a wrong decision.
    python3 backtest_live_vs_shadow.py --days "$WINDOW_DAYS" $flags 2>&1 | tee "$out_file"
    echo "  saved to: $out_file"
    echo ""
done

echo "=== Compare ==="
echo "Manual step: read each gate2_*.out, extract PF + total return."
echo "Apply decision rule:"
echo "  combined PF >= ${BASELINE_PF_LIVE} + 0.10 = $(python3 -c "print(${BASELINE_PF_LIVE}+0.10)") → PROMOTE candidate (proceed to Gate 3)"
echo "  combined PF <  ${BASELINE_PF_LIVE}            → DEFER (skip Gate 3-4)"
echo "  one-lever wins                                 → promote that single lever, document in Gate 4"
