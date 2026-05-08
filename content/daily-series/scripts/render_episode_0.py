"""Render Episode 0 — prologue. "Why I'm handing $1,000 to AI"

Sets up: who Bonny is, why $1,000 (not her limit — an ordinary person's stake),
and the real mission: if this works for her, it can work for anyone with $1,000.

Output:
  out/ep_0_en.mp4
  out/ep_0_cn.mp4
"""
import sys, subprocess
from pathlib import Path

ROOT = Path.home() / "ibitlabs/content/daily-series"
sys.path.insert(0, str(ROOT / "lib"))
from cards_warm import (
    card_signature_intro, card_topic_reveal, card_bilingual, card_stat,
    card_single, card_outro,
    CREAM_BG, FG, MUTED, SAGE, TERRACOTTA, INK, INK_MUTED,
)

CARD_DIR = ROOT / "assets/cards/ep_0"
CARD_DIR.mkdir(parents=True, exist_ok=True)


def render_cards():
    # 1. About — "Bonny · 9 years in crypto · 2017 → 2026"
    card_stat(str(CARD_DIR / "01_about.png"),
              value="9",
              label_en="years in crypto · since 2017",
              label_cn="币圈 9 年 · 2017 年入场",
              value_color=TERRACOTTA)

    # 2. DeFi gas flex — "$100s on a single transaction"
    card_stat(str(CARD_DIR / "02_defi_gas.png"),
              value="$100s",
              label_en="one DeFi gas fee, peak cycle",
              label_cn="DeFi gas 最疯时 · 一笔手续费",
              value_color=MUTED)

    # 3. $1,000 hook
    card_stat(str(CARD_DIR / "03_stake.png"),
              value="$1,000",
              label_en="what an ordinary person can risk",
              label_cn="一个普通人能掏得起的金额",
              value_color=TERRACOTTA)

    # 4. The question (quote card)
    card_bilingual(str(CARD_DIR / "04_question.png"),
                   '"Can you write me\na trading bot?"',
                   '"你能不能帮我写一个\n交易机器人？"',
                   en_size=76, cn_size=62,
                   en_color=FG, cn_color=SAGE)

    # 5. 7 days
    card_stat(str(CARD_DIR / "05_7days.png"),
              value="7",
              label_en="days later · AI wrote it",
              label_cn="7 天之后 · AI 写出来了",
              value_color=SAGE)

    # 6. Hero declaration (米白卡) — "If I can, you can"
    card_single(str(CARD_DIR / "06_declaration.png"),
                text="If I can,\nyou can.",
                size=140, color=TERRACOTTA, font_type="en",
                bg=CREAM_BG, accent=True)
    card_single(str(CARD_DIR / "06_declaration_cn.png"),
                text="如果我能，\n你也能。",
                size=130, color=TERRACOTTA, font_type="cn",
                bg=CREAM_BG, accent=True)

    # 7. Transparency promise
    card_bilingual(str(CARD_DIR / "07_transparent.png"),
                   "Every loss.\nEvery win.\nEvery bug.\nPublic.",
                   "每一笔亏损。\n每一笔盈利。\n每一个 bug。\n公开发。",
                   en_size=70, cn_size=56,
                   en_color=FG, cn_color=MUTED)

    # 8. Handoff — Day 1 preview
    card_signature_intro(str(CARD_DIR / "08_handoff_en.png"), day_n=1, is_english=True)
    card_signature_intro(str(CARD_DIR / "08_handoff_cn.png"), day_n=1, is_english=False)

    # 9. Tomorrow outro
    card_bilingual(str(CARD_DIR / "09_tomorrow.png"),
                   "Day 1\nstarts tomorrow.",
                   "第 1 天\n从明天开始。",
                   en_size=92, cn_size=78,
                   en_color=FG, cn_color=FG)

    print(f"  rendered {len(list(CARD_DIR.glob('*.png')))} cards → {CARD_DIR}")


def render_tts():
    scripts_dir = ROOT / "scripts"
    audio_dir = ROOT / "assets/audio"

    en_text = (
        "My name is Bonny. I've been in crypto since 2017. "
        "Honestly, a thousand dollars isn't much for me. "
        "Back when DeFi fees went crazy, I paid hundreds in gas for a single transaction. "
        "I'm putting a thousand down for this experiment because it's the exact amount an ordinary person can afford to risk. "
        "I want to test one thing — "
        "can someone who can't code use AI to build a trading bot that actually makes money? "
        "If yes, then anyone with a thousand dollars and no time to watch charts can plug it in, "
        "and let AI earn them their own pocket money. "
        "Seven days ago I asked AI: can you write me one? "
        "Seven days later, it had. "
        "Now I've given a thousand real dollars to it. Every loss, every win, every bug — public. "
        "This isn't a product. It's an experiment. "
        "If I can, you can. "
        "That's AI trades my thousand dollars. Day 1 starts tomorrow."
    )
    cn_text = (
        "我叫 Bonny，一个女生，在币圈 9 年了。"
        "说实话，1000 美元对我不算大钱。"
        "DeFi gas 费最疯的那段时间，一笔交易我就付过几百美金的手续费。"
        "但我拿这 1000 美元出来做这个实验，是因为它刚好是一个普通人能掏得起的金额。"
        "我想验证一件事 —— "
        "一个不会写代码的人，能不能靠 AI 写出一个真的能赚钱的交易机器人？"
        "如果能，那以后每一个手上有 1000 美元、又没时间盯盘的普通人，"
        "都可以直接拿去用 —— 让 AI 替他们自动赚一点自己的零花钱。"
        "7 天前我问 AI：你能不能帮我写一个？"
        "7 天后，它写出来了。"
        "现在我把 1000 美元真的交给了它。每一笔亏损、每一笔盈利、每一个 bug，我都公开。"
        "这不是一个产品。这是一个实验。"
        "如果我能，你也能。"
        "这就是 AI 帮我操盘。第一天，从明天开始。"
    )

    (scripts_dir / "ep_0_vo_en.txt").write_text(en_text)
    (scripts_dir / "ep_0_vo_cn.txt").write_text(cn_text)

    subprocess.run([
        "edge-tts", "--voice", "en-US-AvaMultilingualNeural", "--rate=-10%",
        "--file", str(scripts_dir / "ep_0_vo_en.txt"),
        "--write-media", str(audio_dir / "ep_0_vo_en.mp3"),
    ], check=True, env=_env())
    subprocess.run([
        "edge-tts", "--voice", "zh-CN-XiaoxiaoNeural", "--rate=-6%",
        "--file", str(scripts_dir / "ep_0_vo_cn.txt"),
        "--write-media", str(audio_dir / "ep_0_vo_cn.mp3"),
    ], check=True, env=_env())

    for lang in ("en", "cn"):
        subprocess.run([
            "ffmpeg", "-y", "-i", str(audio_dir / f"ep_0_vo_{lang}.mp3"),
            "-ar", "48000", "-ac", "2",
            str(audio_dir / f"ep_0_vo_{lang}.wav"),
        ], check=True, capture_output=True)
    print(f"  rendered TTS")


def build_concat_file(lang):
    card_dir = ROOT / "assets/cards/ep_0"
    declaration_card = "06_declaration.png" if lang == "en" else "06_declaration_cn.png"
    beats = [
        (6, "01_about.png"),
        (8, "02_defi_gas.png"),
        (8, "03_stake.png"),
        (10, "04_question.png"),
        (6, "05_7days.png"),
        (9, declaration_card),
        (7, "07_transparent.png"),
        (5, f"08_handoff_{lang}.png"),
        (6, "09_tomorrow.png"),
    ]
    concat_path = ROOT / f"scripts/ep_0_concat_{lang}.txt"
    lines = []
    for dur, fn in beats:
        lines.append(f"file '{card_dir / fn}'")
        lines.append(f"duration {dur}")
    lines.append(f"file '{card_dir / beats[-1][1]}'")
    concat_path.write_text("\n".join(lines) + "\n")
    return concat_path


def render_mp4(lang):
    out = ROOT / f"out/ep_0_{lang}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    concat_path = build_concat_file(lang)
    audio = ROOT / f"assets/audio/ep_0_vo_{lang}.wav"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_path),
        "-i", str(audio),
        "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v", "-map", "1:a",
        str(out),
    ], check=True, capture_output=True)
    print(f"  rendered {out.name}")


def _env():
    import os
    env = os.environ.copy()
    env["PATH"] = f"{Path.home()/'.local/bin'}:{Path.home()/'Library/Python/3.9/bin'}:{env.get('PATH','')}"
    return env


if __name__ == "__main__":
    print("→ cards")
    render_cards()
    print("→ TTS")
    render_tts()
    print("→ MP4 (EN)")
    render_mp4("en")
    print("→ MP4 (CN)")
    render_mp4("cn")
    print("\n✅ Episode 0 rendered")
