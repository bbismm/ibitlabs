"""Render Day 1 v3 — full pipeline: cards + narrative VO + BGM + kinetic subtitles.

Output: out/day_01_{en,cn}.mp4 (overwrites v2)
"""
import os, sys, subprocess
from pathlib import Path

ROOT = Path.home() / "ibitlabs/content/daily-series"
sys.path.insert(0, str(ROOT / "lib"))
from cards_warm import (
    card_signature_intro, card_topic_reveal, card_bilingual, card_outro,
    card_stat, card_single,
    FG, MUTED, TERRACOTTA, SAGE, CREAM_BG, INK,
)
from subs import parse_vtt, build_ass

DAY = 1
TOPIC_EN = "I stared at that button for a while"
TOPIC_CN = "我盯着那个按钮看了很久"
CARD_DIR = ROOT / "assets/cards/day_01"
AUDIO_DIR = ROOT / "assets/audio"
SUBS_DIR = ROOT / "assets/subs"
BGM = ROOT / "assets/music/calm_reflection.mp3"   # Day 1 mood = calm
SCRIPTS = ROOT / "scripts"
OUT = ROOT / "out"

for d in (CARD_DIR, AUDIO_DIR, SUBS_DIR, OUT):
    d.mkdir(parents=True, exist_ok=True)


def _env():
    env = os.environ.copy()
    env["PATH"] = f"{Path.home()/'.local/bin'}:{Path.home()/'Library/Python/3.9/bin'}:{env.get('PATH','')}"
    return env


def render_cards():
    # 1. HOOK — 0 trades / 0 profit with punchline
    card_bilingual(str(CARD_DIR / "k01_hook.png"),
                   "Day 1 ended.\n0 trades. $0 profit.\n\nBut I learned more than\n7 days of paper testing.",
                   "第 1 天结束。\n0 笔交易。0 利润。\n\n但我学到的 ——\n比 7 天纸上模拟还多。",
                   en_size=54, cn_size=52,
                   en_color=FG, cn_color=TERRACOTTA)

    # 2-4. Identity stack (3 rapid-fire bullets)
    card_bilingual(str(CARD_DIR / "k02_id1.png"),
                   "I can't code.", "我不会写代码。",
                   en_size=120, cn_size=96, en_color=FG)
    card_bilingual(str(CARD_DIR / "k03_id2.png"),
                   "9 years\nin crypto.", "币圈 9 年。",
                   en_size=104, cn_size=96, en_color=FG)
    card_bilingual(str(CARD_DIR / "k04_id3.png"),
                   "7 days ago, AI built me\na trading bot.",
                   "7 天前，AI 替我写了\n一个交易机器人。",
                   en_size=60, cn_size=54)

    # 5. Mission
    card_bilingual(str(CARD_DIR / "k05_mission.png"),
                   "$1,000 stake.\nIf it works —\nany ordinary person can use it.",
                   "1000 美金做实验。\n如果成了 ——\n任何普通人都能用。",
                   en_size=58, cn_size=50)

    # 6. Signature "AI 帮我操盘 · 第 1 天"
    card_signature_intro(str(CARD_DIR / "k06_sig_en.png"), day_n=DAY, is_english=True)
    card_signature_intro(str(CARD_DIR / "k06_sig_cn.png"), day_n=DAY, is_english=False)

    # 7. paper → live code moment
    card_bilingual(str(CARD_DIR / "k07_flag.png"),
                   "--paper\n      →\n--live",
                   "一个字的差别",
                   en_size=96, cn_size=54, en_color=TERRACOTTA)

    # 8. 20 min staring
    card_stat(str(CARD_DIR / "k08_20min.png"),
              value="20 min", label_en="staring at the Enter key",
              label_cn="盯着 Enter 键看",
              value_color=TERRACOTTA)

    # 9. The thought (quote)
    card_bilingual(str(CARD_DIR / "k09_thought.png"),
                   '"If this loses\neverything tonight,\nhow do I tell anyone?"',
                   '"万一今晚全亏光，\n我怎么跟人交代？"',
                   en_size=62, cn_size=58, en_color=SAGE, cn_color=SAGE)

    # 10. I pressed. Nothing.
    card_bilingual(str(CARD_DIR / "k10_pressed.png"),
                   "I pressed.\nNothing happened.",
                   "我按了。\n什么都没发生。",
                   en_size=96, cn_size=82, en_color=FG)

    # 11. 1h / 2h no trades
    card_bilingual(str(CARD_DIR / "k11_waited.png"),
                   "1 hour · 0 trades\n2 hours · still 0",
                   "1 小时 · 0 笔\n2 小时 · 还是 0",
                   en_size=80, cn_size=66, en_color=MUTED, cn_color=MUTED)

    # 12. Hour 3 · dishes
    card_bilingual(str(CARD_DIR / "k12_dishes.png"),
                   "Hour 3 ·\nI went to wash dishes.",
                   "第 3 小时 ·\n我去洗碗了。",
                   en_size=72, cn_size=64)

    # 13. Something shifted
    card_bilingual(str(CARD_DIR / "k13_shifted.png"),
                   "Something had shifted.\nI couldn't have said what.",
                   "有什么已经换了位置。\n我说不清是什么。",
                   en_size=62, cn_size=54)

    # 14. Outro — golden line
    card_outro(str(CARD_DIR / "k14_outro_en.png"),
               lesson_en="Zero trades on Day 1.\nAnd most of what I learned all week\ncame from those three hours.",
               lesson_cn="第 1 天 0 笔交易。\n可我这一周学到最重要的事，\n就藏在那 3 小时里。",
               day_n=DAY, is_english=True)
    card_outro(str(CARD_DIR / "k14_outro_cn.png"),
               lesson_en="Zero trades on Day 1.\nAnd most of what I learned all week\ncame from those three hours.",
               lesson_cn="第 1 天 0 笔交易。\n可我这一周学到最重要的事，\n就藏在那 3 小时里。",
               day_n=DAY, is_english=False)

    # 15. CTA
    card_single(str(CARD_DIR / "k15_cta_en.png"),
                text="Day 2 tomorrow.\nIt actually traded →\n\nFollow along.",
                size=74, color=TERRACOTTA, font_type="en", bg=CREAM_BG, accent=True)
    card_single(str(CARD_DIR / "k15_cta_cn.png"),
                text="Day 2 明天 ·\n它真的下单了 →\n\n关注一下，不走丢。",
                size=72, color=TERRACOTTA, font_type="cn", bg=CREAM_BG, accent=True)

    print(f"  rendered cards")


def render_tts():
    """Generate MP3 + VTT for both languages."""
    en_text = (SCRIPTS / "day_01_v2_vo_en.txt").read_text()
    cn_text = (SCRIPTS / "day_01_v2_vo_cn.txt").read_text()

    for lang, voice, rate, text in [
        ("en", "en-US-AvaMultilingualNeural", "-10%", en_text),
        ("cn", "zh-CN-XiaoxiaoNeural", "-6%", cn_text),
    ]:
        txt_path = SCRIPTS / f"day_01_v3_vo_{lang}.txt"
        txt_path.write_text(text)
        subprocess.run([
            "edge-tts", "--voice", voice, f"--rate={rate}",
            "--file", str(txt_path),
            "--write-media", str(AUDIO_DIR / f"day_01_v3_vo_{lang}.mp3"),
            "--write-subtitles", str(SUBS_DIR / f"day_01_v3_{lang}.vtt"),
        ], check=True, env=_env())
        subprocess.run([
            "ffmpeg", "-y", "-i", str(AUDIO_DIR / f"day_01_v3_vo_{lang}.mp3"),
            "-ar", "48000", "-ac", "2",
            str(AUDIO_DIR / f"day_01_v3_vo_{lang}.wav"),
        ], check=True, capture_output=True)
    print(f"  rendered TTS + VTT")


def render_subs():
    for lang in ("en", "cn"):
        events = parse_vtt(SUBS_DIR / f"day_01_v3_{lang}.vtt")
        build_ass(events, SUBS_DIR / f"day_01_v3_{lang}.ass", lang=lang, title=f"Day 1 {lang.upper()}")
    print(f"  rendered ASS subtitles")


def get_audio_duration(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def beats_for(lang):
    """List of (duration, filename, transition_to_next). Transitions use xfade effects."""
    return [
        (4.0, "k01_hook.png",        "slideleft"),     # HOOK — slam in
        (2.0, "k02_id1.png",         "fade"),          # I can't code
        (2.0, "k03_id2.png",         "fade"),          # 9 years
        (3.0, "k04_id3.png",         "fade"),          # 7 days
        (4.5, "k05_mission.png",     "fadewhite"),     # mission (bright turn)
        (3.0, f"k06_sig_{lang}.png", "circlecrop"),    # signature reveal
        (4.0, "k07_flag.png",        "fade"),          # paper → live
        (3.5, "k08_20min.png",       "fade"),          # 20 min
        (7.0, "k09_thought.png",     "circleopen"),    # thought (emotional)
        (3.5, "k10_pressed.png",     "fadeblack"),     # nothing happened
        (4.0, "k11_waited.png",      "fade"),          # hours
        (4.0, "k12_dishes.png",      "fade"),          # dishes
        (5.0, "k13_shifted.png",     "fadewhite"),     # shift reveal
        (6.5, f"k14_outro_{lang}.png", "fade"),        # outro → cta
        (4.5, f"k15_cta_{lang}.png", None),            # CTA (last)
    ]


def build_concat_file(lang, total_audio_s):
    """Fallback concat — only used if xfade path fails."""
    beats = beats_for(lang)
    total_weight = sum(b[0] for b in beats)
    scaled = [(total_audio_s * dur / total_weight, fn) for dur, fn, _ in beats]

    concat_path = SCRIPTS / f"day_01_v3_concat_{lang}.txt"
    lines = []
    for dur, fn in scaled:
        lines.append(f"file '{CARD_DIR / fn}'")
        lines.append(f"duration {dur:.3f}")
    lines.append(f"file '{CARD_DIR / scaled[-1][1]}'")
    concat_path.write_text("\n".join(lines) + "\n")
    return concat_path


FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
XFADE_DUR = 0.35  # seconds for each transition


def render_mp4(lang):
    """Fancy render: xfade transitions + Ken Burns zoompan + subtitles + BGM."""
    out = OUT / f"day_01_{lang}.mp4"
    vo = AUDIO_DIR / f"day_01_v3_vo_{lang}.wav"
    subs = SUBS_DIR / f"day_01_v3_{lang}.ass"

    vo_duration = get_audio_duration(vo) + 1.2
    beats = beats_for(lang)
    # Scale beat durations so they cleanly sum up to vo_duration
    orig_total = sum(b[0] for b in beats)
    scale = vo_duration / orig_total
    beats = [(dur * scale, fn, trans) for dur, fn, trans in beats]

    # Build inputs — each card loops for (its duration + xfade overlap)
    inputs = []
    for i, (dur, fn, trans) in enumerate(beats):
        # Each card needs to be at least dur + XFADE_DUR long so xfade has overlap
        t = dur + XFADE_DUR + 0.1
        inputs.extend(["-loop", "1", "-t", f"{t:.3f}", "-i", str(CARD_DIR / fn)])
    # VO + BGM
    inputs.extend(["-i", str(vo)])
    inputs.extend(["-stream_loop", "-1", "-i", str(BGM)])
    vo_idx = len(beats)
    bgm_idx = len(beats) + 1

    # Per-card processing: scale + subtle Ken Burns breathing (slow zoom up to 1.04)
    per_card = []
    for i, (dur, _, _) in enumerate(beats):
        frames = max(2, int((dur + XFADE_DUR) * 30))
        # zoompan across entire frame count, gentle
        per_card.append(
            f"[{i}:v]scale=1080:1920,setsar=1,"
            f"zoompan=z='min(zoom+0.0008,1.04)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
            f"format=yuv420p[c{i}]"
        )

    # Chain xfade transitions
    xfade_chain = []
    cumulative = beats[0][0]
    prev = "c0"
    for i in range(1, len(beats)):
        trans = beats[i - 1][2] or "fade"
        offset = cumulative - XFADE_DUR
        tag = f"x{i}"
        xfade_chain.append(
            f"[{prev}][c{i}]xfade=transition={trans}:duration={XFADE_DUR}:"
            f"offset={offset:.3f}[{tag}]"
        )
        prev = tag
        cumulative += beats[i][0]

    # Apply subtitles last
    subs_str = str(subs).replace(":", "\\:")
    final = f"[{prev}]subtitles={subs_str}[vout]"

    # Audio mix
    audio_mix = (
        f"[{vo_idx}:a]volume=1.0[vo_audio];"
        f"[{bgm_idx}:a]volume=0.12,"
        f"afade=t=in:st=0:d=1.5,"
        f"afade=t=out:st={vo_duration-1.5:.2f}:d=1.5[bgm];"
        f"[vo_audio][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )

    filter_complex = ";".join(per_card + xfade_chain + [final, audio_mix])

    cmd = [FFMPEG_FULL, "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{vo_duration:.2f}",
        "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  !!! ffmpeg failed for {lang}")
        print(r.stderr[-3000:])
        raise SystemExit(1)
    print(f"  rendered {out.name}")


if __name__ == "__main__":
    print("→ cards")
    render_cards()
    print("→ TTS + VTT")
    render_tts()
    print("→ ASS subs")
    render_subs()
    print("→ MP4 with subs + BGM (EN)")
    render_mp4("en")
    print("→ MP4 with subs + BGM (CN)")
    render_mp4("cn")
    print("\n✅ Day 1 v3 rendered (cards + BGM + kinetic subs)")
