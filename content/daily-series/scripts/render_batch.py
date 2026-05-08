"""Batch-render Day 2-15 using the same KOL pipeline as Day 1.

Reads episode data from lib/episode_specs.py. For each episode:
  1. Renders cards via the type-handler dispatch
  2. Generates TTS (edge-tts) + VTT timing
  3. Builds ASS subtitles
  4. Assembles MP4 (xfade transitions + Ken Burns zoompan + BGM mix + burned subs)

Output: out/day_NN_{en,cn}.mp4
"""
import os, sys, subprocess
from pathlib import Path

ROOT = Path.home() / "ibitlabs/content/daily-series"
sys.path.insert(0, str(ROOT / "lib"))
from cards_warm import (
    card_signature_intro, card_topic_reveal, card_bilingual, card_outro,
    card_stat, card_single,
    FG, MUTED, TERRACOTTA, SAGE, CREAM_BG,
)
from subs import parse_vtt, build_ass
from episode_specs import EPISODES

FFMPEG_FULL = "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
FFPROBE = "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
XFADE_DUR = 0.35

AUDIO_DIR = ROOT / "assets/audio"
SUBS_DIR = ROOT / "assets/subs"
OUT = ROOT / "out"
MUSIC_DIR = ROOT / "assets/music"
SCRIPTS = ROOT / "scripts"

for d in (AUDIO_DIR, SUBS_DIR, OUT):
    d.mkdir(parents=True, exist_ok=True)


def _env():
    env = os.environ.copy()
    env["PATH"] = f"{Path.home()/'.local/bin'}:{Path.home()/'Library/Python/3.9/bin'}:{env.get('PATH','')}"
    return env


# Transition assignment policy (which xfade between which cards, by type sequence)
DEFAULT_TRANSITIONS = {
    "hook": "slideleft",       # after hook
    "id": "fade",              # between identity cards
    "sig": "circlecrop",       # after signature
    "stat": "fade",
    "bilingual": "fade",
    "outro": "fadewhite",      # after outro
}


def render_episode_cards(day_n, spec, card_dir):
    """Render all cards for one episode based on spec['cards']."""
    card_dir.mkdir(parents=True, exist_ok=True)
    topic_cn = spec["topic_cn"]
    topic_en = spec["topic_en"]
    rendered = []  # list of (filename, lang_variants_dict) tuples

    for i, card in enumerate(spec["cards"]):
        t = card["type"]
        prefix = f"{i + 1:02d}"

        if t == "hook":
            fn = f"{prefix}_hook.png"
            card_bilingual(str(card_dir / fn),
                           card["en"], card["cn"],
                           en_size=card.get("en_size", 54),
                           cn_size=card.get("cn_size", 52),
                           en_color=FG, cn_color=TERRACOTTA)
            rendered.append((fn, None))
        elif t == "id":
            fn = f"{prefix}_id.png"
            card_bilingual(str(card_dir / fn),
                           card["en"], card["cn"],
                           en_size=card.get("en_size", 108),
                           cn_size=card.get("cn_size", 96),
                           en_color=FG)
            rendered.append((fn, None))
        elif t == "sig":
            # signature card has en/cn variants
            card_signature_intro(str(card_dir / f"{prefix}_sig_en.png"), day_n=day_n, is_english=True)
            card_signature_intro(str(card_dir / f"{prefix}_sig_cn.png"), day_n=day_n, is_english=False)
            rendered.append((f"{prefix}_sig_{{lang}}.png", {"en": f"{prefix}_sig_en.png",
                                                            "cn": f"{prefix}_sig_cn.png"}))
        elif t == "stat":
            fn = f"{prefix}_stat.png"
            card_stat(str(card_dir / fn),
                      value=card["value"],
                      label_en=card["en"],
                      label_cn=card["cn"],
                      value_color=card.get("value_color", TERRACOTTA))
            rendered.append((fn, None))
        elif t == "bilingual":
            fn = f"{prefix}_bi.png"
            card_bilingual(str(card_dir / fn),
                           card["en"], card["cn"],
                           en_size=card.get("en_size", 70),
                           cn_size=card.get("cn_size", 58),
                           en_color=card.get("en_color", FG),
                           cn_color=card.get("cn_color", MUTED))
            rendered.append((fn, None))
        elif t == "outro":
            card_outro(str(card_dir / f"{prefix}_outro_en.png"),
                       lesson_en=card["en"], lesson_cn=card["cn"],
                       day_n=day_n, is_english=True)
            card_outro(str(card_dir / f"{prefix}_outro_cn.png"),
                       lesson_en=card["en"], lesson_cn=card["cn"],
                       day_n=day_n, is_english=False)
            rendered.append((f"{prefix}_outro_{{lang}}.png", {"en": f"{prefix}_outro_en.png",
                                                              "cn": f"{prefix}_outro_cn.png"}))
        elif t == "cta":
            card_single(str(card_dir / f"{prefix}_cta_en.png"),
                        text=card["en"], size=card.get("en_size", 72),
                        color=TERRACOTTA, font_type="en", bg=CREAM_BG, accent=True)
            card_single(str(card_dir / f"{prefix}_cta_cn.png"),
                        text=card["cn"], size=card.get("cn_size", 70),
                        color=TERRACOTTA, font_type="cn", bg=CREAM_BG, accent=True)
            rendered.append((f"{prefix}_cta_{{lang}}.png", {"en": f"{prefix}_cta_en.png",
                                                            "cn": f"{prefix}_cta_cn.png"}))
        else:
            raise ValueError(f"unknown card type: {t}")

    return rendered


def render_episode_tts(day_n, spec):
    """Generate TTS mp3 + wav + VTT for both languages."""
    en_text = spec["vo_en"]
    cn_text = spec["vo_cn"]

    (SCRIPTS / f"day_{day_n:02d}_vo_en.txt").write_text(en_text)
    (SCRIPTS / f"day_{day_n:02d}_vo_cn.txt").write_text(cn_text)

    for lang, voice, rate, text_path in [
        ("en", "en-US-AvaMultilingualNeural", "-10%", SCRIPTS / f"day_{day_n:02d}_vo_en.txt"),
        ("cn", "zh-CN-XiaoxiaoNeural", "-6%", SCRIPTS / f"day_{day_n:02d}_vo_cn.txt"),
    ]:
        mp3 = AUDIO_DIR / f"day_{day_n:02d}_vo_{lang}.mp3"
        vtt = SUBS_DIR / f"day_{day_n:02d}_{lang}.vtt"
        subprocess.run([
            "edge-tts", "--voice", voice, f"--rate={rate}",
            "--file", str(text_path),
            "--write-media", str(mp3),
            "--write-subtitles", str(vtt),
        ], check=True, env=_env())
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp3),
            "-ar", "48000", "-ac", "2",
            str(AUDIO_DIR / f"day_{day_n:02d}_vo_{lang}.wav"),
        ], check=True, capture_output=True)


def render_episode_subs(day_n):
    for lang in ("en", "cn"):
        events = parse_vtt(SUBS_DIR / f"day_{day_n:02d}_{lang}.vtt")
        build_ass(events, SUBS_DIR / f"day_{day_n:02d}_{lang}.ass",
                  lang=lang, title=f"Day {day_n} {lang.upper()}")


def get_audio_duration(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def render_mp4(day_n, lang, spec, rendered_cards, card_dir):
    """Fancy render: xfade + Ken Burns + subtitles + BGM."""
    out = OUT / f"day_{day_n:02d}_{lang}.mp4"
    vo = AUDIO_DIR / f"day_{day_n:02d}_vo_{lang}.wav"
    subs = SUBS_DIR / f"day_{day_n:02d}_{lang}.ass"
    bgm = MUSIC_DIR / f"{spec['bgm']}.mp3"

    vo_duration = get_audio_duration(vo) + 1.2

    # Assign durations & transitions per card
    cards_list = spec["cards"]
    # Even baseline weight, overridden per-card optional
    default_weights = {
        "hook": 4.0, "id": 2.0, "sig": 3.0, "stat": 3.5,
        "bilingual": 5.0, "outro": 6.5, "cta": 4.5,
    }
    beat_durations = []
    beat_files = []
    beat_trans = []
    for i, card in enumerate(cards_list):
        fn_template, variants = rendered_cards[i]
        if variants:
            fn = variants[lang]
        else:
            fn = fn_template
        w = card.get("weight", default_weights.get(card["type"], 3.0))
        trans = DEFAULT_TRANSITIONS.get(card["type"], "fade")
        beat_durations.append(w)
        beat_files.append(fn)
        beat_trans.append(trans)

    total_weight = sum(beat_durations)
    scale = vo_duration / total_weight
    beat_durations = [d * scale for d in beat_durations]

    # Inputs: each card loops for (dur + xfade overlap)
    inputs = []
    for dur, fn in zip(beat_durations, beat_files):
        t = dur + XFADE_DUR + 0.1
        inputs.extend(["-loop", "1", "-t", f"{t:.3f}", "-i", str(card_dir / fn)])
    inputs.extend(["-i", str(vo), "-stream_loop", "-1", "-i", str(bgm)])
    vo_idx = len(beat_durations)
    bgm_idx = len(beat_durations) + 1

    per_card = []
    for i, dur in enumerate(beat_durations):
        frames = max(2, int((dur + XFADE_DUR) * 30))
        per_card.append(
            f"[{i}:v]scale=1080:1920,setsar=1,"
            f"zoompan=z='min(zoom+0.0008,1.04)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
            f"format=yuv420p[c{i}]"
        )

    xfade_chain = []
    cumulative = beat_durations[0]
    prev = "c0"
    for i in range(1, len(beat_durations)):
        trans = beat_trans[i - 1] or "fade"
        offset = cumulative - XFADE_DUR
        tag = f"x{i}"
        xfade_chain.append(
            f"[{prev}][c{i}]xfade=transition={trans}:duration={XFADE_DUR}:offset={offset:.3f}[{tag}]"
        )
        prev = tag
        cumulative += beat_durations[i]

    subs_str = str(subs).replace(":", "\\:")
    final = f"[{prev}]subtitles={subs_str}[vout]"
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
        print(f"  !!! Day {day_n} {lang} ffmpeg failed")
        print(r.stderr[-2000:])
        return False
    return True


def render_day(day_n):
    spec = EPISODES[day_n]
    card_dir = ROOT / f"assets/cards/day_{day_n:02d}"

    print(f"\n=== Day {day_n} · {spec['topic_cn']} ===")
    print("  → cards")
    rendered = render_episode_cards(day_n, spec, card_dir)
    print("  → TTS + VTT")
    render_episode_tts(day_n, spec)
    print("  → ASS subs")
    render_episode_subs(day_n)
    for lang in ("en", "cn"):
        print(f"  → MP4 ({lang})")
        ok = render_mp4(day_n, lang, spec, rendered, card_dir)
        if not ok:
            return False
    return True


if __name__ == "__main__":
    days = sys.argv[1:] or [str(d) for d in sorted(EPISODES.keys())]
    for d in days:
        ok = render_day(int(d))
        if not ok:
            print(f"\n❌ stopped at Day {d}")
            break
    print("\n✅ batch complete")
