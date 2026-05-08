"""Generate Ep 2-6 cards, SRT, VO text, and preview MP4s."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from cards_lib import (
    card_bilingual, card_code, card_terminal, card_split, card_big_number,
    ACCENT_RED, ACCENT_GREEN, ACCENT_YELLOW, FG, MUTED,
)

ROOT = Path.home() / "ibitlabs/content/ghost-series"
CARDS = ROOT / "assets/cards"
SCRIPTS = ROOT / "scripts"

# Each episode = list of beats. Each beat = (duration_s, card_spec, vo_en, vo_cn)
# card_spec is a tuple (type, **kwargs)

EPISODES = {
    "ep02": {
        "title": "Three Wrong Theories",
        "beats": [
            (4, ("bilingual",
                 "For 20 hours I knew exactly what the bug was.\nI was wrong three times.",
                 "有 20 小时我非常确定 bug 在哪。\n我错了三次。",
                 {"en_size": 72, "cn_size": 54}),
             "For 20 hours I knew exactly what the bug was. I was wrong three times.",
             "有 20 小时我非常确定 bug 在哪。我错了三次。"),
            (5, ("big_number", "#1",
                 "Market was too choppy.\nStrategy shouldn't have entered.",
                 "市场在震荡。\n策略不该入场。",
                 ACCENT_RED),
             "Theory one. Market was too choppy. The strategy shouldn't have entered.",
             "理论一。市场太震荡，策略不该入场。"),
            (5, ("bilingual",
                 "It entered cleanly.\nNot the bug.",
                 "但它入场得很干净。\n不是这个 bug。",
                 {"en_color": MUTED}),
             "It entered cleanly. Not the bug.",
             "但它入场得很干净。不是这个 bug。"),
            (5, ("big_number", "#2",
                 "Coinbase had maintenance\nthe night before.",
                 "前一晚 Coinbase 有\n计划维护。",
                 ACCENT_RED),
             "Theory two. Coinbase had scheduled maintenance the night before.",
             "理论二。前一晚 Coinbase 有计划维护。"),
            (5, ("bilingual",
                 "Maintenance ended\n25 hours before the bug hit.\nWrong time.",
                 "维护在 bug 出现前\n25 小时就结束了。\n时间对不上。",
                 {"en_size": 64, "cn_size": 48, "en_color": MUTED}),
             "It ended 25 hours before the bug hit. Wrong time.",
             "维护在 bug 出现前 25 小时就结束。时间对不上。"),
            (5, ("big_number", "#3",
                 "Live and shadow bots\nuse different logic.",
                 "Live 和 shadow\n代码逻辑不一样。",
                 ACCENT_RED),
             "Theory three. Live and shadow bots use different logic.",
             "理论三。Live 和 shadow 代码逻辑不一样。"),
            (5, ("bilingual",
                 "Different, yes.\nNot the one that mattered.",
                 "是不一样。\n但不是关键那条。",
                 {"en_color": MUTED}),
             "Different, yes. Not the one that mattered.",
             "是不一样。但不是关键那条。"),
            (7, ("bilingual",
                 "Three plausible theories.\nAll wrong.\nOne command proved it.",
                 "三个合理的理论。\n全错。\n一条命令证明了。",
                 {"en_size": 68, "cn_size": 52, "en_color": FG}),
             "Three plausible theories. All wrong. One command proved it.",
             "三个合理的理论。全错。一条命令证明了。"),
            (4, ("bilingual",
                 "Tomorrow: the command.",
                 "下一集：那条命令。",
                 {"en_size": 82, "cn_size": 62, "en_color": FG, "cn_color": FG}),
             "Tomorrow. The command.",
             "下一集。那条命令。"),
        ],
    },

    "ep03": {
        "title": "The One Command",
        "beats": [
            (4, ("bilingual",
                 "20 hours of thinking.\n1 command.\nGuess which won.",
                 "20 小时的分析。\n1 条命令。\n猜谁赢。",
                 {"en_size": 74, "cn_size": 56}),
             "Twenty hours of thinking versus one command. Guess which won.",
             "20 小时的分析，对一条命令。猜谁赢。"),
            (6, ("code", [
                "$ python3 scripts/",
                "    db_vs_exchange_reconcile.py",
                "    --days 2",
             ], None, None,
                 {0: FG, 1: ACCENT_GREEN, 2: ACCENT_GREEN}),
             "I ran the reconciler.",
             "我跑了对账器。"),
            (7, ("terminal", [
                "window: 2026-04-18 → 2026-04-20",
                "",
                "  db rows:          1",
                "  exchange fills:   3",
                "  unmatched fills:  2",
                "",
                "  EXCHANGE-ONLY  18:15  SELL",
                "  EXCHANGE-ONLY  23:39  BUY",
             ],
             "The bot knew one fill. The exchange knew three.",
             "机器人以为有 1 条。交易所说有 3 条。",
             [3, 4, 6, 7]),
             "The bot's database said one fill. The exchange said three. Two ghosts.",
             "机器人数据库说有 1 条成交。交易所说 3 条。两个幽灵。"),
            (5, ("bilingual",
                 "The reconciler doesn't think like me.",
                 "对账器不按我的思路想问题。",
                 {"en_size": 76, "cn_size": 54}),
             "The reconciler doesn't think like me.",
             "对账器不按我的思路想问题。"),
            (5, ("bilingual",
                 "It doesn't care about my theories.\nIt compares two lists.",
                 "它不理会我的理论。\n它只比两个列表。",
                 {"en_size": 68, "cn_size": 52}),
             "It doesn't care about my theories. It just compares two lists.",
             "它不理会我的理论。它只比两个列表。"),
            (6, ("bilingual",
                 "A second witness\nthat asks a different question.",
                 "第二个见证人，\n问一个不同的问题。",
                 {"en_size": 66, "cn_size": 52, "en_color": ACCENT_GREEN}),
             "A second witness. That asks a different question.",
             "第二个见证人。问一个不同的问题。"),
            (4, ("bilingual",
                 "The fix was 3 lines.",
                 "修复就 3 行代码。",
                 {"en_size": 92, "cn_size": 64, "en_color": FG, "cn_color": FG}),
             "The fix was three lines.",
             "修复就 3 行代码。"),
        ],
    },

    "ep04": {
        "title": "The Fix",
        "beats": [
            (4, ("bilingual",
                 "The bug that cost $40\nwas 3 lines of code.",
                 "让我亏 40 美元的 bug，\n修起来 3 行代码。",
                 {"en_size": 82, "cn_size": 58}),
             "The bug that cost forty dollars was three lines of code.",
             "让我亏 40 美元的 bug，修起来就 3 行代码。"),
            (8, ("code", [
                "- resp = self.exchange.create_market_order(",
                "-     symbol=symbol,",
                "-     side=close_side,",
                "-     amount=quantity,",
                "- )",
                "+ resp = self.exchange.close_perp_position(",
                "+     symbol=symbol,",
                "+     size=quantity,",
                "+ )",
             ], None, None, {0: "auto", 1: "auto", 2: "auto", 3: "auto", 4: "auto",
                             5: "auto", 6: "auto", 7: "auto", 8: "auto"},
                 {"code_size": 34}),
             "Out with the old. In with the new.",
             "旧代码去，新代码来。"),
            (5, ("bilingual",
                 "No more side parameter.\nThe SDK figures out direction.",
                 "不再传 side 参数。\nSDK 自己判断方向。",
                 {"en_size": 68, "cn_size": 52}),
             "No more side parameter. The SDK figures out the direction itself.",
             "不再传 side 参数。SDK 自己判断方向。"),
            (5, ("split",
                 "LONG", "→", "sell", ACCENT_GREEN,
                 "SHORT", "→", "buy", ACCENT_RED,
                 "SDK auto-detects direction",
                 "SDK 自动判别方向"),
             "If I'm long, it sells. If I'm short, it buys.",
             "多单就卖。空单就买。"),
            (5, ("bilingual",
                 "It physically cannot\nleave a residual.",
                 "它在物理上\n不可能留下残余。",
                 {"en_size": 80, "cn_size": 58, "en_color": ACCENT_GREEN}),
             "It physically cannot leave a residual.",
             "它在物理上不可能留下残余。"),
            (5, ("bilingual",
                 'Never trust a "close" is a close.\nMake the API prove it.',
                 "永远别默认\"平仓\"就是平仓。\n让 API 证明给你看。",
                 {"en_size": 62, "cn_size": 48, "en_color": FG, "cn_color": FG}),
             "Never trust that a close is a close. Make the A P I prove it.",
             "永远别默认平仓就是平仓。让 A P I 证明给你看。"),
        ],
    },

    "ep05": {
        "title": "The Canary",
        "beats": [
            (4, ("bilingual",
                 "First trade after the restart.\nTrade #61.\nThe canary.",
                 "重启后第一笔交易。\n第 61 号。\n这就是金丝雀。",
                 {"en_size": 70, "cn_size": 54}),
             "First trade after the restart. Trade number sixty-one. The canary.",
             "重启后的第一笔交易。第 61 号。这就是金丝雀。"),
            (6, ("split",
                 "ENTRY", "$85.27", "long", ACCENT_GREEN,
                 "EXIT", "$86.45", "trailing", ACCENT_GREEN,
                 "TRADE #61 · 2026-04-21",
                 "追踪止损平仓"),
             "Long at eighty-five twenty-seven. Closed at eighty-six forty-five.",
             "85.27 开多。86.45 平仓。"),
            (4, ("big_number", "+$10.35",
                 "Real money. Real position.",
                 "真钱。真仓位。",
                 ACCENT_GREEN),
             "Plus ten dollars thirty-five. On real money.",
             "赚了 10.35 美元。用真钱。"),
            (7, ("terminal", [
                "$ reconcile --days 1",
                "",
                "  db rows:          2",
                "  exchange fills:   2",
                "  unmatched:        0",
                "  orphans:          0",
                "",
                "  ✅ clean — no discrepancies",
             ], "DB matches exchange. Zero residual.",
                 "DB 和交易所对齐。零残余。",
                 [7]),
             "Two D-B rows. Two exchange fills. Zero unmatched. Zero residual.",
             "DB 两条。交易所两条。零不匹配。零残余。"),
            (5, ("bilingual",
                 "The fix works.\nIn production.\nOn real money.",
                 "修复有效。\n在生产。\n用真钱。",
                 {"en_size": 78, "cn_size": 58, "en_color": ACCENT_GREEN}),
             "The fix works. In production. On real money.",
             "修复有效。在生产。用真钱。"),
            (4, ("bilingual",
                 "But one trade isn't trust.",
                 "但一笔交易还不算信任。",
                 {"en_size": 80, "cn_size": 56, "en_color": MUTED}),
             "But one trade isn't trust.",
             "但一笔交易还不算信任。"),
            (4, ("bilingual",
                 "Receipts, not promises.",
                 "要收据，不要承诺。",
                 {"en_size": 96, "cn_size": 66, "en_color": FG, "cn_color": FG}),
             "Receipts. Not promises.",
             "要收据，不要承诺。"),
        ],
    },

    "ep06": {
        "title": "The Untested Twin",
        "beats": [
            (5, ("split",
                 "TRAILING", "✓", "validated", ACCENT_GREEN,
                 "STOP-LOSS", "?", "not yet", ACCENT_YELLOW,
                 "CLOSE PATHS · POST-FIX",
                 "两条平仓路径 · 修复后状态"),
             "Trailing stop path. Validated. Hard stop-loss path. Not yet.",
             "追踪止损路径。已验证。硬止损路径。还没。"),
            (5, ("bilingual",
                 "Same fix.\nSame code.\nStop-loss hasn't fired since the patch.",
                 "同一修复。\n同一代码。\n但补丁上线后 SL 还没触发过。",
                 {"en_size": 62, "cn_size": 48}),
             "Same fix. Same code. But stop-loss hasn't fired since the patch.",
             "同一修复。同一代码。但补丁上线后止损还没打过。"),
            (5, ("bilingual",
                 "So I wait.\nSize small.",
                 "所以我等。\n仓位压小。",
                 {"en_size": 92, "cn_size": 66, "en_color": FG}),
             "So I wait. I size small.",
             "所以我等。仓位压小。"),
            (5, ("bilingual",
                 "When the next SL hits,\nI'll know in 30 seconds.",
                 "下一次 SL 打的时候，\n30 秒内我就知道结果。",
                 {"en_size": 66, "cn_size": 52}),
             "When the next S-L hits, I'll know in thirty seconds.",
             "下一次 SL 打的时候，30 秒内我就知道结果。"),
            (7, ("bilingual",
                 "Silent failures\ndon't announce themselves.",
                 "静默失败\n不会自己喊出来。",
                 {"en_size": 80, "cn_size": 60, "en_color": ACCENT_RED}),
             "Silent failures don't announce themselves.",
             "静默失败不会自己喊出来。"),
            (6, ("bilingual",
                 "You have to build\nthe signal that catches them.",
                 "你得自己造出\n抓它的信号。",
                 {"en_size": 66, "cn_size": 52, "en_color": FG}),
             "You have to build the signal that catches them.",
             "你得自己造出抓它的信号。"),
            (5, ("bilingual",
                 "If you're building with an API\u2014\ncheck what \"close\" actually does.",
                 "如果你在接 API \u2014\u2014\n去确认\"平仓\"到底做了什么。",
                 {"en_size": 58, "cn_size": 46, "en_color": MUTED}),
             "If you're building with an A P I — check what close actually does.",
             "如果你在接 API —— 去确认平仓到底做了什么。"),
            (4, ("bilingual",
                 "I learned it the $40 way.",
                 "我是花了 40 美元学会的。",
                 {"en_size": 88, "cn_size": 60, "en_color": FG, "cn_color": FG}),
             "I learned it the forty-dollar way.",
             "我是花了 40 美元学会的。"),
        ],
    },
}


def render_card(filename, spec):
    type_ = spec[0]
    if type_ == "bilingual":
        en, cn = spec[1], spec[2]
        kwargs = spec[3] if len(spec) > 3 else {}
        card_bilingual(filename, en, cn, **kwargs)
    elif type_ == "code":
        lines, cap_en, cap_cn, line_colors = spec[1], spec[2], spec[3], spec[4]
        kwargs = spec[5] if len(spec) > 5 else {}
        card_code(filename, lines, caption_en=cap_en, caption_cn=cap_cn,
                  line_colors=line_colors, **kwargs)
    elif type_ == "terminal":
        lines, cap_en, cap_cn, highlight = spec[1], spec[2], spec[3], spec[4]
        card_terminal(filename, lines, caption_en=cap_en, caption_cn=cap_cn,
                      highlight_lines=highlight)
    elif type_ == "split":
        (ll, lv, ld, lc, rl, rv, rd, rc, banner, bottom) = spec[1:11]
        card_split(filename, ll, lv, ld, lc, rl, rv, rd, rc,
                   top_banner=banner, bottom_cn=bottom)
    elif type_ == "big_number":
        number, label_en, label_cn, color = spec[1], spec[2], spec[3], spec[4]
        card_big_number(filename, number, color, label_en, label_cn)


def srt_ts(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_episode(ep_id, data):
    print(f"\n=== {ep_id.upper()} · {data['title']} ===")
    ep_cards = CARDS / ep_id
    ep_cards.mkdir(parents=True, exist_ok=True)

    # Generate cards + collect timing
    beats = data["beats"]
    srt_entries = []
    vo_en_lines = []
    vo_cn_lines = []
    concat_lines = []
    t = 0.0
    for i, (dur, spec, vo_en, vo_cn) in enumerate(beats, start=1):
        fn = ep_cards / f"{i:02d}.png"
        render_card(str(fn), spec)
        print(f"  {fn.name}  ({dur}s)")
        srt_entries.append((len(srt_entries) + 1, t, t + dur, vo_en, vo_cn))
        vo_en_lines.append(vo_en)
        vo_cn_lines.append(vo_cn)
        concat_lines.append(f"file '../assets/cards/{ep_id}/{i:02d}.png'\nduration {dur}")
        t += dur
    # concat demuxer quirk: repeat last file
    concat_lines.append(f"file '../assets/cards/{ep_id}/{len(beats):02d}.png'")

    # SRT
    srt_path = SCRIPTS / f"{ep_id}_subtitles.srt"
    srt_text = ""
    for idx, start, end, en, cn in srt_entries:
        srt_text += f"{idx}\n{srt_ts(start)} --> {srt_ts(end)}\n{en}\n{cn}\n\n"
    srt_path.write_text(srt_text)
    print(f"  → SRT {srt_path.name}")

    # VO scripts
    (SCRIPTS / f"{ep_id}_vo_en.txt").write_text("\n\n".join(vo_en_lines) + "\n")
    (SCRIPTS / f"{ep_id}_vo_cn.txt").write_text("\n\n".join(vo_cn_lines) + "\n")
    print(f"  → VO EN + CN")

    # Concat
    (SCRIPTS / f"{ep_id}_concat.txt").write_text("\n".join(concat_lines) + "\n")
    print(f"  → concat {ep_id}_concat.txt  (total {t:.1f}s)")

    return t


if __name__ == "__main__":
    total = 0.0
    for ep_id, data in EPISODES.items():
        total += build_episode(ep_id, data)
    print(f"\n✅ Built {len(EPISODES)} episodes · total {total:.1f}s")
