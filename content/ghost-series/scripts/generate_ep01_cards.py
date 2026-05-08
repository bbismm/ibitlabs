"""
Generate 1080x1920 bilingual text cards for Ep 1 of The Ghost in My Trading Bot.
Output: ~/ibitlabs/content/ghost-series/assets/cards/ep01/*.png
"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

OUT = Path.home() / "ibitlabs/content/ghost-series/assets/cards/ep01"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1080, 1920
BG = (10, 10, 12)
FG = (245, 245, 245)
ACCENT_RED = (255, 90, 90)
ACCENT_GREEN = (130, 230, 160)
MUTED = (130, 130, 135)

FONT_EN_BOLD = "/System/Library/Fonts/Helvetica.ttc"
FONT_CN = "/System/Library/Fonts/Hiragino Sans GB.ttc"
FONT_MONO = "/System/Library/Fonts/Menlo.ttc"


def load(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


def wrap_text(draw, text, font, max_w):
    out = []
    for segment in text.split("\n"):
        words = segment.split(" ")
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
    for segment in text.split("\n"):
        cur = ""
        for ch in segment:
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


def card_bilingual(filename, en, cn, en_size=78, cn_size=56, en_color=FG, cn_color=MUTED):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_en = load(FONT_EN_BOLD, en_size, index=1)
    f_cn = load(FONT_CN, cn_size, index=1)

    pad_x = 90
    max_w = W - 2 * pad_x
    en_lines = wrap_text(d, en, f_en, max_w)
    cn_lines = wrap_cn(d, cn, f_cn, max_w)

    def line_h(font, size_hint):
        return int(size_hint * 1.35)

    en_line_h = line_h(f_en, en_size)
    cn_line_h = line_h(f_cn, cn_size)
    en_block_h = len(en_lines) * en_line_h
    gap = 140
    cn_block_h = len(cn_lines) * cn_line_h
    total_h = en_block_h + gap + cn_block_h
    y = (H - total_h) // 2

    for ln in en_lines:
        bbox = d.textbbox((0, 0), ln, font=f_en)
        tw = bbox[2] - bbox[0]
        d.text(((W - tw) // 2, y), ln, font=f_en, fill=en_color)
        y += en_line_h
    y += gap
    for ln in cn_lines:
        bbox = d.textbbox((0, 0), ln, font=f_cn)
        tw = bbox[2] - bbox[0]
        d.text(((W - tw) // 2, y), ln, font=f_cn, fill=cn_color)
        y += cn_line_h

    img.save(OUT / filename, "PNG")
    print(f"  {filename}  ({len(en_lines)} EN lines, {len(cn_lines)} CN lines)")


def card_code(filename, code_lines, caption_en=None, caption_cn=None, highlight_lines=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_code = load(FONT_MONO, 40)
    f_en = load(FONT_EN_BOLD, 52, index=1)
    f_cn = load(FONT_CN, 40, index=1)

    pad_x = 80
    code_y = 380
    line_h_code = 56

    highlight_lines = highlight_lines or []
    for i, line in enumerate(code_lines):
        color = FG
        if i in highlight_lines:
            color = ACCENT_RED
        elif line.startswith("+"):
            color = ACCENT_GREEN
        elif line.startswith("-"):
            color = ACCENT_RED
        d.text((pad_x, code_y + i * line_h_code), line, font=f_code, fill=color)

    code_block_h = len(code_lines) * line_h_code
    cap_y = code_y + code_block_h + 120

    if caption_en:
        lines = wrap_text(d, caption_en, f_en, W - 2 * pad_x)
        for ln in lines:
            bbox = d.textbbox((0, 0), ln, font=f_en)
            d.text(((W - (bbox[2] - bbox[0])) // 2, cap_y), ln, font=f_en, fill=FG)
            cap_y += 62
        cap_y += 32
    if caption_cn:
        lines = wrap_cn(d, caption_cn, f_cn, W - 2 * pad_x)
        for ln in lines:
            bbox = d.textbbox((0, 0), ln, font=f_cn)
            d.text(((W - (bbox[2] - bbox[0])) // 2, cap_y), ln, font=f_cn, fill=MUTED)
            cap_y += 52

    img.save(OUT / filename, "PNG")
    print(f"  {filename}  (code card, {len(code_lines)} lines)")


def card_diagram_long_short(filename):
    """Show LONG +1 and new SHORT +1 simultaneously."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_big = load(FONT_EN_BOLD, 120, index=1)
    f_med = load(FONT_EN_BOLD, 56, index=1)
    f_cn = load(FONT_CN, 48, index=1)

    title = "SAME ACCOUNT · SAME SECOND"
    bbox = d.textbbox((0, 0), title, font=f_med)
    d.text(((W - (bbox[2] - bbox[0])) // 2, 280), title, font=f_med, fill=MUTED)

    col_w = W // 2
    card_y = 580
    card_h = 600

    d.rectangle((80, card_y, 80 + col_w - 120, card_y + card_h), outline=ACCENT_GREEN, width=6)
    d.text((130, card_y + 50), "LONG", font=f_med, fill=ACCENT_GREEN)
    bbox = d.textbbox((0, 0), "+1", font=f_big)
    d.text((130, card_y + 180), "+1", font=f_big, fill=ACCENT_GREEN)
    d.text((130, card_y + 420), "intended", font=f_med, fill=MUTED)

    d.rectangle((col_w + 40, card_y, W - 80, card_y + card_h), outline=ACCENT_RED, width=6)
    d.text((col_w + 90, card_y + 50), "SHORT", font=f_med, fill=ACCENT_RED)
    d.text((col_w + 90, card_y + 180), "+1", font=f_big, fill=ACCENT_RED)
    d.text((col_w + 90, card_y + 420), "ghost", font=f_med, fill=MUTED)

    cap_y = card_y + card_h + 100
    cn = "同一账户，同一秒钟 —— 多了一个幽灵空单"
    lines = wrap_cn(d, cn, f_cn, W - 160)
    for ln in lines:
        bbox = d.textbbox((0, 0), ln, font=f_cn)
        d.text(((W - (bbox[2] - bbox[0])) // 2, cap_y), ln, font=f_cn, fill=MUTED)
        cap_y += 60

    img.save(OUT / filename, "PNG")
    print(f"  {filename}  (diagram card)")


def card_balance_drop(filename):
    """Balance curve dropping with ghost bleeding caption."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_big = load(FONT_EN_BOLD, 96, index=1)
    f_med = load(FONT_EN_BOLD, 52, index=1)
    f_cn = load(FONT_CN, 46, index=1)

    d.text((90, 300), "$991.49", font=f_med, fill=MUTED)
    d.text((90, 370), "↓", font=f_big, fill=ACCENT_RED)
    d.text((90, 520), "$975.49", font=f_big, fill=ACCENT_RED)
    d.text((90, 660), "−$16 in 5.5 hours", font=f_med, fill=MUTED)
    d.text((90, 740), "while the bot thought it was flat", font=f_med, fill=MUTED)

    y = 1120
    en = ["Stop-loss fired.", "The long closed at a loss.", "The ghost short kept bleeding."]
    for ln in en:
        bbox = d.textbbox((0, 0), ln, font=f_med)
        d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_med, fill=FG)
        y += 70

    y += 50
    cn = ["止损触发。", "多单以亏损平掉。", "那个幽灵空单继续流血。"]
    for ln in cn:
        bbox = d.textbbox((0, 0), ln, font=f_cn)
        d.text(((W - (bbox[2] - bbox[0])) // 2, y), ln, font=f_cn, fill=MUTED)
        y += 60

    img.save(OUT / filename, "PNG")
    print(f"  {filename}  (balance drop card)")


print(f"Generating cards to {OUT}")

card_bilingual(
    "01_hook.png",
    "This position does not exist.\nI just lost $40 to it.",
    "这个仓位不存在。\n我为它亏了 40 美元。",
    en_size=88, cn_size=62,
    en_color=FG,
)

card_bilingual(
    "02_setup.png",
    "My bot placed a sell to close a long.",
    "我的机器人下了一个卖单，本意是平掉一个多单。",
)

card_diagram_long_short("03_diagram.png")

card_bilingual(
    "04_twin.png",
    "The long closed. The sell opened a new short.",
    "多单平掉了。但那个卖单同时开了一个新的空单。",
)

card_bilingual(
    "05_api_quote.png",
    'Coinbase\'s API doesn\'t know a "close" is a close.',
    'Coinbase 的 API 不知道"平仓"是平仓。',
    en_color=ACCENT_RED,
)

card_code(
    "06_code_bad.png",
    [
        "self.exchange.create_market_order(",
        "    symbol=symbol,",
        "    side='SELL',       # <- treated as",
        "    amount=quantity,    #    a new order,",
        ")                       #    not a close",
    ],
    caption_en="No reduce_only. No close endpoint.",
    caption_cn="没 reduce_only，也没调专用接口。",
    highlight_lines=[2],
)

card_bilingual(
    "07_neither.png",
    "Unless you set reduce_only,\nor hit a special endpoint.\nMy bot did neither.",
    "除非你设 reduce_only，\n或调用专用接口。\n我的机器人两样都没做。",
    en_size=74, cn_size=54,
)

card_balance_drop("08_balance_drop.png")

card_bilingual(
    "09_tease.png",
    "I then spent 20 hours\nblaming the wrong things.",
    "接下来 20 小时，\n我一直在怪错对象。",
    en_size=88, cn_size=60,
    en_color=FG, cn_color=FG,
)

print("\nAll 9 cards generated.")
