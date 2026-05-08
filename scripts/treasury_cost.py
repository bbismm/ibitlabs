#!/usr/bin/env python3
"""
treasury_cost.py — Emit the AI's daily cost-to-run snapshot.

Phase A of the AI Treasury experiment (see docs/AI_TREASURY_V0.md).

This script captures how much money the iBitLabs trading bot burns every
day to stay alive — cloud, hardware, electricity, and model subscription.

Design notes:
  - No network calls. All figures are constants or locally computed.
  - No DB reads. This script is purely the "fixed cost" side of the ledger.
  - Runway calculation lives in treasury_runway.py.
  - Output is a single JSON file at state/treasury_cost.json. Atomic write.
  - Safe to run from cron, from a harness, or by hand at any cadence.

Change any constant below and rerun — downstream scripts pick it up
immediately.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ─── Identity ────────────────────────────────────────────────────────────────
# Working handle for the AI. Can be renamed in one place. See docs/AI_TREASURY_V0.md §7.
AGENT_NAME = "Agent Carry"

# ─── Constants: locked 2026-04-11 ────────────────────────────────────────────
# Keep this table in sync with docs/AI_TREASURY_V0.md §1.
# Every number here must have a defensible source in the doc.

# L1 — Direct cloud & API ($/month)
L1_CLOUDFLARE_WORKERS_PAID = 5.00   # flat plan rate; KV + Pages within free tier
L1_DOMAINS                 = 1.25   # ibitlabs.com + trade.ibitlabs.com, $15/yr amortized
L1_COINBASE_API            = 0.00   # free tier; trading fees live in P&L not here
L1_TELEGRAM_BOT            = 0.00   # free
L1_STRIPE_FIXED            = 0.00   # only counted once subscription revenue exists

# L2 — Hardware & network ($/month)
# Mac Mini electricity: 15W avg × 24h × 30.44d / 1000 = 10.96 kWh/mo
# NYC ConEd residential ~ $0.33/kWh (2026-04-11 rate provided by Bonny)
L2_ELECTRICITY_KWH_PER_MONTH = 10.96
L2_ELECTRICITY_RATE_USD_KWH  = 0.33
L2_ELECTRICITY               = round(
    L2_ELECTRICITY_KWH_PER_MONTH * L2_ELECTRICITY_RATE_USD_KWH, 2
)
L2_INTERNET_AMORTIZED = 5.00  # 10% of household ISP bill

# L3 — Anthropic / Claude ($/month)
L3_CLAUDE_SUBSCRIPTION = 200.00  # flat Max plan, confirmed 2026-04-11

# ─── Paths ───────────────────────────────────────────────────────────────────
REPO_ROOT   = Path(__file__).resolve().parent.parent
STATE_DIR   = REPO_ROOT / "state"
OUTPUT_FILE = STATE_DIR / "treasury_cost.json"

# Standard month length used to convert monthly → daily.
# 30.44 = 365.25 / 12. Consistent with the kWh calc above.
DAYS_PER_MONTH = 30.44


def compute_cost() -> dict:
    l1 = round(
        L1_CLOUDFLARE_WORKERS_PAID
        + L1_DOMAINS
        + L1_COINBASE_API
        + L1_TELEGRAM_BOT
        + L1_STRIPE_FIXED,
        2,
    )
    l2 = round(L2_ELECTRICITY + L2_INTERNET_AMORTIZED, 2)
    l3 = round(L3_CLAUDE_SUBSCRIPTION, 2)
    total_month = round(l1 + l2 + l3, 2)
    total_day = round(total_month / DAYS_PER_MONTH, 4)

    return {
        "agent_name": AGENT_NAME,
        "schema_version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "currency": "USD",
        "period": "monthly",
        "days_per_month": DAYS_PER_MONTH,
        "layers": {
            "L1_cloud_api": {
                "subtotal": l1,
                "items": {
                    "cloudflare_workers_paid": L1_CLOUDFLARE_WORKERS_PAID,
                    "domains": L1_DOMAINS,
                    "coinbase_api": L1_COINBASE_API,
                    "telegram_bot": L1_TELEGRAM_BOT,
                    "stripe_fixed": L1_STRIPE_FIXED,
                },
                "note": "flat; CF billing API not accessible with KV-scoped token",
            },
            "L2_hardware_network": {
                "subtotal": l2,
                "items": {
                    "electricity": L2_ELECTRICITY,
                    "internet_amortized": L2_INTERNET_AMORTIZED,
                },
                "electricity_calc": {
                    "kwh_per_month": L2_ELECTRICITY_KWH_PER_MONTH,
                    "rate_usd_per_kwh": L2_ELECTRICITY_RATE_USD_KWH,
                    "source": "NYC ConEd residential, 2026-04-11",
                    "device_assumption": "Mac Mini M-series, 15W avg, 24/7",
                },
            },
            "L3_claude": {
                "subtotal": l3,
                "items": {
                    "claude_max_subscription": L3_CLAUDE_SUBSCRIPTION,
                },
                "note": "flat subscription; burn does not scale with agent activity",
            },
        },
        "total_usd_per_month": total_month,
        "total_usd_per_day": total_day,
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write to a temp file in the same directory, then rename — atomic on POSIX.
    fd, tmp_path = tempfile.mkstemp(
        prefix=".treasury_cost_", suffix=".json", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def main() -> int:
    payload = compute_cost()
    atomic_write_json(OUTPUT_FILE, payload)
    print(
        f"[treasury_cost] {AGENT_NAME}: "
        f"${payload['total_usd_per_month']:.2f}/mo "
        f"→ ${payload['total_usd_per_day']:.4f}/day "
        f"(L1 ${payload['layers']['L1_cloud_api']['subtotal']:.2f} · "
        f"L2 ${payload['layers']['L2_hardware_network']['subtotal']:.2f} · "
        f"L3 ${payload['layers']['L3_claude']['subtotal']:.2f})"
    )
    print(f"[treasury_cost] wrote {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
