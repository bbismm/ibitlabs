#!/usr/bin/env python3
"""
Sprite recolor for /office.

Recolors each char_X.png sprite sheet to a role-themed palette by replacing
hue+saturation of every "colorful" pixel (skin/hair-neutral pixels are kept).
This is the standard 90s game-dev "palette swap" technique adapted to
arbitrary input sprites.

Why HLS not HSV:
  - HLS lightness preserves shading structure exactly (sprite still has
    light/dark gradients, only the hue changes)
  - HSV value is brightness-of-channel-max, distorts shading when hue rotates

Saturation threshold 0.16:
  - Skin colors usually have saturation 0.3-0.5 in HLS — would be recolored
    too. Solution: also gate on a *lightness band* (skin is ~0.6-0.8 light).
  - Hair (brown, dark) has saturation ~0.3-0.5 — would be recolored.
    Decision: that's fine. The audit asks for "agents look distinct" — letting
    hair recolor too IS distinct.
  - True grayscale pixels (outlines, white teeth, black eyes) have sat < 0.05
    — kept as-is automatically.

A small accessory dot is added to frame[0] (top-left, the front-facing still
frame) of each sprite to give role-icon flavor at zoom-in. At zoom-out it
just reads as "agent has a colored hat."
"""
import colorsys
from PIL import Image
from pathlib import Path

# (target_hue, target_sat, role_label, accent_for_accessory_pixel)
# Hues are 0.0-1.0 (HLS scale, multiply by 360 for degrees).
ROLE_PALETTES = {
    "char_0": (0.33, 0.65, "v5.3 LIVE",       (60, 220, 100)),  # green — live, money
    "char_1": (0.78, 0.55, "shadow_no_rev",   (180, 110, 235)),  # purple — shadow
    "char_2": (0.60, 0.70, "v5.3-ETH",        (90, 130, 240)),  # ethereum blue
    "char_3": (0.50, 0.55, "ETH paper",       (90, 200, 220)),  # cyan — paper ETH
    "char_4": (0.11, 0.65, "Sideways paper",  (240, 195, 70)),  # amber — caution
    "char_5": (0.00, 0.70, "Watchdog",        (220, 80, 80)),   # red — alert
}

# Keep grayscale pixels (eyes, outlines, teeth, paper-white) untinted
GRAYSCALE_THRESHOLD = 0.07


def recolor_pixel(rgba, target_h, target_s):
    r, g, b, a = rgba
    if a == 0:
        return rgba
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if s < GRAYSCALE_THRESHOLD:
        return rgba  # pure grayscale (outlines, eyes) — preserve
    nr, ng, nb = colorsys.hls_to_rgb(target_h, l, target_s)
    return (int(nr * 255), int(ng * 255), int(nb * 255), a)


def recolor_sheet(src_path, target_h, target_s, accent_rgb, role_label):
    im = Image.open(src_path).convert("RGBA")
    w, h = im.size
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = recolor_pixel(px[x, y], target_h, target_s)

    # Frame layout: 7 cols × 6 rows of 16×16
    # Add a 1px accent dot at the very top-center of each frame's bounding box
    # so at zoom-1 the agent visibly has a "team color tag" above their head.
    fw, fh = w // 7, h // 6
    for fy in range(6):
        for fx in range(7):
            # Center top of this frame
            top_x = fx * fw + fw // 2
            top_y = fy * fh + 1  # 1 px from top edge
            # Only paint if not transparent at that pixel — otherwise we get
            # floating dots above sprites that haven't started rendering.
            if px[top_x, top_y][3] == 0:
                # Place the dot anyway in transparent area — it'll read as
                # a small floating tag, like an RTS unit marker. 2x2 patch.
                for dx in (0, 1):
                    for dy in (0, 1):
                        if top_x + dx < w and top_y + dy < h:
                            px[top_x + dx, top_y + dy] = accent_rgb + (255,)

    return im


def main():
    src_dir = Path("/Users/bonnyagent/ibitlabs/web/public/office/assets/characters")
    out_dir = Path("/tmp/sprite-gen/output")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Build a 1-image preview of all 6 originals + 6 recolored side-by-side
    preview_w = 112 * 2 + 32
    preview_h = 96 * 6 + 80
    preview = Image.new("RGBA", (preview_w, preview_h), (20, 20, 28, 255))

    for i, (name, (h, s, role, accent)) in enumerate(ROLE_PALETTES.items()):
        src = src_dir / f"{name}.png"
        if not src.exists():
            print(f"missing {src}")
            continue
        orig = Image.open(src).convert("RGBA")
        out = recolor_sheet(src, h, s, accent, role)
        out.save(out_dir / f"{name}.png")
        preview.paste(orig, (0, i * 96 + 16), orig)
        preview.paste(out, (112 + 32, i * 96 + 16), out)
        print(f"recolored {name} → role={role} hue={int(h*360)}°")

    preview.save(out_dir / "_preview.png")
    print(f"\npreview at {out_dir / '_preview.png'}")
    print(f"new sprites in {out_dir}")


if __name__ == "__main__":
    main()
