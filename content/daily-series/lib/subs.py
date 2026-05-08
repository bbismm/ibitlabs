"""Generate ASS subtitle files with kinetic animation from edge-tts VTT output.

Per-line animation: fade-in + slight upward slide + mini-pop scale. Subtle, restrained
for Polanyi (no obnoxious motion).
"""
import re
from pathlib import Path


ASS_HEADER = """[Script Info]
Title: {title}
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: {style_name}, {font}, {size}, &H00EDE5D5, &H00F5EDD5, &H00141210, &H80000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 4, 2, 2, 100, 100, 280, 1
Style: Accent, {font}, {size}, &H002A4ADB, &H00F5EDD5, &H00141210, &H80000000, 1, 0, 0, 0, 100, 100, 0, 0, 1, 4, 2, 2, 100, 100, 280, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# ASS colour format: &H<BB><GG><RR> (reverse hex)
# EDE5D5 (cream) → &H00EDE5D5 actually needs reversal → &H00D5E5ED? Let me just let FG be cream off-white.
# Actually ASS uses BGR order, so for cream #EDE5D5 → 0xD5, 0xE5, 0xED → &H00D5E5ED
# I'll rebuild with correct BGR below.


def _ts(seconds: float) -> str:
    """ASS timestamp: H:MM:SS.CS (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def parse_vtt(vtt_path: Path):
    """Parse edge-tts VTT/SRT output into (start_s, end_s, text) tuples."""
    text = Path(vtt_path).read_text()
    events = []
    for block in text.split("\n\n"):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        # idx line, timing line, text lines
        if lines[0].startswith("WEBVTT"):
            continue
        # find timing line
        timing_line = None
        for i, l in enumerate(lines):
            if "-->" in l:
                timing_line = l
                text_lines = lines[i + 1 :]
                break
        if timing_line is None:
            continue
        ts = timing_line.replace(",", ".")
        m = re.match(r"(\d+):(\d+):([\d.]+)\s*-->\s*(\d+):(\d+):([\d.]+)", ts)
        if not m:
            continue
        sh, sm, ss, eh, em, es = m.groups()
        start = int(sh) * 3600 + int(sm) * 60 + float(ss)
        end = int(eh) * 3600 + int(em) * 60 + float(es)
        content = " ".join(text_lines).strip()
        if content:
            events.append((start, end, content))
    return events


def _split_long_line(text: str, lang: str, max_cn=20, max_en=50):
    """Recursively split ONCE at best midpoint marker if too long; else return as-is."""
    text = text.strip()
    if not text:
        return []
    if lang == "cn":
        if len(text) <= max_cn:
            return [text]
    else:
        if len(text.split()) <= max_en:
            return [text]

    markers_cn = ["。", "！", "？", "——", "；", "：", "，", "、"]
    markers_en = [". ", "! ", "? ", " — ", "; ", ": ", ", "]
    markers = markers_cn if lang == "cn" else markers_en

    mid = len(text) // 2
    best_pos = -1
    best_dist = float("inf")
    for m in markers:
        idx = text.find(m)
        while idx > 0:
            split_after = idx + len(m)
            # avoid splitting too close to either edge
            if 5 <= split_after <= len(text) - 5:
                dist = abs(split_after - mid)
                if dist < best_dist:
                    best_dist = dist
                    best_pos = split_after
            idx = text.find(m, idx + 1)
        if best_pos >= 0 and best_dist < len(text) // 4:
            break  # found a good split with this marker tier

    if best_pos <= 0:
        # last-resort: split at midpoint word/char
        if lang == "cn":
            best_pos = mid
        else:
            words = text.split()
            best_pos = len(" ".join(words[: len(words) // 2])) + 1

    left = text[:best_pos].strip().rstrip(",.;:，。；：、")
    right = text[best_pos:].strip().lstrip(",.;:，。；：、 ")
    out = []
    if left:
        out.extend(_split_long_line(left, lang, max_cn, max_en))
    if right:
        out.extend(_split_long_line(right, lang, max_cn, max_en))
    return out


def _break_midpoint(text: str, lang: str):
    """If text is still a bit long, insert \\N at nearest comma past midpoint."""
    limit = 14 if lang == "cn" else 32
    if lang == "cn":
        if len(text) <= limit:
            return text
        mid = len(text) // 2
        best = -1
        for i, ch in enumerate(text):
            if ch in "，、——；：" and abs(i - mid) < abs(best - mid) if best >= 0 else True:
                if abs(i - mid) < len(text) // 3:
                    best = i
        if best >= 0:
            return text[: best + 1].rstrip() + r"\N" + text[best + 1 :].lstrip()
    else:
        words = text.split()
        if len(words) <= limit:
            return text
        mid = len(words) // 2
        for i in range(max(0, mid - 3), min(len(words) - 1, mid + 3)):
            if words[i].endswith(("." , "," , "—" , ";" , ":")):
                return " ".join(words[: i + 1]) + r"\N" + " ".join(words[i + 1 :])
        # fallback: break at middle word
        return " ".join(words[:mid]) + r"\N" + " ".join(words[mid:])
    return text


def build_ass(events, out_path: Path, lang="cn", title="subs", offset_s=0.0):
    """Build kinetic ASS subtitle file.

    - Soft fade-in/fade-out (250ms)
    - Tiny upward drift (20px) during fade-in — gentle, not popping
    - Auto-split long lines proportionally so each chunk fits on screen
    """
    font = "Hiragino Sans GB W6" if lang == "cn" else "Helvetica"
    size = 56 if lang == "cn" else 54
    style_name = "Default"

    header = ASS_HEADER.format(
        title=title, font=font, size=size, style_name=style_name,
    ).replace(
        # Fix ASS BGR colour for cream
        "&H00EDE5D5,", "&H00D5E5ED,"
    ).replace(
        "&H00F5EDD5,", "&H00D5EDF5,"
    ).replace(
        # Accent terracotta #D9724A → BGR = 4A72D9
        "&H002A4ADB,", "&H004A72D9,"
    ).replace(
        "&H00141210,", "&H00101214,"
    )

    body_lines = []
    for start, end, text in events:
        text_clean = text.replace("\\", " ").strip()
        if not text_clean:
            continue

        # Pre-split very long lines — libass wraps with WrapStyle 0 but absolute \pos
        # bypasses margin-based wrapping; chunking keeps each event short.
        chunks = _split_long_line(text_clean, lang)

        total_dur = max(0.6, (end - start))
        per_chunk = total_dur / len(chunks)

        for i, chunk in enumerate(chunks):
            s = max(0.0, start + offset_s + i * per_chunk)
            e = max(s + 0.3, start + offset_s + (i + 1) * per_chunk)

            # Animation: fade only. Rely on Alignment=2 (bottom-center) +
            # MarginL/R/V from style for positioning. No \pos/\move so wrap works.
            effect = r"{\fad(200,200)}"
            line = f"Dialogue: 0,{_ts(s)},{_ts(e)},{style_name},,0,0,0,,{effect}{chunk}"
            body_lines.append(line)

    Path(out_path).write_text(header + "\n".join(body_lines) + "\n")
    return out_path


if __name__ == "__main__":
    # Smoke test
    import sys
    if len(sys.argv) < 3:
        print("usage: subs.py <input.vtt> <output.ass> [lang cn|en]")
        sys.exit(1)
    lang = sys.argv[3] if len(sys.argv) > 3 else "cn"
    events = parse_vtt(Path(sys.argv[1]))
    build_ass(events, Path(sys.argv[2]), lang=lang, title="Day subs")
    print(f"  {len(events)} subtitle events → {sys.argv[2]}")
