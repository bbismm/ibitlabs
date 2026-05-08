"""Card rendering library for The Ghost in My Trading Bot series."""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

W, H = 1080, 1920
BG = (10, 10, 12)
FG = (245, 245, 245)
ACCENT_RED = (255, 90, 90)
ACCENT_GREEN = (130, 230, 160)
ACCENT_YELLOW = (255, 210, 100)
MUTED = (130, 130, 135)
CODE_GREEN = (130, 230, 160)
CODE_RED = (255, 110, 110)

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


def line_h(size):
    return int(size * 1.35)


def card_bilingual(path, en, cn, en_size=78, cn_size=56, en_color=FG, cn_color=MUTED):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_en = load_font(FONT_EN_BOLD, en_size, index=1)
    f_cn = load_font(FONT_CN, cn_size, index=1)

    pad_x = 90
    max_w = W - 2 * pad_x
    en_lines = wrap_en(d, en, f_en, max_w)
    cn_lines = wrap_cn(d, cn, f_cn, max_w)

    en_lh = line_h(en_size)
    cn_lh = line_h(cn_size)
    en_block_h = len(en_lines) * en_lh
    gap = 140
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

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def card_code(path, code_lines, caption_en=None, caption_cn=None,
              line_colors=None, code_size=40, caption_en_size=52, caption_cn_size=40):
    """code_lines: list of strings. line_colors: dict {index: color} for specific lines."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_code = load_font(FONT_MONO, code_size)
    f_en = load_font(FONT_EN_BOLD, caption_en_size, index=1)
    f_cn = load_font(FONT_CN, caption_cn_size, index=1)

    pad_x = 80
    code_y = 360
    lh = int(code_size * 1.38)

    line_colors = line_colors or {}
    for i, ln in enumerate(code_lines):
        color = line_colors.get(i, FG)
        if color == "auto":
            if ln.startswith("+"):
                color = CODE_GREEN
            elif ln.startswith("-"):
                color = CODE_RED
            else:
                color = FG
        d.text((pad_x, code_y + i * lh), ln, font=f_code, fill=color)

    code_block_h = len(code_lines) * lh
    cap_y = code_y + code_block_h + 130

    if caption_en:
        lines = wrap_en(d, caption_en, f_en, W - 2 * pad_x)
        for ln in lines:
            bbox = d.textbbox((0, 0), ln, font=f_en)
            d.text(((W - (bbox[2] - bbox[0])) // 2, cap_y), ln, font=f_en, fill=FG)
            cap_y += int(caption_en_size * 1.2)
        cap_y += 32
    if caption_cn:
        lines = wrap_cn(d, caption_cn, f_cn, W - 2 * pad_x)
        for ln in lines:
            bbox = d.textbbox((0, 0), ln, font=f_cn)
            d.text(((W - (bbox[2] - bbox[0])) // 2, cap_y), ln, font=f_cn, fill=MUTED)
            cap_y += int(caption_cn_size * 1.3)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def card_terminal(path, lines, caption_en=None, caption_cn=None, highlight_lines=None):
    """Terminal output card with green prompt feel."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_code = load_font(FONT_MONO, 36)
    f_en = load_font(FONT_EN_BOLD, 50, index=1)
    f_cn = load_font(FONT_CN, 40, index=1)

    pad_x = 70
    top = 320
    lh = 54

    highlight_lines = highlight_lines or []
    for i, ln in enumerate(lines):
        color = FG
        if i in highlight_lines:
            color = ACCENT_RED
        elif "✅" in ln or "clean" in ln.lower():
            color = ACCENT_GREEN
        d.text((pad_x, top + i * lh), ln, font=f_code, fill=color)

    cap_y = top + len(lines) * lh + 100
    if caption_en:
        ls = wrap_en(d, caption_en, f_en, W - 2 * pad_x)
        for ln in ls:
            bbox = d.textbbox((0, 0), ln, font=f_en)
            d.text(((W - (bbox[2] - bbox[0])) // 2, cap_y), ln, font=f_en, fill=FG)
            cap_y += 60
        cap_y += 20
    if caption_cn:
        ls = wrap_cn(d, caption_cn, f_cn, W - 2 * pad_x)
        for ln in ls:
            bbox = d.textbbox((0, 0), ln, font=f_cn)
            d.text(((W - (bbox[2] - bbox[0])) // 2, cap_y), ln, font=f_cn, fill=MUTED)
            cap_y += 52

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def card_split(path, left_label, left_value, left_desc, left_color,
               right_label, right_value, right_desc, right_color,
               top_banner=None, bottom_cn=None):
    """Two-column diagram card (used for LONG/SHORT, validated/pending, etc)."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_big = load_font(FONT_EN_BOLD, 110, index=1)
    f_med = load_font(FONT_EN_BOLD, 54, index=1)
    f_small = load_font(FONT_EN_BOLD, 44, index=1)
    f_cn = load_font(FONT_CN, 46, index=1)

    if top_banner:
        bbox = d.textbbox((0, 0), top_banner, font=f_med)
        d.text(((W - (bbox[2] - bbox[0])) // 2, 280), top_banner, font=f_med, fill=MUTED)

    col_w = W // 2
    card_y = 580
    card_h = 600

    d.rectangle((80, card_y, col_w - 20, card_y + card_h), outline=left_color, width=6)
    d.text((130, card_y + 50), left_label, font=f_med, fill=left_color)
    d.text((130, card_y + 180), left_value, font=f_big, fill=left_color)
    d.text((130, card_y + 440), left_desc, font=f_small, fill=MUTED)

    d.rectangle((col_w + 20, card_y, W - 80, card_y + card_h), outline=right_color, width=6)
    d.text((col_w + 70, card_y + 50), right_label, font=f_med, fill=right_color)
    d.text((col_w + 70, card_y + 180), right_value, font=f_big, fill=right_color)
    d.text((col_w + 70, card_y + 440), right_desc, font=f_small, fill=MUTED)

    if bottom_cn:
        cap_y = card_y + card_h + 100
        lines = wrap_cn(d, bottom_cn, f_cn, W - 160)
        for ln in lines:
            bbox = d.textbbox((0, 0), ln, font=f_cn)
            d.text(((W - (bbox[2] - bbox[0])) // 2, cap_y), ln, font=f_cn, fill=MUTED)
            cap_y += 60

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")


def card_big_number(path, number, number_color, label_en, label_cn, subtitle_en=None, subtitle_cn=None):
    """Large number focus card."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_huge = load_font(FONT_EN_BOLD, 260, index=1)
    f_en = load_font(FONT_EN_BOLD, 56, index=1)
    f_cn = load_font(FONT_CN, 48, index=1)

    y = 460
    bbox = d.textbbox((0, 0), number, font=f_huge)
    d.text(((W - (bbox[2] - bbox[0])) // 2, y), number, font=f_huge, fill=number_color)
    y += 340

    ls = wrap_en(d, label_en, f_en, W - 180)
    for ln in ls:
        bbox = d.textbbox((0, 0), ln, font=f_en)
        d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_en, fill=FG)
        y += 72
    y += 40
    ls = wrap_cn(d, label_cn, f_cn, W - 180)
    for ln in ls:
        bbox = d.textbbox((0, 0), ln, font=f_cn)
        d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_cn, fill=MUTED)
        y += 60

    if subtitle_en:
        y += 80
        ls = wrap_en(d, subtitle_en, f_en, W - 180)
        for ln in ls:
            bbox = d.textbbox((0, 0), ln, font=f_en)
            d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_en, fill=MUTED)
            y += 66
    if subtitle_cn:
        y += 30
        ls = wrap_cn(d, subtitle_cn, f_cn, W - 180)
        for ln in ls:
            bbox = d.textbbox((0, 0), ln, font=f_cn)
            d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_cn, fill=MUTED)
            y += 56

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
