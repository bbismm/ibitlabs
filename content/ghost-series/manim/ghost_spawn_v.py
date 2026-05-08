"""Vertical (1080x1920) ghost-position spawn animation.

Stacked layout:
  Top    — LONG +1 @ $88.39 (green, the intended position)
  Middle — market SELL arrow fires (no reduce_only tag)
  Bottom — new SHORT +1 @ $83.95 (red) with GHOST label
  Footer — balance $991.49 → $975.49, 5.5h undetected

Render:
  manim -qh ghost_spawn_v.py GhostSpawnVertical
"""
from manim import *

config.pixel_width = 1080
config.pixel_height = 1920
config.frame_width = 9
config.frame_height = 16


class GhostSpawnVertical(Scene):
    def construct(self):
        self.camera.background_color = "#0a0a0c"
        W_FG = "#F5F5F5"
        W_MUTED = "#82828A"
        C_GREEN = "#82E6A0"
        C_RED = "#FF5A5A"
        C_YELLOW = "#FFD264"

        # --- title ---------------------------------------------------
        title = Text("YOUR ACCOUNT", font="Helvetica", color=W_MUTED, weight=BOLD).scale(0.55)
        title.to_edge(UP, buff=1.0)
        self.play(FadeIn(title, shift=UP*0.2), run_time=0.5)

        # --- Step 1: LONG exists (top) ------------------------------
        long_box = RoundedRectangle(
            width=6.0, height=3.5, corner_radius=0.25,
            color=C_GREEN, stroke_width=6,
        ).shift(UP * 3.2)
        long_label = Text("LONG", font="Helvetica", weight=BOLD, color=C_GREEN).scale(0.9)
        long_label.move_to(long_box.get_top() + DOWN * 0.5)
        long_value = Text("+1", font="Helvetica", weight=BOLD, color=C_GREEN).scale(3.2)
        long_value.move_to(long_box.get_center() + UP * 0.1)
        long_cost = Text("@ $88.39  ·  intended", font="Menlo", color=W_MUTED).scale(0.55)
        long_cost.move_to(long_box.get_bottom() + UP * 0.4)

        self.play(Create(long_box), run_time=0.6)
        self.play(Write(long_label), Write(long_value), Write(long_cost), run_time=0.8)
        self.wait(0.6)

        # --- Step 2: market SELL fires (middle arrow) --------------
        sell_from = long_box.get_bottom() + DOWN * 0.3
        sell_to = long_box.get_bottom() + DOWN * 2.6
        arrow = Arrow(start=sell_from, end=sell_to, color=C_RED, buff=0, stroke_width=10)
        sell_label = Text("market SELL 1", font="Menlo", color=C_RED, weight=BOLD).scale(0.72)
        sell_label.next_to(arrow, RIGHT, buff=0.3)
        no_flag = Text("no reduce_only", font="Menlo", color=W_MUTED).scale(0.5)
        no_flag.next_to(sell_label, DOWN, buff=0.15, aligned_edge=LEFT)

        self.play(GrowArrow(arrow), FadeIn(sell_label, shift=LEFT*0.2), run_time=0.6)
        self.play(FadeIn(no_flag), run_time=0.4)
        self.wait(0.5)

        # --- Step 3: netting — LONG marked CLOSED, SHORT spawns ----
        closed_stamp = Text("CLOSED", font="Helvetica", weight=BOLD, color=W_MUTED).scale(1.1)
        closed_stamp.rotate(-PI / 12).move_to(long_box.get_center())

        short_box = RoundedRectangle(
            width=6.0, height=3.5, corner_radius=0.25,
            color=C_RED, stroke_width=6,
        ).shift(DOWN * 3.4)
        short_label = Text("SHORT", font="Helvetica", weight=BOLD, color=C_RED).scale(0.9)
        short_label.move_to(short_box.get_top() + DOWN * 0.5)
        short_value = Text("+1", font="Helvetica", weight=BOLD, color=C_RED).scale(3.2)
        short_value.move_to(short_box.get_center() + UP * 0.1)
        short_cost = Text("@ $83.95", font="Menlo", color=W_MUTED).scale(0.55)
        short_cost.move_to(short_box.get_bottom() + UP * 0.4)

        self.play(
            long_value.animate.set_opacity(0.22),
            long_label.animate.set_opacity(0.35),
            FadeOut(arrow), FadeOut(sell_label), FadeOut(no_flag),
            run_time=0.7,
        )
        self.play(FadeIn(closed_stamp, scale=1.2), run_time=0.5)
        self.play(Create(short_box), run_time=0.6)
        self.play(Write(short_label), Write(short_value), Write(short_cost), run_time=0.7)

        # --- Step 4: GHOST label appears over short box -----------
        ghost_tag = Text("GHOST", font="Helvetica", weight=BOLD, color=C_YELLOW).scale(1.0)
        ghost_tag.next_to(short_box, UP, buff=0.25)
        underline = Line(
            start=ghost_tag.get_corner(DL) + DOWN * 0.1,
            end=ghost_tag.get_corner(DR) + DOWN * 0.1,
            color=C_YELLOW, stroke_width=5,
        )
        self.play(FadeIn(ghost_tag, shift=DOWN*0.15), Create(underline), run_time=0.5)
        self.wait(0.5)

        # --- Step 5: balance bleed footer --------------------------
        bal_from = Text("$991.49", font="Menlo", color=W_MUTED).scale(0.75)
        arrow_mid = Text("→", font="Menlo", color=W_MUTED).scale(0.75)
        bal_to = Text("$975.49", font="Menlo", weight=BOLD, color=C_RED).scale(0.85)
        bleed = VGroup(bal_from, arrow_mid, bal_to).arrange(RIGHT, buff=0.28)
        bleed.to_edge(DOWN, buff=1.4)

        caption = Text("5.5 hours undetected", font="Helvetica", color=W_MUTED).scale(0.55)
        caption.next_to(bleed, DOWN, buff=0.3)

        self.play(FadeIn(bleed, shift=UP*0.2), FadeIn(caption, shift=UP*0.2), run_time=0.8)
        self.wait(1.0)
