"""Warm-palette card rendering for the daily-series.

Brand signature:
  CN: AI 帮我操盘第 [N] 天 · [主题]
  EN: Day [N]: AI trades my $1,000 · [topic]

Palette:
  - Dark warm bg      #16130F (not pure black; slight warm undertone)
  - Cream FG          #EDE5D5
  - Muted sage        #7FA686
  - Accent terracotta #D9724A
  - Accent gold       #D4A24C
  - Cream bg (high)   #F2E9DA (for highlight/cream cards)
  - Ink dark (on cream) #1B2520
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

W, H = 1080, 1920

# Dark-warm default palette
BG = (22, 19, 15)               # #16130F
FG = (237, 229, 213)            # #EDE5D5
MUTED = (138, 128, 115)         # #8A8073
SAGE = (127, 166, 134)          # #7FA686
TERRACOTTA = (217, 114, 74)     # #D9724A
GOLD = (212, 162, 76)           # #D4A24C

# Cream-bg alt palette for "highlight" cards
CREAM_BG = (242, 233, 218)      # #F2E9DA
INK = (27, 37, 32)              # #1B2520
INK_MUTED = (107, 112, 103)     # #6B7067

FONT_EN_BOLD = "/System/Library/Fonts/Helvetica.ttc"
FONT_CN = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_MONO = "/System/Library/Fonts/Menlo.ttc"


def load_font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


def wrap_en(draw, text, font, max_w):
    out = []
    for seg in text.split("\n"):
        words = seg.split(" ")
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_w and cur:
                out.append(cur)
                cur = w
            else:
                cur = test
        if cur:
            out.append(cur)
    return out


def wrap_cn(draw, text, font, max_w):
    out = []
    for seg in text.split("\n"):
        cur = ""
        for ch in seg:
            test = cur + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_w and cur:
                out.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            out.append(cur)
    return out


def footer_tag(draw, img, palette_fg=MUTED):
    """Small bonnybb · ibitlabs footer tag — brand signature on every card."""
    f_tag = load_font(FONT_EN_BOLD, 30, index=1)
    txt = "bonnybb · ibitlabs.com"
    bbox = draw.textbbox((0, 0), txt, font=f_tag)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H - 90), txt, font=f_tag, fill=palette_fg)


def card_signature_intro(path, day_n, is_english=False):
    """First card — brand + day ONLY. Topic comes on the next card.

    VO matching this card: "AI 帮我操盘，第一天。" / "AI trades my one thousand dollars. Day one."
    """
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    f_series_en = load_font(FONT_EN_BOLD, 88, index=1)
    f_series_cn = load_font(FONT_CN, 96, index=1)
    f_day_num = load_font(FONT_EN_BOLD, 240, index=1)
    f_day_cn = load_font(FONT_CN, 200, index=1)

    if is_english:
        series_text = "AI trades my $1,000"
        series_font = f_series_en
        day_text = f"Day {day_n}"
        day_font = f_day_num
    else:
        series_text = "AI 帮我操盘"
        series_font = f_series_cn
        day_text = f"第 {day_n} 天"
        day_font = f_day_cn

    # Series name — upper
    bbox = d.textbbox((0, 0), series_text, font=series_font)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) // 2, 640), series_text, font=series_font, fill=FG)

    # Thin divider
    divider_y = 850
    d.rectangle((W // 2 - 40, divider_y, W // 2 + 40, divider_y + 4), fill=TERRACOTTA)

    # Day number — lower, large terracotta
    bbox = d.textbbox((0, 0), day_text, font=day_font)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) // 2, 950), day_text, font=day_font, fill=TERRACOTTA)

    footer_tag(d, img)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def card_topic_reveal(path, topic_en, topic_cn, is_english=False):
    """Second card — today's topic. VO speaks the topic verbatim."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Small top label "今日" / "TODAY"
    f_label = load_font(FONT_EN_BOLD if is_english else FONT_CN, 40, index=1)
    label = "TODAY" if is_english else "今天"
    bbox = d.textbbox((0, 0), label, font=f_label)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) // 2, 600), label, font=f_label, fill=MUTED)

    # Divider
    d.rectangle((W // 2 - 30, 680, W // 2 + 30, 683), fill=SAGE)

    # Topic text — big, centered
    topic = topic_en if is_english else topic_cn
    font = load_font(FONT_EN_BOLD if is_english else FONT_CN, 72, index=1)
    pad_x = 100
    max_w = W - 2 * pad_x
    wrap_fn = wrap_en if is_english else wrap_cn
    lines = wrap_fn(d, topic, font, max_w)
    lh = int(72 * 1.4)
    total_h = len(lines) * lh
    y = 800

    for ln in lines:
        bbox = d.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        d.text(((W - tw) // 2, y), ln, font=font, fill=FG)
        y += lh

    footer_tag(d, img)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def card_bilingual(path, en, cn, en_size=74, cn_size=54,
                   en_color=FG, cn_color=MUTED, bg=None):
    img = Image.new("RGB", (W, H), bg if bg else BG)
    d = ImageDraw.Draw(img)
    f_en = load_font(FONT_EN_BOLD, en_size, index=1)
    f_cn = load_font(FONT_CN, cn_size, index=1)

    pad_x = 100
    max_w = W - 2 * pad_x
    en_lines = wrap_en(d, en, f_en, max_w)
    cn_lines = wrap_cn(d, cn, f_cn, max_w)

    en_lh = int(en_size * 1.35)
    cn_lh = int(cn_size * 1.35)
    en_block_h = len(en_lines) * en_lh
    gap = 120
    cn_block_h = len(cn_lines) * cn_lh
    total_h = en_block_h + gap + cn_block_h
    y = (H - total_h) // 2

    for ln in en_lines:
        bbox = d.textbbox((0, 0), ln, font=f_en)
        tw = bbox[2] - bbox[0]
        d.text(((W - tw) // 2, y), ln, font=f_en, fill=en_color)
        y += en_lh
    y += gap
    for ln in cn_lines:
        bbox = d.textbbox((0, 0), ln, font=f_cn)
        tw = bbox[2] - bbox[0]
        d.text(((W - tw) // 2, y), ln, font=f_cn, fill=cn_color)
        y += cn_lh

    footer_tag(d, img, palette_fg=INK_MUTED if bg == CREAM_BG else MUTED)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def card_single(path, text, size=92, color=None, font_type="en", bg=None, accent=False):
    """Single-language impact card (used when CN-only or EN-only per episode variant)."""
    img = Image.new("RGB", (W, H), bg if bg else BG)
    d = ImageDraw.Draw(img)
    if color is None:
        color = TERRACOTTA if accent else (INK if bg == CREAM_BG else FG)

    font = load_font(FONT_EN_BOLD if font_type == "en" else FONT_CN, size, index=1)
    pad_x = 110
    max_w = W - 2 * pad_x
    lines = (wrap_en if font_type == "en" else wrap_cn)(d, text, font, max_w)
    lh = int(size * 1.4)
    total_h = len(lines) * lh
    y = (H - total_h) // 2

    for ln in lines:
        bbox = d.textbbox((0, 0), ln, font=font)
        tw = bbox[2] - bbox[0]
        d.text(((W - tw) // 2, y), ln, font=font, fill=color)
        y += lh

    footer_tag(d, img, palette_fg=INK_MUTED if bg == CREAM_BG else MUTED)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def card_stat(path, value, label_en, label_cn, value_color=None, bg=None):
    """Big number / statistic card."""
    img = Image.new("RGB", (W, H), bg if bg else BG)
    d = ImageDraw.Draw(img)
    if value_color is None:
        value_color = TERRACOTTA

    f_huge = load_font(FONT_EN_BOLD, 300, index=1)
    f_en = load_font(FONT_EN_BOLD, 58, index=1)
    f_cn = load_font(FONT_CN, 48, index=1)

    pad_x = 100
    max_w = W - 2 * pad_x

    bbox = d.textbbox((0, 0), value, font=f_huge)
    tw = bbox[2] - bbox[0]
    d.text(((W - tw) // 2, 560), value, font=f_huge, fill=value_color)
    y = 920

    ls = wrap_en(d, label_en, f_en, max_w)
    for ln in ls:
        bbox = d.textbbox((0, 0), ln, font=f_en)
        d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_en, fill=FG if bg != CREAM_BG else INK)
        y += 76
    y += 40
    ls = wrap_cn(d, label_cn, f_cn, max_w)
    for ln in ls:
        bbox = d.textbbox((0, 0), ln, font=f_cn)
        d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_cn, fill=MUTED if bg != CREAM_BG else INK_MUTED)
        y += 58

    footer_tag(d, img, palette_fg=INK_MUTED if bg == CREAM_BG else MUTED)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def card_outro(path, lesson_en, lesson_cn, day_n, is_english=False):
    """Closing card — the life lesson, signature callback."""
    img = Image.new("RGB", (W, H), CREAM_BG)
    d = ImageDraw.Draw(img)

    f_quote_en = load_font(FONT_EN_BOLD, 68, index=1)
    f_quote_cn = load_font(FONT_CN, 54, index=1)
    f_sig = load_font(FONT_EN_BOLD, 42, index=1)
    f_sig_cn = load_font(FONT_CN, 40, index=1)

    pad_x = 100
    max_w = W - 2 * pad_x

    # Decorative top quote mark
    f_mark = load_font(FONT_EN_BOLD, 200, index=1)
    d.text((120, 300), '"', font=f_mark, fill=TERRACOTTA)

    # English lesson
    en_lines = wrap_en(d, lesson_en, f_quote_en, max_w)
    y = 600
    for ln in en_lines:
        bbox = d.textbbox((0, 0), ln, font=f_quote_en)
        d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_quote_en, fill=INK)
        y += 86
    y += 100

    cn_lines = wrap_cn(d, lesson_cn, f_quote_cn, max_w)
    for ln in cn_lines:
        bbox = d.textbbox((0, 0), ln, font=f_quote_cn)
        d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_quote_cn, fill=INK_MUTED)
        y += 68

    # Signature callback
    sig_en = f"Day {day_n} · AI trades my $1,000"
    sig_cn = f"AI 帮我操盘第 {day_n} 天"
    d.text((pad_x, H - 240), sig_en, font=f_sig, fill=INK_MUTED)
    d.text((pad_x, H - 180), sig_cn, font=f_sig_cn, fill=INK_MUTED)
    f_tail = load_font(FONT_EN_BOLD, 36, index=1)
    d.text((pad_x, H - 120), "Tomorrow: Day %d →" % (day_n + 1), font=f_tail, fill=TERRACOTTA)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
