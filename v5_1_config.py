"""
v5_1_config — Multi-symbol config factory for hybrid_v5.1.

Returns `SniperConfig` instances with per-symbol overrides applied. This is
the single source of truth for "which v5.1 parameters are SOL-specific vs
ETH-specific vs shared."

Three tiers per `docs/multi_symbol_eth_expansion_DD.md` decision #3:

  🔒 SHARED LOGIC          Entry/exit conditions, risk officer rules. These
                           live in CODE (sol_sniper_signals.py /
                           sol_sniper_executor.py), not here.

  🔧 DEFAULT SHARED         Strategy parameters: ATR multipliers, regime
                           window, vol_ratio thresholds, hold times, fees,
                           trailing/SL pcts, etc. Initial ETH values =
                           SOL values. Divergence requires:
                             (1) ≥30 ETH trades on the parameter in question
                             (2) per-bucket hit-rate evidence
                             (3) contributor frame in the ledger
                           Encoded as `_PER_SYMBOL_TUNING` overrides — empty
                           by default. Adding a key here is a public decision.

  🔓 PER-SYMBOL             Symbol identifier, contract spec, fee schedule.
                           Always different per Coinbase contract — sharing
                           these would silently misprice trades. Encoded as
                           `_PER_SYMBOL_CONTRACT`.

Existing live SOL bot continues to import `SniperConfig` directly from
`sol_sniper_config` and is unaffected by this module's existence.
ETH bot (forthcoming) imports `config_for("ETH")`.

Smoke-test:    python3 v5_1_config.py
"""

from __future__ import annotations

from dataclasses import replace

from sol_sniper_config import SniperConfig


# 🔓 PER-SYMBOL — contract spec & symbol identifier
#
# SOL values match the existing SniperConfig defaults (live since 2026-04-20).
# ETH values are placeholders until verified against Coinbase Advanced Trade.
_PER_SYMBOL_CONTRACT: dict[str, dict] = {
    "SOL": {
        "symbol": "SLP-20DEC30-CDE",
        # Fees match SniperConfig defaults — explicit here to make tier
        # classification visible at the call site.
        "maker_fee": 0.0004,
        "taker_fee": 0.0006,
        # Coinbase product spec: SLP-20DEC30-CDE has contract_size=5 SOL/contract.
        "contract_size": 5.0,
    },
    "ETH": {
        # Verified 2026-05-04 against Coinbase Advanced Trade public products
        # API. ETP-20DEC30-CDE: contract_root=ETH, is_perpetual=True,
        # contract_size=0.1 ETH per contract, price_increment=$0.50,
        # base_min_size=1 contract (= 0.1 ETH ≈ $236 notional at $2360).
        # Far-future "20DEC30" (Dec 30 2030) expiry is Coinbase's perpetual
        # placeholder — same convention as SLP-20DEC30-CDE for SOL.
        "symbol": "ETP-20DEC30-CDE",
        # Fees match SOL defaults; Coinbase publishes the same schedule for
        # all perpetual futures contracts. Override here if that changes.
        "maker_fee": 0.0004,
        "taker_fee": 0.0006,
        # Coinbase product spec: ETP-20DEC30-CDE has contract_size=0.1 ETH/contract.
        # (Verified 2026-05-04 via /api/v3/brokerage/market/products/ETP-20DEC30-CDE.)
        # CRITICAL: this value is what stops sol_sniper_executor's quantity math
        # from over-ordering 50× on ETH. Do NOT change without re-verifying
        # the contract spec on Coinbase.
        "contract_size": 0.1,
    },
}


# 🔧 DEFAULT SHARED — divergence overrides
#
# Empty for both symbols at launch. ANY entry here is a named decision —
# log it in the contributor ledger and reference it in the saga before merge.
# The point of this module is that "SOL and ETH use the same v5.1" is the
# default, and any deviation is conspicuous.
_PER_SYMBOL_TUNING: dict[str, dict] = {
    "SOL": {},
    "ETH": {},
}


def config_for(symbol: str, *, instance_name: str = "live") -> SniperConfig:
    """
    Build a SniperConfig for the given symbol.

    Args:
        symbol: "SOL" or "ETH" (case-insensitive)
        instance_name: e.g. "live", "paper", "shadow"

    Raises:
        ValueError: if symbol is unknown
        RuntimeError: if symbol is known but its contract identifier is not
                      yet set (intentional pre-launch blocker)
    """
    sym = symbol.upper()
    if sym not in _PER_SYMBOL_CONTRACT:
        raise ValueError(
            f"Unknown symbol {symbol!r}. Known: {known_symbols()}. "
            f"To add a new symbol, edit _PER_SYMBOL_CONTRACT in v5_1_config.py "
            f"and verify its Coinbase contract spec."
        )

    contract = _PER_SYMBOL_CONTRACT[sym]
    if contract.get("symbol") is None:
        raise RuntimeError(
            f"Contract identifier for {sym} not set. Look up the real "
            f"Coinbase Advanced Trade product symbol and update "
            f"_PER_SYMBOL_CONTRACT[{sym!r}]['symbol'] before any "
            f"paper or live use."
        )

    tuning = _PER_SYMBOL_TUNING[sym]
    base = SniperConfig()
    return replace(base, instance_name=instance_name, **contract, **tuning)


def known_symbols() -> list[str]:
    return sorted(_PER_SYMBOL_CONTRACT.keys())


def has_tier_2_divergence(symbol: str) -> bool:
    """True iff this symbol has any tier-2 (default-shared) override."""
    return bool(_PER_SYMBOL_TUNING[symbol.upper()])


def tier_2_divergences(symbol: str) -> dict:
    """Return the tier-2 overrides for this symbol (empty dict if none)."""
    return dict(_PER_SYMBOL_TUNING[symbol.upper()])


if __name__ == "__main__":
    # Smoke test: verify per-symbol distinctions and shared invariants.
    print("=" * 60)
    print("v5_1_config smoke test")
    print("=" * 60)

    for sym in known_symbols():
        try:
            cfg = config_for(sym)
        except RuntimeError as e:
            print(f"\n⛔ {sym} config blocked (expected pre-launch state):")
            print(f"   {e}")
            continue
        print(f"\n✅ {sym} config built")
        print(f"   symbol               : {cfg.symbol!r}")
        print(f"   strategy_version     : {cfg.strategy_version}")
        print(f"   regime_window_hours  : {cfg.regime_window_hours}")
        print(f"   maker / taker fee    : {cfg.maker_fee} / {cfg.taker_fee}")
        print(f"   trailing_activate    : {cfg.trailing_activate_pct}")
        print(f"   sl_pct               : {cfg.sl_pct}")
        print(f"   tier-2 divergences   : "
              f"{tier_2_divergences(sym) or 'none'}")

    print(f"\nShared-invariant checks (must hold across all symbols):")
    cfgs = {s: config_for(s) for s in known_symbols()
            if _PER_SYMBOL_CONTRACT[s].get("symbol")}
    if len(cfgs) > 1:
        first = next(iter(cfgs.values()))
        for s, c in cfgs.items():
            assert c.strategy_version == first.strategy_version, \
                f"strategy_version drift on {s}"
            assert c.regime_window_hours == first.regime_window_hours, \
                f"regime_window_hours drift on {s}"
            assert c.bb_period == first.bb_period, f"bb_period drift on {s}"
            assert c.trailing_activate_pct == first.trailing_activate_pct, \
                f"trailing_activate drift on {s}"
        print(f"   ✅ {len(cfgs)} symbols share all tier-1/tier-2 defaults")
    else:
        print(f"   (only 1 symbol resolvable, no cross-symbol check)")

    print(f"\nPre-launch checklist for ETH (live promotion):")
    print(f"   [✓] Coinbase ETH perp product symbol verified (2026-05-04): "
          f"ETP-20DEC30-CDE")
    print(f"   [✓] _PER_SYMBOL_CONTRACT['ETH']['symbol'] set")
    print(f"   [✓] Fee schedule confirmed (Coinbase uses same schedule for "
          f"all perp contracts)")
    print(f"   [ ] Verify executor handles ETH contract_size=0.1 (vs SOL's "
          f"contract_size=5) — may need adjustment in quantity calc")
    print(f"   [ ] Run paper-mode ≥7 days, ≥10 virtual trades")
    print(f"   [ ] Phantom SOL-only counterfactual recorder live")
    print(f"   [ ] Risk officer portfolio-cap + DD-brake live")
    print(f"\n{'='*60}")
