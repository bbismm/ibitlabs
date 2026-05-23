"""Anchor a backtest run via Receipt protocol (~/Documents/receipt/).

Emits a Receipt-spec JSONL chain covering the backtest:
  seq 0           claim            — "we will run this backtest" (with manifest hashes)
  seq 1           external_action  — "executed; here's the summary"
  seq 2..N+1      verified         — one per closed trade (EXIT event)
  seq N+2         anchor           — Merkle root of seq 0..N+1, with CID/URI

If PINATA_JWT is unset, anchor uses dry-run placeholders (file:// gateway) and
prints the anchor_daily.py command for the user to publish manually. Backtest
anchors are a SEPARATE chain from the LIVE bot's chain — does not pollute the
sniper-v5.1-live receipt chain or the 6-10 clean-realtime gate.

Closes mission #3 三件套: 模拟 (ibit-backtest run) → 治理 (export-shadow + harness)
→ 锚定 (anchor + receipt viewer).
"""

from __future__ import annotations
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Documents" / "receipt"))
from receipt import Receipt  # noqa: E402
from receipt.chain import verify_chain  # noqa: E402


def _merkle_root(hashes: list) -> str:
    """SHA-256 binary Merkle tree (matches ~/Documents/receipt/scripts/anchor_daily.py)."""
    if not hashes:
        return "sha256:" + "0" * 64
    layer = [bytes.fromhex(h.split(":", 1)[1]) for h in hashes]
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        nxt = []
        for i in range(0, len(layer), 2):
            nxt.append(hashlib.sha256(layer[i] + layer[i + 1]).digest())
        layer = nxt
    return "sha256:" + layer[0].hex()


def anchor_run(run_dir_str: str, output_dir_str=None) -> int:
    run_dir = Path(run_dir_str).expanduser().resolve()
    manifest_path = run_dir / "manifest.json"
    events_path = run_dir / "events.jsonl"
    if not manifest_path.exists() or not events_path.exists():
        print(f"[anchor] missing manifest.json or events.jsonl in {run_dir}", file=sys.stderr)
        return 2

    manifest = json.loads(manifest_path.read_text())
    events = [json.loads(l) for l in events_path.read_text().splitlines() if l.strip()]
    exits = [e for e in events if e.get("kind") == "EXIT"]

    out_dir = (Path(output_dir_str).expanduser().resolve()
               if output_dir_str else run_dir / "anchor")
    out_dir.mkdir(parents=True, exist_ok=True)
    chain_path = out_dir / "chain.receipt.jsonl"
    if chain_path.exists():
        chain_path.unlink()

    agent = (
        f"ibitlabs/ibit-backtest/{manifest['strategy_name']}"
        f"/v{manifest['strategy_version']}"
    )
    r = Receipt(agent=agent, out_path=str(chain_path))

    total_pnl = sum(e.get("pnl", 0) for e in exits)
    wins = sum(1 for e in exits if (e.get("pnl") or 0) > 0)
    wr_pct = round(100 * wins / len(exits), 2) if exits else 0.0

    # seq 0: claim — backtest run intent + reproducibility hashes
    r.claim(
        action="run_backtest",
        run_id=manifest["run_id"],
        strategy=manifest["strategy_name"],
        strategy_version=manifest["strategy_version"],
        symbol=manifest["symbol"],
        period=manifest["period"],
        config_hash=manifest["config_hash"],
        data_window_hash=manifest["data_window_hash"],
        code_commit=manifest["code_commit"],
        known_gaps=manifest.get("known_gaps") or [],
    )

    # seq 1: external_action — executed; summary
    r.external_action(
        claim_seq=0,
        venue="ibit_backtest_simulator",
        request={
            "engine": (manifest.get("config") or {}).get("engine", "unknown"),
            "fee_model": manifest.get("fee_model", ""),
            "n_bars_15m": manifest.get("n_bars_15m"),
            "n_bars_1h": manifest.get("n_bars_1h"),
        },
        response={
            "status": 200,
            "n_trades": len(exits),
            "total_pnl": round(total_pnl, 4),
            "wins": wins,
            "wr_pct": wr_pct,
        },
    )

    # seq 2..N+1: verified events — one per closed trade.
    # trust_tier="backfill_local" — backtest is local replay of historical bars,
    # no external venue cross-check (LIVE bot uses "exchange_realtime").
    for i, e in enumerate(exits):
        r.verified(
            claim_seq=0,
            trust_tier="backfill_local",
            match={
                "symbol": e.get("symbol"),
                "side": e.get("direction"),
                "size": e.get("quantity"),
                "price_match": True,
                "time_match": True,
                "id_match": True,
                "tolerance_used": 0,
            },
            action_seq=1,
            source="ibit_backtest_simulator",
            fill_price=e.get("exit_price"),
            filled_size=e.get("quantity"),
            trade_index=i,
            symbol=e.get("symbol"),
            direction=e.get("direction"),
            entry_price=e.get("entry_price"),
            entry_ts=e.get("entry_ts"),
            exit_ts=e.get("ts"),
            pnl=e.get("pnl"),
            fees=e.get("fees"),
            hours_held=e.get("hours_held"),
            exit_reason=e.get("exit_reason"),
            regime=e.get("regime"),
        )

    # seq N+2: reconciliation — backtest is its own state-of-truth,
    # so matched=N / unmatched=0 / errors=0 by construction. This keeps
    # verify_chain() from returning STALE_RECONCILIATION on the final chain.
    r.reconciliation(
        period="backtest_full_window",
        trust_tier="backfill_local",
        matched=len(exits),
        unmatched=0,
        errors=0,
        n_entries=len(events) - len(exits),  # ENTRY count
        n_closes=len(exits),
        total_pnl=round(total_pnl, 4),
        wr_pct=wr_pct,
    )

    # Compute Merkle over seq 0..N+2 (everything except the upcoming anchor)
    pre_anchor = [json.loads(l) for l in chain_path.read_text().splitlines() if l.strip()]
    merkle_root = _merkle_root([evt["hash"] for evt in pre_anchor])

    # seq N+2: anchor
    has_pinata = bool(os.environ.get("PINATA_JWT"))
    if has_pinata:
        cid = "PENDING_UPLOAD"
        anchor_uri = "ipfs://PENDING_UPLOAD"
        gateway_url = "https://gateway.pinata.cloud/ipfs/PENDING_UPLOAD"
    else:
        cid = "DRY_RUN_NO_PINATA_JWT"
        anchor_uri = "dry-run:no-pinata-jwt"
        gateway_url = f"file://{chain_path}"

    r.anchor(
        merkle_root=merkle_root,
        anchor_uri=anchor_uri,
        anchor_kind="ipfs",
        cid=cid,
        events_covered=len(pre_anchor),
        gateway_url=gateway_url,
    )

    # Write latest.json (matches sniper-v5.1-live shape)
    now = datetime.now(timezone.utc)
    latest = {
        "agent": agent,
        "anchor": {
            "seq": len(pre_anchor),
            "ts_ms": int(now.timestamp() * 1000),
            "ts_iso": now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "cid": cid,
            "anchor_uri": anchor_uri,
            "gateway_url": gateway_url,
            "merkle_root": merkle_root,
            "events_covered": len(pre_anchor),
        },
        "published_at_iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "backtest_run_id": manifest["run_id"],
    }
    latest_path = out_dir / "latest.json"
    latest_path.write_text(json.dumps(latest, indent=2))

    # Verify chain integrity (re-runs hash chain over all events)
    final_events = [json.loads(l) for l in chain_path.read_text().splitlines() if l.strip()]
    try:
        report = verify_chain(final_events)
        verify_label = (
            getattr(report, "status", None) or getattr(report, "value", None) or str(report)
        )
    except Exception as ex:
        verify_label = f"verify_error: {ex}"

    final = final_events
    print(f"[anchor] chain  -> {chain_path}")
    print(f"[anchor] events -> {len(final)} (1 claim + 1 external_action + {len(exits)} verified + 1 reconciliation + 1 anchor)")
    print(f"[anchor] merkle -> {merkle_root}")
    print(f"[anchor] verify -> {verify_label}")
    print(f"[anchor] latest -> {latest_path}")
    print()
    if has_pinata:
        print("PINATA_JWT detected — replace placeholder CID by running:")
    else:
        print("DRY-RUN (no PINATA_JWT). To publish to IPFS, run:")
    print(
        f"  PYTHONPATH=~/Documents/receipt python3 "
        f"~/Documents/receipt/scripts/anchor_daily.py --chain {chain_path}"
    )
    print()
    print("Once published, anyone can verify in the public viewer:")
    print("  https://www.ibitlabs.com/receipt/viewer/?chain=<gateway_url>")
    return 0
