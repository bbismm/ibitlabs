"""Ghost position spawn animation for Ep 1, 0:09-0:14 slot.

Narrative:
  Step 1 — LONG +1 exists (green box)
  Step 2 — market SELL fires (red arrow, no reduce_only tag)
  Step 3 — netting: LONG drops toward zero, but a new SHORT appears (red box)
  Step 4 — label both: "closed" and "ghost"
  Step 5 — balance starts dropping

Render:
  manim -qh ghost_spawn.py GhostSpawn       # 1080p60
  manim -ql ghost_spawn.py GhostSpawn       # 480p15 quick preview
"""
from manim import *


class GhostSpawn(Scene):
    def construct(self):
        self.camera.background_color = "#0a0a0c"
        W_FG = "#F5F5F5"
        W_MUTED = "#82828A"
        C_GREEN = "#82E6A0"
        C_RED = "#FF5A5A"
        C_YELLOW = "#FFD264"

        # --- Step 1: LONG +1 exists --------------------------------
        long_box = RoundedRectangle(
            width=3.5, height=4.5, corner_radius=0.2,
            color=C_GREEN, stroke_width=5,
        ).shift(LEFT * 3.5)
        long_label = Text("LONG", font="Helvetica", weight=BOLD, color=C_GREEN).scale(0.8).move_to(long_box.get_top() + DOWN * 0.6)
        long_value = Text("+1", font="Helvetica", weight=BOLD, color=C_GREEN).scale(2.8).move_to(long_box.get_center() + UP * 0.2)
        long_cost = Text("@ $88.39", font="Menlo", color=W_MUTED).scale(0.5).move_to(long_box.get_bottom() + UP * 0.5)
        long_group = VGroup(long_box, long_label, long_value, long_cost)

        title = Text("Account state", font="Helvetica", color=W_MUTED).scale(0.5).to_edge(UP, buff=1.0)

        self.play(FadeIn(title, shift=UP*0.2), run_time=0.5)
        self.play(Create(long_box), run_time=0.6)
        self.play(Write(long_label), Write(long_value), Write(long_cost), run_time=0.8)
        self.wait(0.6)

        # --- Step 2: bot fires market SELL -------------------------
        arrow = Arrow(
            start=UP * 2.5 + LEFT * 3.5,
            end=UP * 0.3 + LEFT * 3.5,
            color=C_RED, buff=0, stroke_width=8,
        )
        sell_label = Text("market SELL 1", font="Menlo", color=C_RED, weight=BOLD).scale(0.55).move_to(arrow.get_start() + UP * 0.4)
        no_flag = Text("no reduce_only  ·  no close endpoint", font="Menlo", color=W_MUTED).scale(0.35).move_to(arrow.get_start() + UP * 0.85)

        self.play(FadeIn(sell_label, shift=DOWN*0.15), FadeIn(no_flag, shift=DOWN*0.15), run_time=0.6)
        self.play(GrowArrow(arrow), run_time=0.5)
        self.wait(0.4)

        # --- Step 3: netting — LONG closes, SHORT spawns -----------
        closed_stamp = Text("CLOSED", font="Helvetica", weight=BOLD, color=W_MUTED).scale(0.7).move_to(long_box.get_center())

        short_box = RoundedRectangle(
            width=3.5, height=4.5, corner_radius=0.2,
            color=C_RED, stroke_width=5,
        ).shift(RIGHT * 3.5)
        short_label = Text("SHORT", font="Helvetica", weight=BOLD, color=C_RED).scale(0.8).move_to(short_box.get_top() + DOWN * 0.6)
        short_value = Text("+1", font="Helvetica", weight=BOLD, color=C_RED).scale(2.8).move_to(short_box.get_center() + UP * 0.2)
        short_cost = Text("@ $83.95", font="Menlo", color=W_MUTED).scale(0.5).move_to(short_box.get_bottom() + UP * 0.5)

        # LONG fades to "closed", SHORT box fades in
        self.play(
            long_value.animate.set_opacity(0.25),
            long_label.animate.set_opacity(0.35),
            FadeOut(arrow), FadeOut(sell_label), FadeOut(no_flag),
            run_time=0.7,
        )
        self.play(FadeIn(closed_stamp), run_time=0.4)
        self.play(Create(short_box), run_time=0.6)
        self.play(Write(short_label), Write(short_value), Write(short_cost), run_time=0.7)

        # --- Step 4: ghost label ----------------------------------
        ghost_tag = Text("GHOST", font="Helvetica", weight=BOLD, color=C_YELLOW).scale(0.85)
        ghost_tag.move_to(short_box.get_top() + UP * 0.5)
        ghost_underline = Line(
            start=ghost_tag.get_corner(DL) + DOWN * 0.1,
            end=ghost_tag.get_corner(DR) + DOWN * 0.1,
            color=C_YELLOW, stroke_width=4,
        )
        self.play(FadeIn(ghost_tag, shift=DOWN*0.1), Create(ghost_underline), run_time=0.5)
        self.wait(0.4)

        # --- Step 5: balance bleeds -------------------------------
        bal_text = Text("$991.49 →", font="Menlo", color=W_MUTED).scale(0.55)
        bal_val = Text("$975.49", font="Menlo", color=C_RED, weight=BOLD).scale(0.6)
        bleed = VGroup(bal_text, bal_val).arrange(RIGHT, buff=0.25).to_edge(DOWN, buff=1.2)
        bleed_label = Text("5.5 hours undetected", font="Helvetica", color=W_MUTED).scale(0.4).next_to(bleed, DOWN, buff=0.25)

        self.play(FadeIn(bleed, shift=UP*0.15), FadeIn(bleed_label, shift=UP*0.15), run_time=0.7)
        self.wait(1.0)
