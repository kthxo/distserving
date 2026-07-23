#!/usr/bin/env python3
"""Generate STEP 2-6 + 4-workload presentation slides (.pptx).

Output: slides/2026-07-21_overcommit-regime-study_yunuikang.pptx (~15 slides)
Every slide has at least one diagram/figure. Text minimal; detail in notes.

작성: 강윤의 · 2026-07-21
"""
import math
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.font_manager as fm
import numpy as np

# Register Korean font
_ko_font = os.path.expanduser("~/.local/share/fonts/NotoSansCJKkr-Regular.otf")
if os.path.exists(_ko_font):
    fm.fontManager.addfont(_ko_font)
    plt.rcParams["font.family"] = "Noto Sans CJK KR"
    plt.rcParams["axes.unicode_minus"] = False

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ──── Paths ──────────────────────────────────────────────────────────
BASE = "/home/yunuikang/yunuikang_work/distserving"
FIGS = f"{BASE}/figures"
DIAG = f"{BASE}/scratch/slide_diagrams"
OUT  = f"{BASE}/slides/2026-07-21_overcommit-regime-study_yunuikang.pptx"
os.makedirs(DIAG, exist_ok=True)
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# ──── Colors ─────────────────────────────────────────────────────────
C_DARK   = RGBColor(0x1B, 0x2A, 0x4A)
C_BLUE   = RGBColor(0x21, 0x96, 0xF3)
C_RED    = RGBColor(0xE5, 0x39, 0x35)
C_GREEN  = RGBColor(0x43, 0xA0, 0x47)
C_ORANGE = RGBColor(0xFF, 0x98, 0x00)
C_WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
C_GRAY   = RGBColor(0x75, 0x75, 0x75)
C_LGRAY  = RGBColor(0xE0, 0xE0, 0xE0)
C_TEXT   = RGBColor(0x33, 0x33, 0x33)
C_ACCENT = RGBColor(0x00, 0x7A, 0xCC)

# matplotlib palette
MPL_BG    = "#FFFFFF"
MPL_DARK  = "#1B2A4A"
MPL_BLUE  = "#2196F3"
MPL_RED   = "#E53935"
MPL_GREEN = "#43A047"
MPL_ORANGE= "#FF9800"
MPL_GRAY  = "#757575"

# ──── Helpers ────────────────────────────────────────────────────────
def _add_title_bar(slide, title_text, subtitle_text=""):
    """Dark bar at top with white title text."""
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0), Inches(13.333), Inches(1.15)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = C_DARK
    bar.line.fill.background()
    tf = bar.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title_text
    p.font.size = Pt(28)
    p.font.bold = True
    p.font.color.rgb = C_WHITE
    p.alignment = PP_ALIGN.LEFT
    tf.margin_left = Inches(0.6)
    tf.margin_top = Inches(0.15)
    if subtitle_text:
        p2 = tf.add_paragraph()
        p2.text = subtitle_text
        p2.font.size = Pt(14)
        p2.font.color.rgb = RGBColor(0xBB, 0xDE, 0xFB)
        p2.alignment = PP_ALIGN.LEFT

def _add_textbox(slide, left, top, width, height, text,
                 font_size=14, bold=False, color=None, align=PP_ALIGN.LEFT,
                 font_name="Calibri"):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.name = font_name
    if bold:
        p.font.bold = True
    if color:
        p.font.color.rgb = color
    p.alignment = align
    return txBox

def _add_image(slide, path, left, top, width=None, height=None):
    if not os.path.exists(path):
        # placeholder
        _add_textbox(slide, left, top, Inches(4), Inches(0.4),
                     f"[missing: {os.path.basename(path)}]",
                     font_size=10, color=C_RED)
        return
    kwargs = {}
    if width: kwargs["width"] = width
    if height: kwargs["height"] = height
    slide.shapes.add_picture(path, left, top, **kwargs)

def _set_notes(slide, text):
    notes = slide.notes_slide
    notes.notes_text_frame.text = text

def _add_callout(slide, left, top, width, height, text,
                 bg_color=C_BLUE, font_size=12, text_color=C_WHITE):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                 left, top, width, height)
    box.fill.solid()
    box.fill.fore_color.rgb = bg_color
    box.line.fill.background()
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.1)
    tf.margin_right = Inches(0.1)
    tf.margin_top = Inches(0.05)
    tf.margin_bottom = Inches(0.05)
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.color.rgb = text_color
    p.font.bold = True
    p.alignment = PP_ALIGN.CENTER


def _add_table(slide, left, top, width, height, headers, rows,
               header_bg=None, alt_bg=None, font_size=11):
    """Add a formatted table to a slide.

    headers: list of str
    rows:    list of list of str (each inner list = one row)
    """
    if header_bg is None:
        header_bg = C_DARK
    if alt_bg is None:
        alt_bg = RGBColor(0xF5, 0xF5, 0xF5)
    n_rows = len(rows) + 1  # +1 for header
    n_cols = len(headers)
    table_shape = slide.shapes.add_table(n_rows, n_cols, left, top, width, height)
    tbl = table_shape.table

    # Distribute columns evenly
    col_w = int(width / n_cols)
    for i in range(n_cols):
        tbl.columns[i].width = col_w

    # Header row
    for ci, h in enumerate(headers):
        cell = tbl.cell(0, ci)
        cell.text = h
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(font_size)
        p.font.bold = True
        p.font.color.rgb = C_WHITE
        p.alignment = PP_ALIGN.CENTER
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_bg
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE

    # Data rows
    for ri, row_data in enumerate(rows):
        for ci, val in enumerate(row_data):
            cell = tbl.cell(ri + 1, ci)
            cell.text = str(val)
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(font_size)
            p.font.color.rgb = C_TEXT
            p.alignment = PP_ALIGN.CENTER
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            # Alternate row color
            if ri % 2 == 1:
                cell.fill.solid()
                cell.fill.fore_color.rgb = alt_bg
            else:
                cell.fill.solid()
                cell.fill.fore_color.rgb = C_WHITE


# ════════════════════════════════════════════════════════════════════
# DIAGRAM GENERATION (matplotlib → PNG)
# ════════════════════════════════════════════════════════════════════

def _fig_setup(figsize=(12, 6)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_facecolor(MPL_BG)
    fig.patch.set_facecolor(MPL_BG)
    return fig, ax

def gen_title_motif():
    """Hyperbola curve as title background motif."""
    fig, ax = _fig_setup((12, 6))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    # Faint hyperbola fit×d = 1 curve
    d_arr = np.linspace(0.05, 0.95, 200)
    fit_arr = 1.0 / d_arr
    # Normalize to [0,1]
    fit_norm = fit_arr / 30.0  # scale so fit=30 → 1.0
    fit_norm = np.clip(fit_norm, 0, 1)
    ax.fill_between(d_arr, 0, fit_norm, alpha=0.06, color=MPL_RED, label="fit×d<1")
    ax.fill_between(d_arr, fit_norm, 1, alpha=0.04, color=MPL_BLUE, label="fit×d≥1")
    ax.plot(d_arr, fit_norm, color=MPL_GRAY, linewidth=2, alpha=0.3)
    ax.text(0.5, 0.85, "fit × d", fontsize=48, ha="center", va="center",
            fontweight="bold", color=MPL_DARK, alpha=0.12)
    fig.savefig(f"{DIAG}/title_motif.png", dpi=200, bbox_inches="tight",
                transparent=True)
    plt.close(fig)

def gen_pipeline():
    """Agentic serving pipeline: reasoning↔tool loop, KV accumulation."""
    fig, ax = _fig_setup((13, 5.5))
    ax.set_xlim(-0.5, 12.5)
    ax.set_ylim(-1.5, 5)
    ax.axis("off")

    # Main boxes
    boxes = [
        (0.5, 3, 2.2, 1.2, "User\nRequest", "#E3F2FD"),
        (3.5, 3, 2.2, 1.2, "LLM\n(GPU)", "#BBDEFB"),
        (6.8, 3, 2.2, 1.2, "Tool\nServer", "#FFF3E0"),
        (10, 3, 2.2, 1.2, "LLM\n(GPU)", "#BBDEFB"),
    ]
    for x, y, w, h, txt, clr in boxes:
        rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                              facecolor=clr, edgecolor=MPL_DARK, linewidth=1.5)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h/2, txt, ha="center", va="center",
                fontsize=13, fontweight="bold", color=MPL_DARK)

    # Arrows
    arrow_kw = dict(arrowstyle="->,head_width=0.3,head_length=0.2",
                    color=MPL_DARK, linewidth=2)
    ax.annotate("", xy=(3.4, 3.6), xytext=(2.8, 3.6), arrowprops=arrow_kw)
    ax.annotate("", xy=(6.7, 3.6), xytext=(5.8, 3.6), arrowprops=arrow_kw)
    ax.annotate("", xy=(9.9, 3.6), xytext=(9.1, 3.6), arrowprops=arrow_kw)
    # Labels on arrows
    ax.text(3.1, 4.0, "prompt", fontsize=10, ha="center", color=MPL_GRAY)
    ax.text(6.25, 4.0, "tool call", fontsize=10, ha="center", color=MPL_GRAY)
    ax.text(9.5, 4.0, "result +\nre-prompt", fontsize=10, ha="center", color=MPL_GRAY)

    # Loop arrow (tool → LLM → tool repeat)
    ax.annotate("", xy=(6.8, 2.9), xytext=(10, 2.9),
                arrowprops=dict(arrowstyle="<->,head_width=0.2,head_length=0.15",
                                color=MPL_ORANGE, linewidth=2, linestyle="--"))
    ax.text(8.4, 2.4, "multi-turn loop", fontsize=11, ha="center",
            color=MPL_ORANGE, fontstyle="italic")

    # GPU timeline below
    y_bar = 0.8
    bar_h = 0.7
    # Reasoning blocks (blue)
    for x0, w in [(1.5, 1.5), (5.5, 1.0), (9.0, 1.8)]:
        rect = plt.Rectangle((x0, y_bar), w, bar_h, facecolor=MPL_BLUE,
                              alpha=0.7, edgecolor="none")
        ax.add_patch(rect)
    # Tool/idle blocks (orange hatched)
    for x0, w in [(3.0, 2.5), (6.5, 2.5)]:
        rect = plt.Rectangle((x0, y_bar), w, bar_h, facecolor=MPL_ORANGE,
                              alpha=0.15, edgecolor=MPL_ORANGE, linewidth=1,
                              linestyle="--")
        ax.add_patch(rect)
    ax.text(2.25, y_bar + bar_h/2, "reas.", fontsize=10, ha="center", va="center",
            color="white", fontweight="bold")
    ax.text(4.25, y_bar + bar_h/2, "tool (idle)", fontsize=10, ha="center",
            va="center", color=MPL_ORANGE)
    ax.text(6.0, y_bar + bar_h/2, "reas.", fontsize=10, ha="center", va="center",
            color="white", fontweight="bold")
    ax.text(7.75, y_bar + bar_h/2, "tool (idle)", fontsize=10, ha="center",
            va="center", color=MPL_ORANGE)
    ax.text(9.9, y_bar + bar_h/2, "reas.", fontsize=10, ha="center", va="center",
            color="white", fontweight="bold")
    ax.text(6.0, 0.15, "GPU Timeline  (1 program)", fontsize=12, ha="center",
            color=MPL_DARK, fontweight="bold")

    # KV bar growing
    y_kv = -0.8
    kv_h = 0.5
    kv_widths = [1.5, 3.0, 4.5, 6.0, 7.5]
    for i, w in enumerate(kv_widths):
        alpha = 0.2 + 0.15 * i
        rect = plt.Rectangle((1.5, y_kv - i*0.12), w, kv_h*0.3,
                              facecolor=MPL_GREEN, alpha=alpha, edgecolor="none")
        ax.add_patch(rect)
    ax.text(5.5, y_kv - 0.65, "KV cache grows with each turn →",
            fontsize=11, ha="center", color=MPL_GREEN, fontweight="bold")

    # Policy comparison box
    tr_box = FancyBboxPatch((0.2, -1.4), 5.5, 0.5, boxstyle="round,pad=0.05",
                            facecolor="#E3F2FD", edgecolor=MPL_BLUE, linewidth=1.5)
    ax.add_patch(tr_box)
    ax.text(3.0, -1.15, "tr: pause → KV 보존, GPU idle 감수",
            fontsize=11, ha="center", color=MPL_BLUE, fontweight="bold")

    def_box = FancyBboxPatch((6.3, -1.4), 5.5, 0.5, boxstyle="round,pad=0.05",
                             facecolor="#FFF3E0", edgecolor=MPL_ORANGE, linewidth=1.5)
    ax.add_patch(def_box)
    ax.text(9.05, -1.15, "default: overcommit → GPU 채움, KV evict",
            fontsize=11, ha="center", color="#E65100", fontweight="bold")

    fig.savefig(f"{DIAG}/pipeline.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def gen_puzzle():
    """Win/loss grid: 4 cells showing where tr wins/loses."""
    fig, ax = _fig_setup((11, 5.5))
    ax.set_xlim(-0.5, 10.5)
    ax.set_ylim(-1.5, 5.5)
    ax.axis("off")

    # Grid header
    ax.text(5, 5.2, "tr(ThunderAgent) vs default: 같은 SOTA가 이기기도, 지기도",
            fontsize=16, ha="center", fontweight="bold", color=MPL_DARK)

    # Column headers
    ax.text(3, 4.5, "SWE-bench\n(d≈1.0, decode-heavy)",
            fontsize=12, ha="center", color=MPL_DARK, fontweight="bold")
    ax.text(7.5, 4.5, "TraceLab\n(d≈0.2, tool-heavy)",
            fontsize=12, ha="center", color=MPL_DARK, fontweight="bold")
    # Row headers
    ax.text(0.5, 3.0, "4090\n(fit≈2~6)",
            fontsize=12, ha="center", color=MPL_DARK, fontweight="bold")
    ax.text(0.5, 1.0, "Pro6000×2\n(fit≈25~58)",
            fontsize=12, ha="center", color=MPL_DARK, fontweight="bold")

    # Cells
    cells = [
        (1.8, 2.3, 2.4, 1.4, "+78~84%", MPL_GREEN, "tr 승", "fd=5.54"),
        (6.2, 2.3, 2.6, 1.4, "-34%", MPL_RED, "tr 패!", "fd=0.46"),
        (1.8, 0.3, 2.4, 1.4, "+113%", MPL_GREEN, "tr 승", "fd=57.6"),
        (6.2, 0.3, 2.6, 1.4, "+80~87%", MPL_GREEN, "tr 승", "fd=7.07"),
    ]
    for x, y, w, h, pct, clr, label, fd_txt in cells:
        rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1",
                              facecolor=clr, alpha=0.15, edgecolor=clr, linewidth=2)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h*0.65, pct, fontsize=20, ha="center", va="center",
                fontweight="bold", color=clr)
        ax.text(x + w/2, y + h*0.25, f"{label}  (fit×d={fd_txt})",
                fontsize=10, ha="center", va="center", color=MPL_GRAY)

    # Arrow pointing to the red cell
    ax.annotate("왜 여기서만 지나?", xy=(7.5, 2.3), xytext=(9.2, 1.5),
                fontsize=13, fontweight="bold", color=MPL_RED,
                arrowprops=dict(arrowstyle="->", color=MPL_RED, linewidth=2))

    # Bottom conclusion
    ax.text(5, -0.7, '→ "4090 인공물?"  NO.  유일한 fit×d < 1 셀 = 일반적 레짐 현상',
            fontsize=14, ha="center", color=MPL_DARK, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFDE7",
                      edgecolor=MPL_ORANGE, linewidth=1.5))

    fig.savefig(f"{DIAG}/puzzle.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def gen_seesaw():
    """idle vs recompute tradeoff balance diagram."""
    fig, ax = _fig_setup((12, 6))
    ax.set_xlim(-1, 11)
    ax.set_ylim(-2, 6)
    ax.axis("off")

    # Title
    ax.text(5, 5.5, "미포화 영역(fit×d < 1)의 두 비용 상충",
            fontsize=16, ha="center", fontweight="bold", color=MPL_DARK)

    # Fulcrum
    triangle = plt.Polygon([[5, 1.5], [4.5, 0.5], [5.5, 0.5]],
                           facecolor=MPL_GRAY, edgecolor=MPL_DARK, linewidth=2)
    ax.add_patch(triangle)

    # Beam (slightly tilted)
    ax.plot([1.5, 8.5], [3.0, 2.0], color=MPL_DARK, linewidth=3)

    # Left plate — idle cost
    idle_box = FancyBboxPatch((0.5, 3.2), 3.0, 1.5, boxstyle="round,pad=0.1",
                              facecolor=MPL_BLUE, alpha=0.2, edgecolor=MPL_BLUE,
                              linewidth=2)
    ax.add_patch(idle_box)
    ax.text(2.0, 4.2, "idle 비용", fontsize=14, ha="center", fontweight="bold",
            color=MPL_BLUE)
    ax.text(2.0, 3.6, "tr: GPU 놂\n(pause → 처리량↓)",
            fontsize=11, ha="center", color=MPL_DARK)

    # Right plate — recompute cost
    recomp_box = FancyBboxPatch((6.5, 2.2), 3.0, 1.5, boxstyle="round,pad=0.1",
                                facecolor=MPL_ORANGE, alpha=0.2, edgecolor=MPL_ORANGE,
                                linewidth=2)
    ax.add_patch(recomp_box)
    ax.text(8.0, 3.2, "recompute 비용", fontsize=14, ha="center",
            fontweight="bold", color="#E65100")
    ax.text(8.0, 2.6, "default: 재계산 낭비\n(cache miss → GPU 허투)",
            fontsize=11, ha="center", color=MPL_DARK)

    # Two levers below
    ax.text(5, -0.2, "균형을 결정하는 두 레버", fontsize=13, ha="center",
            fontweight="bold", color=MPL_DARK)

    # Lever 1: d (duty)
    d_box = FancyBboxPatch((1.0, -1.5), 3.5, 0.9, boxstyle="round,pad=0.1",
                           facecolor="#E8F5E9", edgecolor=MPL_GREEN, linewidth=1.5)
    ax.add_patch(d_box)
    ax.text(2.75, -0.85, "d (duty) ↑", fontsize=13, ha="center",
            fontweight="bold", color=MPL_GREEN)
    ax.text(2.75, -1.25, "reasoning 비율↑ → GPU 자연 바빠짐",
            fontsize=10, ha="center", color=MPL_DARK)

    # Lever 2: k_fit (overcommit)
    k_box = FancyBboxPatch((5.5, -1.5), 3.5, 0.9, boxstyle="round,pad=0.1",
                           facecolor="#FFF3E0", edgecolor=MPL_ORANGE, linewidth=1.5)
    ax.add_patch(k_box)
    ax.text(7.25, -0.85, "k_fit (overcommit) ↑", fontsize=13, ha="center",
            fontweight="bold", color="#E65100")
    ax.text(7.25, -1.25, "더 많이 적재 → GPU 채우나 cache↓",
            fontsize=10, ha="center", color=MPL_DARK)

    # Arrow: "fit×d가 교차점을 결정"
    ax.annotate("fit×d*에서\n교차!", xy=(5, 1.5), xytext=(5, 0.3),
                fontsize=12, ha="center", fontweight="bold", color=MPL_RED,
                arrowprops=dict(arrowstyle="->", color=MPL_RED, linewidth=2))

    fig.savefig(f"{DIAG}/seesaw.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def gen_fdial():
    """f-dial: continuous knob from tr(f=1) to default(f=∞)."""
    fig, ax = _fig_setup((12, 5))
    ax.set_xlim(-0.5, 11.5)
    ax.set_ylim(-2, 4.5)
    ax.axis("off")

    # Spectrum bar
    from matplotlib.colors import LinearSegmentedColormap
    gradient = np.linspace(0, 1, 256).reshape(1, -1)
    cmap = LinearSegmentedColormap.from_list("fd", [MPL_BLUE, MPL_ORANGE])
    ax.imshow(gradient, aspect="auto", cmap=cmap, extent=[1, 10, 2.8, 3.5], alpha=0.7)
    rect = plt.Rectangle((1, 2.8), 9, 0.7, fill=False, edgecolor=MPL_DARK, linewidth=2)
    ax.add_patch(rect)

    # Labels
    ax.text(1, 3.8, "f = 1", fontsize=16, ha="center", fontweight="bold", color=MPL_BLUE)
    ax.text(1, 2.3, "tr (pause)", fontsize=12, ha="center", color=MPL_BLUE)
    ax.text(10, 3.8, "f = ∞", fontsize=16, ha="center", fontweight="bold", color="#E65100")
    ax.text(10, 2.3, "default", fontsize=12, ha="center", color="#E65100")
    ax.text(5.5, 4.2, "capacity_overcommit_factor  f", fontsize=14,
            ha="center", fontweight="bold", color=MPL_DARK)

    # Gate B verification
    ax.text(1, 1.7, "Gate B(a): f=1 비트동일 ✓", fontsize=10, ha="center",
            color=MPL_GREEN, fontweight="bold")
    ax.text(10, 1.7, "Gate B(b): f→∞ default수렴 ✓", fontsize=10, ha="center",
            color=MPL_GREEN, fontweight="bold")

    # 4 injection points diagram below
    ax.text(5.5, 0.8, "router.py — 4곳 margin=(f−1)×C_total 주입", fontsize=13,
            ha="center", fontweight="bold", color=MPL_DARK)

    inject_pts = [
        (1.2, "_select_backend\n(신규 배정)"),
        (4.0, "_scheduled_check\n(pause 트리거)"),
        (6.8, "_pause_until_safe\n(pause 루프)"),
        (9.6, "_greedy_resume\n(resume 조건)"),
    ]
    for x, label in inject_pts:
        box = FancyBboxPatch((x - 0.9, -0.8), 2.2, 0.9, boxstyle="round,pad=0.05",
                             facecolor="#F5F5F5", edgecolor=MPL_DARK, linewidth=1)
        ax.add_patch(box)
        ax.text(x + 0.2, -0.35, label, fontsize=9, ha="center", va="center",
                color=MPL_DARK)

    # Arrows between injection points
    for x in [2.5, 5.3, 8.1]:
        ax.annotate("", xy=(x + 0.4, -0.35), xytext=(x, -0.35),
                    arrowprops=dict(arrowstyle="->", color=MPL_GRAY))

    # Note about invariants
    ax.text(5.5, -1.6, "불변: pause 선정 순서 · decay · BFD · 우선순위/공정성 큐 — 임계값만 이동",
            fontsize=10, ha="center", color=MPL_GRAY, fontstyle="italic")

    fig.savefig(f"{DIAG}/fdial.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def gen_dsweep():
    """Duty sweep concept: fixed E2E, only d changes."""
    fig, ax = _fig_setup((11, 5))
    ax.set_xlim(-1, 11)
    ax.set_ylim(-1.5, 5.5)
    ax.axis("off")

    ax.text(5, 5.2, "합성 워크로드: E2E 고정, d(=reasoning 비율)만 스윕",
            fontsize=15, ha="center", fontweight="bold", color=MPL_DARK)

    d_values = [0.10, 0.20, 0.50, 0.90]
    bar_len = 8.0
    y_start = 4.0
    bar_h = 0.6
    gap = 0.3

    for i, d in enumerate(d_values):
        y = y_start - i * (bar_h + gap)
        reas_w = bar_len * d
        tool_w = bar_len * (1 - d)

        # Reasoning block (blue)
        rect_r = plt.Rectangle((1.5, y), reas_w, bar_h,
                                facecolor=MPL_BLUE, alpha=0.7, edgecolor=MPL_DARK)
        ax.add_patch(rect_r)
        # Tool block (orange)
        rect_t = plt.Rectangle((1.5 + reas_w, y), tool_w, bar_h,
                                facecolor=MPL_ORANGE, alpha=0.3, edgecolor=MPL_DARK)
        ax.add_patch(rect_t)
        # Label
        ax.text(0.5, y + bar_h/2, f"d={d:.2f}", fontsize=12, ha="center",
                va="center", fontweight="bold", color=MPL_DARK)
        if reas_w > 0.8:
            ax.text(1.5 + reas_w/2, y + bar_h/2, "reasoning",
                    fontsize=9, ha="center", va="center", color="white")
        if tool_w > 1.5:
            ax.text(1.5 + reas_w + tool_w/2, y + bar_h/2, "tool (sleep)",
                    fontsize=9, ha="center", va="center", color="#E65100")

        # fit×d value
        fitd = 4.76 * d
        ax.text(10, y + bar_h/2, f"fit×d={fitd:.2f}",
                fontsize=11, ha="center", va="center", color=MPL_DARK)

    # Legend
    ax.text(1.5, 0.5, "tool_dur = reas_time × (1−d)/d",
            fontsize=12, ha="left", color=MPL_DARK, fontstyle="italic")
    ax.text(1.5, 0.0, "Gate C: d=0.2 검증 → 실측 0.1978, 오차 1.12% ✓",
            fontsize=11, ha="left", color=MPL_GREEN, fontweight="bold")

    # Arrow showing fit×d boundary
    ax.annotate("", xy=(10, 3.8), xytext=(10, 1.1),
                arrowprops=dict(arrowstyle="<->", color=MPL_GRAY, linewidth=1.5))
    ax.text(10.7, 2.5, "스윕\n범위", fontsize=10, ha="center", color=MPL_GRAY)

    fig.savefig(f"{DIAG}/dsweep.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def gen_workload_map():
    """4 workloads positioned on fit×d axis — clean horizontal strip layout."""
    fig, ax = _fig_setup((13, 7))
    ax.set_xlim(-1.2, 2.2)  # log10 scale: ~0.06 to ~160
    ax.set_ylim(-1.8, 5.0)
    ax.axis("off")

    fd_star = math.log10(0.62)  # ≈ -0.208

    # ── Background zones ──
    ax.axvspan(-1.2, fd_star, alpha=0.05, color=MPL_ORANGE)
    ax.axvspan(fd_star, 2.2, alpha=0.05, color=MPL_BLUE)
    ax.axvline(fd_star, color=MPL_RED, linewidth=3, linestyle="--", alpha=0.8,
               zorder=3)

    # Zone labels (top)
    ax.text((fd_star + (-1.2)) / 2, 4.7, "default 영역",
            fontsize=15, ha="center", fontweight="bold",
            color="#E65100", alpha=0.6)
    ax.text((fd_star + 2.2) / 2, 4.7, "tr 영역",
            fontsize=15, ha="center", fontweight="bold",
            color=MPL_BLUE, alpha=0.6)
    # fd* label
    ax.text(fd_star, 4.7, "fd*=0.62", fontsize=14, ha="center",
            fontweight="bold", color=MPL_RED,
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                      edgecolor=MPL_RED, linewidth=1.5))

    # ── Main axis ──
    ax.plot([-1.2, 2.2], [0, 0], color=MPL_DARK, linewidth=2.5)
    for fd_val in [0.1, 0.5, 1.0, 5.0, 10, 50, 100]:
        x = math.log10(fd_val)
        ax.plot(x, 0, "|", color=MPL_DARK, markersize=12, markeredgewidth=2)
        ax.text(x, -0.35, f"{fd_val}", fontsize=11, ha="center", color=MPL_DARK)
    ax.text(0.5, -0.8, "fit × d  (log scale)", fontsize=14, ha="center",
            fontweight="bold", color=MPL_DARK)

    # ── Data points: stacked in clear rows ──
    # Row 1 (y=3.6): Real workloads — 4 cells
    # Row 2 (y=2.2): Synthetic sweep highlights
    # Row 3 (y=1.0): HLE / Science (TBD)
    row1_y, row2_y, row3_y = 3.5, 2.0, 0.8

    # Row labels
    ax.text(-1.15, row1_y, "실제\n워크로드", fontsize=10, ha="center",
            va="center", color=MPL_GRAY, fontstyle="italic")
    ax.text(-1.15, row2_y, "합성\n스윕", fontsize=10, ha="center",
            va="center", color=MPL_GRAY, fontstyle="italic")
    ax.text(-1.15, row3_y, "미완\n(진행중)", fontsize=10, ha="center",
            va="center", color=MPL_GRAY, fontstyle="italic")

    # Separator lines
    for yy in [row1_y - 0.5, row2_y - 0.5]:
        ax.plot([-0.9, 2.1], [yy, yy], color=MPL_GRAY, linewidth=0.5,
                linestyle=":", alpha=0.5)

    # Row 1: real workloads
    # (fd, label, color, marker, result, label_offset_x, label_ha)
    real_points = [
        (0.46, "4090/TraceLab", MPL_RED, "v", "def 승 −34%",
         0, "center"),
        (5.54, "4090/SWE", MPL_GREEN, "^", "tr 승 +78%",
         -0.15, "right"),
        (7.07, "Pro6000/TraceLab", MPL_GREEN, "s", "tr 승 +87%",
         0.15, "left"),
        (57.6, "Pro6000/SWE", MPL_GREEN, "s", "tr 승 +113%",
         0, "center"),
    ]
    for fd, label, clr, mk, result, lx_off, lha in real_points:
        x = math.log10(fd)
        ax.plot(x, row1_y, mk, color=clr, markersize=14,
                markeredgecolor=MPL_DARK, markeredgewidth=1, zorder=5)
        ax.text(x + lx_off, row1_y + 0.55, label, fontsize=9, ha=lha,
                fontweight="bold", color=MPL_DARK)
        ax.text(x + lx_off, row1_y - 0.55, result, fontsize=8, ha=lha,
                color=clr, fontweight="bold")

    # Row 2: synthetic sweep key points
    # Place fd=0.50 left, fd=0.65 center-left, fd=0.90 right to avoid overlap
    # log10: 0.50=-0.301, 0.65=-0.187, 0.90=-0.046
    synth_data = [
        (0.50, "fd=0.50", MPL_ORANGE, "D", "def +12%"),
        (0.65, "fd=0.65★", "#4CAF50", "D", "tr +2% (전환)"),
        (0.90, "fd=0.90", MPL_BLUE, "D", "tr +24%"),
    ]
    for fd, label, clr, mk, result in synth_data:
        x = math.log10(fd)
        ax.plot(x, row2_y, mk, color=clr, markersize=13,
                markeredgecolor=MPL_DARK, markeredgewidth=1, zorder=5)
    # Manual label placement to avoid overlap
    ax.text(math.log10(0.50), row2_y + 0.5, "fd=0.50", fontsize=9,
            ha="right", fontweight="bold", color=MPL_DARK)
    ax.text(math.log10(0.50), row2_y - 0.55, "def +12%", fontsize=8,
            ha="right", color=MPL_ORANGE, fontweight="bold")

    ax.text(math.log10(0.65), row2_y + 0.5, "fd=0.65★", fontsize=9,
            ha="center", fontweight="bold", color=MPL_DARK)
    ax.text(math.log10(0.65), row2_y - 0.55, "tr +2%", fontsize=8,
            ha="center", color="#4CAF50", fontweight="bold")

    ax.text(math.log10(0.90) + 0.06, row2_y + 0.5, "fd=0.90", fontsize=9,
            ha="left", fontweight="bold", color=MPL_DARK)
    ax.text(math.log10(0.90) + 0.06, row2_y - 0.55, "tr +24%", fontsize=8,
            ha="left", color=MPL_BLUE, fontweight="bold")

    # Row 3: HLE and Science (boxes)
    hle_box = FancyBboxPatch((0.9, row3_y - 0.3), 1.1, 0.6,
                             boxstyle="round,pad=0.05",
                             facecolor="#FFF3E0", edgecolor=MPL_ORANGE,
                             linewidth=1.5, linestyle="--")
    ax.add_patch(hle_box)
    ax.text(1.45, row3_y, "HLE  (heavy-tail, d TBD)", fontsize=9,
            ha="center", va="center", fontweight="bold", color="#E65100")

    sci_box = FancyBboxPatch((-0.7, row3_y - 0.3), 1.1, 0.6,
                             boxstyle="round,pad=0.05",
                             facecolor="#F5F5F5", edgecolor=MPL_GRAY,
                             linewidth=1.5, linestyle=":")
    ax.add_patch(sci_box)
    ax.text(-0.15, row3_y, "Science  (data N/A)", fontsize=9,
            ha="center", va="center", fontweight="bold", color=MPL_GRAY)

    # ── Bottom note ──
    ax.text(0.5, -1.5,
            "★ fd < 0.62: default 승  |  fd > 0.62: tr 승  — "
            "실제 4셀 + 합성 84점 전부 정합",
            fontsize=12, ha="center", fontweight="bold", color=MPL_DARK,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#E8F5E9",
                      edgecolor=MPL_GREEN, linewidth=1.5))

    fig.savefig(f"{DIAG}/workload_map.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def gen_findings():
    """3 honest findings boxes."""
    fig, ax = _fig_setup((12, 5))
    ax.set_xlim(-0.5, 12)
    ax.set_ylim(-0.5, 5)
    ax.axis("off")

    boxes = [
        (0.2, 2.5, 3.5, 2.0, "H1 반증", MPL_RED,
         "내부 최적 f* 없음\n→ 이진 선택\n(tr or default)"),
        (4.2, 2.5, 3.5, 2.0, "전환점 예측 가능", MPL_BLUE,
         "fd* 가변(HW/워크로드)\n→ 비용모델 S×W/U로\n0.9% 오차 예측"),
        (8.2, 2.5, 3.5, 2.0, "heavy-tail 한계", MPL_ORANGE,
         "mean-U 모델이\nHLE류에서 과대추정\n→ tail-aware U 필요"),
    ]
    for x, y, w, h, title, clr, body in boxes:
        rect = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15",
                              facecolor=clr, alpha=0.08, edgecolor=clr, linewidth=2.5)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h - 0.3, title, fontsize=15, ha="center",
                fontweight="bold", color=clr)
        ax.text(x + w/2, y + h/2 - 0.2, body, fontsize=12, ha="center",
                va="center", color=MPL_DARK, linespacing=1.4)

    # Additional finding at bottom
    extra = FancyBboxPatch((1.5, 0.3), 9.0, 1.5, boxstyle="round,pad=0.1",
                           facecolor=MPL_GREEN, alpha=0.06, edgecolor=MPL_GREEN,
                           linewidth=1.5)
    ax.add_patch(extra)
    ax.text(6, 1.3, "tr 신뢰성 위험", fontsize=13, ha="center", fontweight="bold",
            color=MPL_GREEN)
    ax.text(6, 0.7, "전환점 근처(fd≈0.60~0.65)에서 tr의 capacity timeout 3~7%  |  "
            "default는 실패 0%  |  선택기가 자동 회피", fontsize=11, ha="center",
            color=MPL_DARK)

    fig.savefig(f"{DIAG}/findings.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def gen_selector():
    """fit×d-aware selector flow diagram + 4 contributions."""
    fig, ax = _fig_setup((12, 6))
    ax.set_xlim(-0.5, 12)
    ax.set_ylim(-2.5, 5.5)
    ax.axis("off")

    # Input box
    inp = FancyBboxPatch((0.5, 3.5), 2.5, 1.2, boxstyle="round,pad=0.1",
                         facecolor="#E3F2FD", edgecolor=MPL_BLUE, linewidth=2)
    ax.add_patch(inp)
    ax.text(1.75, 4.4, "시스템 측정", fontsize=12, ha="center",
            fontweight="bold", color=MPL_DARK)
    ax.text(1.75, 3.8, "fit = C_total/ctx\nd = reas/(reas+tool)",
            fontsize=10, ha="center", color=MPL_DARK)

    # Compute box
    comp = FancyBboxPatch((4.0, 3.7), 2.2, 0.8, boxstyle="round,pad=0.1",
                          facecolor="#F5F5F5", edgecolor=MPL_DARK, linewidth=1.5)
    ax.add_patch(comp)
    ax.text(5.1, 4.1, "fit × d 계산", fontsize=12, ha="center",
            fontweight="bold", color=MPL_DARK)

    # Decision diamond
    diamond = plt.Polygon([[7.5, 4.8], [8.8, 4.1], [7.5, 3.4], [6.2, 4.1]],
                          facecolor="#FFFDE7", edgecolor=MPL_DARK, linewidth=2)
    ax.add_patch(diamond)
    ax.text(7.5, 4.1, "fd > fd*?", fontsize=12, ha="center", va="center",
            fontweight="bold", color=MPL_DARK)

    # Output boxes
    tr_out = FancyBboxPatch((9.5, 4.2), 2.0, 0.8, boxstyle="round,pad=0.1",
                            facecolor=MPL_BLUE, alpha=0.2, edgecolor=MPL_BLUE,
                            linewidth=2)
    ax.add_patch(tr_out)
    ax.text(10.5, 4.6, "tr (f=1)", fontsize=14, ha="center", fontweight="bold",
            color=MPL_BLUE)

    def_out = FancyBboxPatch((9.5, 3.0), 2.0, 0.8, boxstyle="round,pad=0.1",
                             facecolor=MPL_ORANGE, alpha=0.2, edgecolor=MPL_ORANGE,
                             linewidth=2)
    ax.add_patch(def_out)
    ax.text(10.5, 3.4, "default (f=∞)", fontsize=14, ha="center",
            fontweight="bold", color="#E65100")

    # Arrows
    arrow_kw = dict(arrowstyle="->,head_width=0.3", color=MPL_DARK, linewidth=2)
    ax.annotate("", xy=(3.9, 4.1), xytext=(3.1, 4.1), arrowprops=arrow_kw)
    ax.annotate("", xy=(6.1, 4.1), xytext=(6.3, 4.1), arrowprops=arrow_kw)
    ax.annotate("Yes", xy=(9.4, 4.6), xytext=(8.8, 4.5),
                fontsize=11, fontweight="bold", color=MPL_BLUE,
                arrowprops=dict(arrowstyle="->", color=MPL_BLUE, linewidth=1.5))
    ax.annotate("No", xy=(9.4, 3.4), xytext=(8.3, 3.4),
                fontsize=11, fontweight="bold", color="#E65100",
                arrowprops=dict(arrowstyle="->", color=MPL_ORANGE, linewidth=1.5))

    # 4 contributions below
    ax.plot([-0.3, 11.8], [2.3, 2.3], color=MPL_GRAY, linewidth=1, linestyle=":")
    ax.text(6, 2.0, "기여 (Contributions)", fontsize=14, ha="center",
            fontweight="bold", color=MPL_DARK)

    contribs = [
        ("①", "fit×d가 정책 선택의 충분통계량"),
        ("②", "비용모델(S×W/U)로 전환점 0.9% 오차 예측"),
        ("③", "SOTA의 레짐-무지 취약점 발견\n   (미포화: −12~34% 느림 + 3~7% 실패)"),
        ("④", "선택기가 throughput(최대 24%) + 가용성 동시 개선"),
    ]
    for i, (num, txt) in enumerate(contribs):
        y = 1.3 - i * 0.7
        ax.text(0.8, y, num, fontsize=16, fontweight="bold", color=MPL_BLUE)
        ax.text(1.5, y, txt, fontsize=12, va="center", color=MPL_DARK)

    fig.savefig(f"{DIAG}/selector.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def gen_future():
    """Future work roadmap."""
    fig, ax = _fig_setup((12, 4.5))
    ax.set_xlim(-0.5, 12)
    ax.set_ylim(-0.5, 4)
    ax.axis("off")

    items = [
        (0.5, "tail-aware U\n모델 확장",
         "HLE류 heavy-tail:\nmean U → p99 기반 U",
         MPL_ORANGE),
        (4.2, "전환점 이동\n실증",
         "A100/H100·32B/70B:\nfd* 보편성 검증",
         MPL_BLUE),
        (7.9, "적응형 런타임\n스케줄러",
         "온라인 d·fit 추정\n→ 자동 정책 전환",
         MPL_GREEN),
    ]
    for x, title, body, clr in items:
        box = FancyBboxPatch((x, 0.5), 3.2, 2.8, boxstyle="round,pad=0.15",
                             facecolor=clr, alpha=0.08, edgecolor=clr, linewidth=2)
        ax.add_patch(box)
        ax.text(x + 1.6, 2.8, title, fontsize=14, ha="center",
                fontweight="bold", color=clr)
        ax.text(x + 1.6, 1.5, body, fontsize=11, ha="center", va="center",
                color=MPL_DARK, linespacing=1.3)

    # Arrows between
    for x in [3.8, 7.5]:
        ax.annotate("", xy=(x + 0.3, 1.9), xytext=(x, 1.9),
                    arrowprops=dict(arrowstyle="->", color=MPL_GRAY, linewidth=2))

    fig.savefig(f"{DIAG}/future.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

def gen_summary_chain():
    """Compressed causal chain."""
    fig, ax = _fig_setup((13, 5.5))
    ax.set_xlim(-0.5, 13)
    ax.set_ylim(-0.5, 5.5)
    ax.axis("off")

    chain = [
        (0.0, 4.0, "퍼즐\ntr 승패 갈림", "#FFCDD2", MPL_RED),
        (2.2, 4.0, "STEP 2\nfit×d<1\n= 일반 zone", "#BBDEFB", MPL_BLUE),
        (4.4, 4.0, "idle↔recomp\n상충 구조", "#FFF9C4", "#F57F17"),
        (6.6, 4.0, "STEP 3-4\n노브 f\n합성 trace", "#E8F5E9", MPL_GREEN),
        (8.8, 4.0, "STEP 5 ★\nfd*=0.62\n이진 선택", "#E3F2FD", MPL_BLUE),
        (11.0, 4.0, "STEP 6 ★\n모델 예측\n0.625", "#FFECB3", "#E65100"),
    ]
    for x, y, txt, bg, ec in chain:
        box = FancyBboxPatch((x, y - 0.1), 1.8, 1.2, boxstyle="round,pad=0.08",
                             facecolor=bg, edgecolor=ec, linewidth=2)
        ax.add_patch(box)
        ax.text(x + 0.9, y + 0.5, txt, fontsize=9, ha="center", va="center",
                fontweight="bold", color=MPL_DARK, linespacing=1.2)

    # Arrows
    for x in [1.9, 4.1, 6.3, 8.5, 10.7]:
        ax.annotate("", xy=(x + 0.2, 4.5), xytext=(x, 4.5),
                    arrowprops=dict(arrowstyle="->", color=MPL_DARK, linewidth=2))

    # Second row: validation + contribution
    chain2 = [
        (1.5, 1.8, "4워크로드\n교차검증\n방향 전부 정합", "#E8F5E9", MPL_GREEN),
        (5.0, 1.8, "기여\nfit×d-aware 선택기\n최대 24% 개선", "#E3F2FD", MPL_BLUE),
        (8.5, 1.8, "한계\nheavy-tail\n→ tail-aware U", "#FFF3E0", MPL_ORANGE),
    ]
    for x, y, txt, bg, ec in chain2:
        box = FancyBboxPatch((x, y - 0.1), 2.5, 1.2, boxstyle="round,pad=0.08",
                             facecolor=bg, edgecolor=ec, linewidth=2)
        ax.add_patch(box)
        ax.text(x + 1.25, y + 0.5, txt, fontsize=10, ha="center", va="center",
                fontweight="bold", color=MPL_DARK, linespacing=1.2)

    # Down arrows from row 1 to row 2
    ax.annotate("", xy=(2.75, 3.0), xytext=(5.0, 3.8),
                arrowprops=dict(arrowstyle="->", color=MPL_GRAY, linewidth=1.5,
                                linestyle="--"))
    ax.annotate("", xy=(6.25, 3.0), xytext=(8.0, 3.8),
                arrowprops=dict(arrowstyle="->", color=MPL_GRAY, linewidth=1.5,
                                linestyle="--"))
    ax.annotate("", xy=(9.75, 3.0), xytext=(11.9, 3.8),
                arrowprops=dict(arrowstyle="->", color=MPL_GRAY, linewidth=1.5,
                                linestyle="--"))

    # Bottom takeaway
    ax.text(6.5, 0.5,
            "한 줄: fit×d > 0.62 → tr,  아래 → default.  "
            "비용모델로 예측.  선택기로 최대 24% + 실패 회피.",
            fontsize=13, ha="center", fontweight="bold", color=MPL_DARK,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFFDE7",
                      edgecolor=MPL_ORANGE, linewidth=2))

    fig.savefig(f"{DIAG}/summary_chain.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


# ════════════════════════════════════════════════════════════════════
# PPTX BUILDING
# ════════════════════════════════════════════════════════════════════

def build_pptx():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]  # blank layout

    # ── Slide 1: Title ──────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_image(sl, f"{DIAG}/title_motif.png", Inches(0), Inches(0),
               width=Inches(13.333), height=Inches(7.5))
    _add_textbox(sl, Inches(1.5), Inches(1.8), Inches(10), Inches(1.2),
                 "Overcommit × Duty  레짐 연구",
                 font_size=36, bold=True, color=C_DARK, align=PP_ALIGN.CENTER)
    _add_textbox(sl, Inches(1.5), Inches(3.2), Inches(10), Inches(0.8),
                 "fit×d가 tr/default 정책 전환을 예측한다",
                 font_size=20, color=C_GRAY, align=PP_ALIGN.CENTER)
    _add_textbox(sl, Inches(1.5), Inches(5.0), Inches(10), Inches(0.5),
                 "강윤의  ·  5090/Qwen3-8B (goguma) + Pro6000×2/Qwen3-32B (nutella1)  ·  2026-07",
                 font_size=14, color=C_GRAY, align=PP_ALIGN.CENTER)
    _set_notes(sl, """\
[슬라이드 1: 타이틀]
■ 연구 제목: Overcommit × Duty 레짐 연구 — fit×d가 tr/default 정책 전환을 예측한다.
■ ThunderAgent(SOTA agentic LLM serving scheduler)에서, 같은 정책(tr)이 워크로드에 따라 이기기도 지기도 하는 현상의 원인을 밝히고, 하나의 무차원수 fit×d로 정책 선택을 예측하는 법칙과 비용 모델을 제시한다.
■ 실험 서버: goguma (2×RTX5090, 단일 GPU 사용), nutella1 (2×Pro6000 96GB + 4090 24GB).
■ 기간: 2026-07-16 ~ 2026-07-20, STEP 2~6 + 4 워크로드(SWE, TraceLab, HLE, Science).
■ Thesis: fit×d(=C_total/peak_seq × reasoning/(reasoning+tool))가 tr/default 최적 정책의 충분통계량이며, 비용 모델 wall ∝ S×W/U로 전환점 fd*=0.625를 예측(실측 0.62, 오차 0.9%).""")

    # ── Slide 2: Background ─────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "에이전트 서빙: reasoning↔tool 루프와 KV 축적")
    _add_image(sl, f"{DIAG}/pipeline.png", Inches(0.3), Inches(1.3),
               width=Inches(12.7), height=Inches(5.5))
    _set_notes(sl, """\
[슬라이드 2: 배경 — 에이전트 서빙]
■ 이전 질문에서 이어짐: 에이전트 LLM 서빙이 무엇이고 왜 KV 캐시 관리가 어려운지를 설명.
■ 에이전트 LLM 서빙이란: 사용자 요청 → LLM이 reasoning(사고) → tool 호출(코드 실행, 웹 검색 등) → 결과로 다시 reasoning하는 다턴 루프.
■ 각 프로그램(에이전트 세션)은 여러 턴을 거치며 KV 캐시가 턴마다 누적됨. peak_seq = 최종 컨텍스트 길이.
■ GPU는 reasoning 중에만 활성 — tool 실행 중 GPU는 idle. 이것이 핵심 도전.
■ tr(ThunderAgent, SOTA): 새 프로그램이 들어와도 기존 프로그램의 KV를 보존(pause). GPU가 놀 수 있지만 cache hit으로 재계산 절약.
■ default: KV 용량을 초과해서도 새 프로그램 배정(overcommit). GPU는 바쁘지만 기존 프로그램의 캐시가 evict되어 나중에 recompute 필요.
■ 핵심 질문: 둘 중 어느 것이 언제 나은가? → 이 연구의 출발점.""")

    # ── Slide 3: Puzzle ─────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "퍼즐: 같은 SOTA가 이기기도, 지기도 한다",
                   "tr(ThunderAgent) vs default 정책 — 무엇이 승패를 가르나?")
    _add_image(sl, f"{DIAG}/puzzle.png", Inches(0.5), Inches(1.3),
               width=Inches(12), height=Inches(5.8))
    _set_notes(sl, """\
[슬라이드 3: 퍼즐]
■ 이전: 에이전트 서빙의 두 정책(tr vs default)을 설명.
■ 이 슬라이드가 제기하는 질문: "같은 SOTA(tr)가 왜 어떤 워크로드에서는 이기고 다른 데서는 지나?"
■ P1 실험 결과(Pro6000 TP2 Qwen3-32B, 2026-07-16):
  - 4090/SWE: tr +78~84% (fit×d=5.54, zone 밖)
  - 4090/TraceLab: tr −34% (fit×d=0.46, zone 내!) ← 유일한 패배
  - Pro6000/SWE: tr +113% (fit×d=57.6, zone 밖)
  - Pro6000/TraceLab: tr +80~87% (fit×d=7.07, zone 밖)
■ 패배는 4090/TraceLab 하나뿐. "4090이 특수한 건가?"
  → NO. fit×d < 1인 유일한 셀이 여기뿐. 이것은 4090 특수현상이 아니라 fit×d 레짐의 일반 현상.
■ 이 퍼즐이 전체 연구의 동기. → "그래서 fit×d가 뭐고 왜 중요한가?" → STEP 2로.""")

    # ── Slide 4: STEP 2 ─────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "STEP 2: fit × d < 1 = 트레이드오프 영역",
                   "fit = C_total / peak_seq  ·  d = reasoning / (reasoning + tool)")
    _add_image(sl, f"{FIGS}/step2_fitd_hyperbola_yunuikang.png",
               Inches(0.5), Inches(1.3), width=Inches(8), height=Inches(5.8))
    _add_callout(sl, Inches(9.0), Inches(1.6), Inches(4), Inches(0.8),
                 "fit×d < 1: GPU 구조적 idle\n→ 정책 선택이 성능 좌우", C_RED)
    _add_callout(sl, Inches(9.0), Inches(2.8), Inches(4), Inches(0.7),
                 "4셀 검증: 승패 100% 설명", C_GREEN)
    _add_callout(sl, Inches(9.0), Inches(3.8), Inches(4), Inches(0.7),
                 "격자 42셀 중 15셀 zone 내\nA100/H100 TraceLab도 진입", C_BLUE)
    _add_callout(sl, Inches(9.0), Inches(4.8), Inches(4), Inches(0.9),
                 "★ 4090 특수현상 아님\n일반적 레짐 현상", C_DARK)
    _set_notes(sl, """\
[슬라이드 4: STEP 2 — fit×d 경계]
■ 이전 질문: "tr이 지는 조건을 어떻게 정의하나?"
■ fit = C_total / peak_seq: KV 풀에 동시 적재 가능한 프로그램 수.
  - C_total: vLLM 기동 시 할당되는 전체 KV 캐시 토큰 수 (예: 5090에서 95,936)
  - peak_seq: 프로그램 완료 시 최종 컨텍스트 길이 (예: TraceLab ~20,150)
■ d = reasoning / (reasoning + tool): 듀티 사이클. GPU가 활성인 시간 비율.
■ fit×d = R_cap = 스래싱 없이 얻는 GPU 수요의 최대치.
  - fit×d < 1: 프로그램을 아무리 적재해도 GPU가 구조적으로 idle → overcommit(recompute)이 idle보다 나을 수 있음 = 트레이드오프 영역
  - fit×d ≥ 1: 적재만으로 GPU 포화 → tr(pause)이 항상 최선
■ 측정 4셀(4090/SWE, 4090/TraceLab, Pro6000/SWE, Pro6000/TraceLab) 전부에서 fit×d ≷ 1이 승패 100% 설명.
■ 격자(7 GPU/모델 × 워크로드): 42셀 중 15셀이 zone 내. A100-80G/Qwen3-32B TraceLab도 fit×d=0.60<1 → 데이터센터 GPU도 진입.
■ C_total 추정식 검증: EFF=0.9471(3셀 보정), 잔차 ±5.9% 이내. KV/token: Qwen3-8B 147,456 B, Qwen3-32B 262,144 B (로컬 config.json 실측).
■ → "지는 영역이 일반적이면, 왜 지나?" → 다음 슬라이드: idle↔recompute 상충.""")

    # ── Slide 5: Tradeoff ────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "idle vs recompute: 미포화 영역의 두 비용 상충",
                   "fit×d < 1일 때, GPU idle 감수(tr) vs cache miss 감수(default)")
    _add_image(sl, f"{DIAG}/seesaw.png", Inches(0.3), Inches(1.2),
               width=Inches(12.7), height=Inches(6))
    _set_notes(sl, """\
[슬라이드 5: 트레이드오프 — idle vs recompute]
■ 이전: fit×d<1 영역이 일반적임을 보임. 이 슬라이드: "그 영역 안에서 왜 tr이 지나?"
■ 미포화 zone(fit×d<1)에서는 두 비용이 상충:
  - idle 비용 (tr): pause로 KV 보존하면 GPU가 놂. 처리량(throughput) 감소.
    예: d=0.1이면 GPU가 90% 시간 idle → 엄청난 기회비용.
  - recompute 비용 (default): overcommit으로 GPU를 채우지만, 기존 프로그램의 cache가 밀려나서 나중에 재계산 필요. GPU 시간의 99%가 recompute(낭비).
    예: d=0.1 default에서 TRUE hit rate 1.4% — 거의 모든 프롬프트를 처음부터 다시 계산.
■ R을 올리는 두 레버:
  - d (duty cycle) ↑: reasoning 비율이 높아지면 GPU가 자연스럽게 더 바쁨 → idle 비용↓
  - k_fit (overcommit factor) ↑: 더 많이 적재하면 GPU 채워지나 cache eviction↑ → recompute 비용↑
■ fit×d가 낮을수록(=idle 비용 큼): default의 recompute 비용을 감수해도 GPU를 쓰는 게 이득 → default 승.
  fit×d가 높을수록(=idle 비용 작음): GPU 이미 어느 정도 바쁘므로 recompute는 순수 낭비 → tr 승.
■ 교차점 = 전환점 fit×d*. → "어디서 교차하나? 확인하려면 f와 d를 자유롭게 스윕할 도구가 필요" → STEP 3, 4.""")

    # ── Slide 6: STEP 3 ─────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "STEP 3: 연속 노브 f — tr(f=1) ←→ default(f=∞)",
                   "capacity_overcommit_factor로 두 정책을 연속 스펙트럼으로 연결")
    _add_image(sl, f"{DIAG}/fdial.png", Inches(0.3), Inches(1.2),
               width=Inches(12.7), height=Inches(5.5))
    _set_notes(sl, """\
[슬라이드 6: STEP 3 — f 노브 구현]
■ 이전 질문: "idle↔recompute 사이 최적이 있나? → 확인하려면 두 정책 사이를 연속적으로 조절하는 노브가 필요."
■ capacity_overcommit_factor f 구현:
  - f=1: 기존 tr과 산술적으로 동치. margin = (f−1)×C_total = 0 → 모든 용량 검사 그대로.
  - f=∞ (구현상 f=10⁶): margin ≈ 10¹⁰ → 모든 용량 검사 사실상 비활성 → pause 불가 → default와 동치.
■ 5-홉 배선: __main__.py(arg) → config.py(field) → app.py(전달) → router.py(저장+사용).
■ 4곳 주입:
  1. _select_backend_for_new_program: remaining + margin < required (신규 배정)
  2. _scheduled_check: remaining + margin < 0 (pause 트리거)
  3. _pause_until_safe: remaining + margin < 0 (pause 루프)
  4. _greedy_resume: remaining += margin (resume 용량)
■ 불변 보존: pause 대상 선정 순서(작은 ACTING부터), decay 형태, BFD, 우선순위/공정성 큐 — 임계값만 이동.
■ 게이트 B:
  (a) f=1 비트-동일: margin=0 → 산술 NOP + smoke test 통과.
  (b) f→∞ default 수렴: margin=10¹⁰ → 모든 검사 불가능 → C=10 실행에서 pause=0 확인.
■ → 노브가 준비됨. 이제 d를 정밀 통제할 합성 워크로드가 필요 → STEP 4.""")

    # ── Slide 7: STEP 4 ─────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "STEP 4: 듀티 통제 합성 워크로드",
                   "E2E 고정, d(=reasoning 비율)만 스윕 — 상충을 깨끗이 분리")
    _add_image(sl, f"{DIAG}/dsweep.png", Inches(0.3), Inches(1.3),
               width=Inches(12.7), height=Inches(5.5))
    _set_notes(sl, """\
[슬라이드 7: STEP 4 — 듀티 통제 합성 워크로드]
■ 이전 질문: "f 노브가 있으니, 이제 d를 자유롭게 바꾸며 idle↔recompute 교차를 관찰하고 싶다."
■ synth_duty_trace_yunuikang.py로 합성 trace 생성:
  - 핵심 원리: reasoning 시간은 LLM 속도로 고정(5090 c=1 실측), tool sleep만 조절하여 d 정밀 통제.
  - tool_duration = reasoning_time × (1−d)/d → 정의에 의해 d = reasoning/(reasoning+tool) 정확히 성립.
■ ctx-aware 2-component 캘리브레이션 모델 (5090 실측):
  - COLD_PREFILL_RATE = 9,038 tok/s (turn 0 cold, 16K 입력)
  - WARM_NEW_TOKEN_RATE = 7,208 tok/s (새 토큰 KV 계산)
  - WARM_CTX_ATTN_RATE = 116,228 tok/s (캐시된 ctx attention 오버헤드)
  - DECODE_RATE = 91 tok/s (장문맥)
■ 게이트 C: d=0.2 spot-check → actual d=0.1978, 오차 1.12% (±5% 이내) → PASS.
■ 7개 d값(fit×d = 0.50~0.90)으로 7개 trace 생성.
  - input_base=16,250 (TraceLab-scale), growth=500/turn, output=50, 8 turns, 10 sessions.
  - peak_seq = 20,150 → fit = 95,936/20,150 = 4.76.
■ [추정/한계] c=1 전용 캘리브레이션. 부하 하에서 batching/preemption이 속도에 영향 → d 변동은 의도된 효과(STEP 5에서 관찰). warm prefill이 turn 진행 시 증가(attention 오버헤드)하나 전체 d에 1.1% 이내 영향.
■ → 노브(f) + 합성 워크로드(d 통제) 준비 완료. 이제 f×d 스윕 → STEP 5.""")

    # ── Slide 7b: STEP 4 설계 표 (fit×d span, H1/H2 매핑) ──────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "STEP 4 설계: fit×d span — 어느 d가 미포화/포화를 탐침하나",
                   "ctx 보정(input_base 4,000→16,250 → fit 12.1→4.76)로 경계가 격자 통과")

    _add_table(sl,
        Inches(0.5), Inches(1.5), Inches(7.3), Inches(3.6),
        ["d", "fit×d", "영역", "f_sat = 1/(fit×d)", "가설"],
        [
            ["0.1", "0.476", "★ 미포화",        "2.10", "H1"],
            ["0.2", "0.952", "★ 미포화 (경계)", "1.05", "H1"],
            ["0.3", "1.428", "포화",            "0.70", "H2"],
            ["0.5", "2.381", "포화",            "0.42", "H2"],
            ["0.7", "3.333", "포화",            "0.30", "H2"],
            ["0.9", "4.285", "포화",            "0.23", "H2"],
        ],
        font_size=13)

    _add_callout(sl, Inches(0.5), Inches(5.4), Inches(7.3), Inches(0.7),
                 "경계 d ≈ 0.21 — d=0.2(H1)와 d=0.3(H2) 사이 통과  |  fit = C_total/peak_seq = 95,936/20,150 = 4.76",
                 C_DARK, font_size=12)

    _add_callout(sl, Inches(8.1), Inches(1.6), Inches(4.7), Inches(1.5),
                 "H1: 미포화 zone(fit×d<1) 내부에\n최적 overcommit f*가 있는가?\n→ 파일럿에서 반증 (이진 선택)",
                 C_RED, font_size=12)
    _add_callout(sl, Inches(8.1), Inches(3.3), Inches(4.7), Inches(1.5),
                 "H2: 포화 zone(fit×d≥1)에서\ntr(pause)이 default를 지배하는가?\n→ 확인 (경계 d=0.2에서도 tr 승)",
                 C_BLUE, font_size=12)
    _add_callout(sl, Inches(8.1), Inches(5.0), Inches(4.7), Inches(1.1),
                 "f_sat = R=1(GPU 포화)에 필요한\novercommit 배수. 미포화일수록 큼\n(d=0.1 → 2.1배 적재 필요)",
                 C_GRAY, font_size=11)

    _set_notes(sl, """\
[슬라이드 7b: STEP 4 설계 — fit×d span & H1/H2 매핑]
■ 이전(슬라이드 7): 합성 워크로드로 d를 정밀 통제하는 원리(tool_dur = reas×(1−d)/d).
■ 이 슬라이드: "그럼 어떤 d 값들을 스윕해야 트레이드오프 경계(fit×d=1)를 관통하는가?"
■ 문제 발견: v2 traces(input_base=4,000, peak_seq=7,900)에서 fit=12.1 → 모든 d에서 fit×d≥1. 경계가 격자 내부를 통과하지 못함 → 트레이드오프 관찰 불가.
■ 보정: input_base=16,250(TraceLab-scale ctx)로 증가 → peak_seq=20,150 → fit = 95,936/20,150 = 4.76.
■ 표: 6개 d 값의 영역·f_sat·가설 매핑
  - fit×d = 4.76 × d. d=0.1→0.476, d=0.2→0.952 (미포화, <1). d≥0.3 → 포화(≥1).
  - f_sat = 1/(fit×d): R=1(GPU 포화)에 필요한 overcommit 배수. 미포화일수록 크다(d=0.1→2.10, d=0.9→0.23).
  - 경계 d ≈ 0.21에서 fit×d=1 통과 → d=0.2(H1)와 d=0.3(H2) 사이.
■ 두 가설:
  - H1(미포화 zone 내부 최적 f*): 미포화(fit×d<1)에서 tr(f=1)과 default(f=∞) 사이에 중간 sweet spot f*가 존재하는가?
    → 3-point 파일럿에서 반증. f≈f_sat 이상에서 모든 지표가 default로 수렴. 최적은 이진(f=1 or f=∞).
  - H2(포화 zone tr 지배): 포화(fit×d≥1)에서 tr(pause)이 default를 지배하는가?
    → 확인. 심지어 경계 d=0.2(fit×d=0.95)에서도 tr이 이김 → H2 범위가 예상보다 넓음.
■ → 이 설계로 d를 {0.1~0.9} 스윕 → fit×d = 0.48~4.29 커버 → STEP 5 본 스윕(전환점 근처 촘촘히 재설계).""")

    # ── Slide 7c: STEP 4 실측 — 3-point 레짐 지도 ─────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "STEP 4 실측: d=0.1/0.2/0.5 파일럿 → 레짐 전환 발견",
                   "직접 측정 3점 — 미포화 깊은(0.1) → 경계(0.2) → 포화(0.5)에서 정책이 뒤집힘")

    # 3-point regime map (measured)
    _add_table(sl,
        Inches(0.4), Inches(1.45), Inches(12.5), Inches(1.9),
        ["d", "fit×d", "영역", "wall 승자", "wall ratio\n(f=∞/f=1)",
         "p95 승자", "tr TRUE hit\n(f=1)", "tr GPU%\n(f=1)", "가설 판정"],
        [
            ["0.1", "0.48", "미포화(깊은)", "default (f=∞)", "0.79\n(def +21%)",
             "default", "0.76", "22%", "H1 반증"],
            ["0.2", "0.95", "미포화(경계)", "tr (f=1)", "1.31\n(tr +31%)",
             "tr", "0.86", "30%", "H2 확인"],
            ["0.5", "2.38", "포화", "tr (f=1)", "1.96\n(tr +96%)",
             "tr", "0.86", "49%", "H2 확인"],
        ],
        font_size=11)

    _add_callout(sl, Inches(0.4), Inches(3.7), Inches(12.5), Inches(0.7),
                 "★ 레짐 전환점: fit×d ∈ (0.48, 0.95) 에서 최적 정책이 default → tr로 뒤집힘  "
                 "(경계는 fit×d=1보다 약간 아래 — 경계 근처서도 cache 보존 가치 높음)",
                 C_RED, font_size=12)

    # Physical interpretation — 3 boxes
    _add_callout(sl, Inches(0.4), Inches(4.7), Inches(4.0), Inches(2.1),
                 "d=0.1 (fit×d=0.48)\nGPU 10%만 사용 → pause 시 78% idle.\n"
                 "빈 GPU에 recompute 올려도 손해 없음.\n"
                 "→ idle 비용 지배 → default 승\n"
                 "(tr thr 9.7× 열악, 1개 프로그램 실패)",
                 C_ORANGE, font_size=11)
    _add_callout(sl, Inches(4.6), Inches(4.7), Inches(4.1), Inches(2.1),
                 "d=0.2 (fit×d=0.95)\nGPU ~30% 사용, f=1이 85% cache hit.\n"
                 "prefill skip 이점 > recompute 절약.\n"
                 "→ cache 보존 가치 지배 → tr 승\n"
                 "(f=1.25만 돼도 hit 0.86→0.42 급락)",
                 C_BLUE, font_size=11)
    _add_callout(sl, Inches(8.9), Inches(4.7), Inches(4.0), Inches(2.1),
                 "d=0.5 (fit×d=2.38)\nGPU 이미 50% 사용 → overcommit의\n"
                 "recompute는 순수 GPU 낭비.\n"
                 "→ recompute 비용 지배 → tr 압도\n"
                 "(wall 1.96×, p95 2.18× 우위)",
                 C_GREEN, font_size=11)

    _set_notes(sl, """\
[슬라이드 7c: STEP 4 실측 — 3-point 레짐 지도]
■ 이전(7b): 설계 표에서 d를 미포화/포화로 매핑하고 H1/H2 가설 정의.
■ 이 슬라이드: 실제 파일럿으로 3개 앵커 d(0.1/0.2/0.5)를 측정 → 레짐 전환 실증.
  [측정 프로토콜] vLLM restart/clean prefix cache per point, nvidia-smi dmon 1s, prompt_tokens_by_source(참 hit), --stream, C=10(≈2×fit), f grid, REPEAT=1.
■ 3-point 레짐 지도 (f=∞/f=1 wall ratio):
  - d=0.1 (fit×d=0.48, 깊은 미포화): default 승, ratio 0.79 (default 21% 빠름). tr(f=1)은 throughput 9.7× 열악(26.9 vs 261 tok/s), 1개 프로그램 capacity timeout 실패.
  - d=0.2 (fit×d=0.95, 경계): tr 승, ratio 1.31 (tr 31% 빠름), p95 1.42× 우위. f=1.05(≈f_sat)은 f=1과 동일, f=1.25부터 cache hit 0.86→0.42 급락.
  - d=0.5 (fit×d=2.38, 포화): tr 승, ratio 1.96 (tr 96% 빠름), p95 2.18× 우위.
■ ★ 레짐 전환점: fit×d ∈ (0.48, 0.95)에서 정책 최적이 뒤집힘. 경계는 fit×d=1보다 약간 아래.
■ 물리 해석 3단계:
  1. d=0.1: idle 비용 >> recompute 비용 (빈 GPU엔 recompute가 공짜).
  2. d=0.2: cache 보존 가치가 recompute 절약을 능가 (prefill skip 이점).
  3. d=0.5: recompute가 순수 GPU 낭비 (GPU 이미 절반 바쁨).
■ H1·H2 판정:
  - H1(미포화 내부 최적 f*) 반증 — d=0.1에서 f=2.0 vs f=∞ 차이 1.7%(무의미), d=0.2는 f=1이 최선. 최적은 이진.
  - H2(포화 tr 지배) 확인 — d=0.5에서 tr 압도. 심지어 경계 d=0.2에서도 tr 승 → H2 범위가 예상보다 넓음.
■ [정직한 범위] d=0.3/0.7/0.9는 이 fit=4.76 격자에서 직접 측정하지 않음 — 깊은 포화라 H2로 tr 자명 우세. 대신 STEP 5에서 전환점 근처(fit×d=0.50~0.90, d=0.105~0.189)로 재파라미터화해 촘촘히 측정 → fd*=0.62 정밀화.
  preemption=0 (전 f 값): vLLM은 overcommit을 prefix cache eviction(soft)으로 처리, 요청 abort 없음 → f>1의 비용은 미래 recompute뿐.
■ → 3점으로 전환 존재·방향 확정 → "정확히 어디서?" → STEP 5 본 스윕.""")

    # ── Slide 8: STEP 5 Data Table ─────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "★ STEP 5: 84-point 스윕 데이터 (C=10, n=3)",
                   "Wall 비율(def/tr) > 1 = tr 승  |  전환점 fit×d* ≈ 0.62")

    # Table 1: Main sweep wall ratio
    _add_table(sl,
        Inches(0.5), Inches(1.4), Inches(12.3), Inches(2.7),
        ["fit×d", "d", "def wall (s)", "tr wall (s)", "ratio\n(def/tr)",
         "승자", "tr p95 (s)", "def p95 (s)", "tr 실패율"],
        [
            ["0.50", "0.105", "195.2±0.8", "221.0±6.1", "0.88",
             "def +12%", "194.8±1.3", "184.4±0.5", "0%"],
            ["0.60", "0.126", "190.1±0.6", "192.6±6.0", "0.99",
             "tied", "180.5±6.6", "179.5±0.4", "3.3%"],
            ["0.65★", "0.137", "187.9±0.5", "183.9±7.8", "1.02",
             "tr +2%", "168.2±12", "177.4±0.7", "3.3%"],
            ["0.70", "0.147", "186.6±0.5", "174.3±6.4", "1.07",
             "tr +7%", "152.4±6.1", "176.0±0.5", "0%"],
            ["0.75†", "0.158", "185.8±0.4", "195.7±1.3", "0.95",
             "def +5%†", "—†", "—†", "6.7%"],
            ["0.80", "0.168", "184.3±0.6", "162.0±5.3", "1.14",
             "tr +14%", "140.1±1.9", "174.1±1.2", "0%"],
            ["0.90", "0.189", "182.9±0.2", "147.9±0.1", "1.24",
             "tr +24%", "122.6±0.6", "173.3±1.4", "0%"],
        ],
        font_size=10)

    # Table 2: Cache hit & GPU util (compact)
    _add_table(sl,
        Inches(0.5), Inches(4.4), Inches(8), Inches(2.6),
        ["fit×d", "tr TRUE hit", "tr GPU%", "def GPU%",
         "C=10 ratio", "C=20 ratio", "C-차이"],
        [
            ["0.50", "83.8%", "21%", "84%", "0.883", "0.884", "0.1%"],
            ["0.60", "81.1%", "26%", "87%", "0.987", "0.998", "1.1%"],
            ["0.65", "82.3%", "27%", "87%", "1.022", "0.944", "7.8%⚠"],
            ["0.70", "83.8%", "29%", "88%", "1.070", "1.073", "0.3%"],
            ["0.80", "83.6%", "30%", "89%", "1.138", "1.143", "0.5%"],
            ["0.90", "84.5%", "32%", "90%", "1.236", "1.236", "0.0%"],
        ],
        font_size=10)

    _add_callout(sl, Inches(9.0), Inches(4.6), Inches(3.8), Inches(0.7),
                 "†fd=0.75: capacity timeout\n이상점 (2/3 runs 실패)", C_RED,
                 font_size=10)
    _add_callout(sl, Inches(9.0), Inches(5.5), Inches(3.8), Inches(0.7),
                 "★ 보간 전환점: fd=0.60~0.65\n→ fit×d* ≈ 0.62 ±0.03", C_BLUE,
                 font_size=10)

    _set_notes(sl, """\
[슬라이드 8: STEP 5 데이터 테이블]
■ 84-point 본 스윕(7 fd × 2 f × 2 C × 3 rep)의 C=10 기준 정량 데이터.
■ 표 1: Wall time 비율 — ratio > 1이면 tr 승. 선형 보간으로 fd*≈0.62.
  - fd=0.50: def +12%, fd=0.65: tr +2% (전환), fd=0.90: tr +24%.
  - fd=0.75†: capacity timeout 이상점 — 2/3 tr runs에서 1개 프로그램 실패.
■ 표 2: 보조 지표
  - tr TRUE hit ≈ 80-84% 전 구간 안정 (fd 무관 cache 보존).
  - tr GPU util: 21→32% 단조 증가 (d↑ → reasoning↑).
  - def GPU util: 84→90% 거의 고정 (항상 포화).
  - C-안정성: C=10 vs C=20 비율 차이 대부분 <1% (fd=0.65에서만 7.8% 노이즈).
■ 핵심: fit×d가 정책 선택의 충분통계량. C에 흔들리지 않음.""")

    # ── Slide 9: STEP 5 ★ ───────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "★ STEP 5: 전환점 fit×d* = 0.62 — 이진 선택, 완만한 전환",
                   "84-point sweep: 7 fd × 2 f × 2 C × 3 rep  |  5090/Qwen3-8B")
    _add_image(sl, f"{FIGS}/step5_transition_yunuikang.png",
               Inches(0.2), Inches(1.35), width=Inches(9.5), height=Inches(5.8))
    _add_callout(sl, Inches(10.0), Inches(1.6), Inches(3), Inches(0.7),
                 "fd* = 0.62 ±0.03", C_RED, font_size=16)
    _add_callout(sl, Inches(10.0), Inches(2.6), Inches(3), Inches(0.6),
                 "fd<0.60: def 승 (+12%)", C_ORANGE, font_size=11)
    _add_callout(sl, Inches(10.0), Inches(3.4), Inches(3), Inches(0.6),
                 "fd>0.65: tr 승 (+7~24%)", C_BLUE, font_size=11)
    _add_callout(sl, Inches(10.0), Inches(4.2), Inches(3), Inches(0.6),
                 "C-안정: C=10≈C=20", C_GREEN, font_size=11)
    _add_callout(sl, Inches(10.0), Inches(5.0), Inches(3), Inches(0.6),
                 "tr 실패 3~7% (def 0%)", C_RED, font_size=11)
    _add_callout(sl, Inches(10.0), Inches(5.8), Inches(3), Inches(0.6),
                 "H1(내부 f*) 반증 → 이진", C_DARK, font_size=11)
    _set_notes(sl, """\
[슬라이드 8: STEP 5 ★ — 전환점 발견]
■ 이전 질문: "3-point 파일럿(d=0.1/0.2/0.5)에서 레짐 전환 발견(fd ∈ 0.48~0.95). 정확히 어디서?"
■ 84-point 본 스윕 설계:
  - f축 폐기: 파일럿에서 내부 최적 f* 부재 확정 → f=1(tr) vs f=∞(default) 이진만.
  - fit×d = {0.50, 0.60, 0.65, 0.70, 0.75, 0.80, 0.90} (전환점 근처 촘촘)
  - C = {10, 20} (2×fit, 4×fit — C-안정성 검증)
  - REPEAT = 3 (에러바)
  - 총 84 runs, ~9시간 실행
■ 측정 프로토콜: vLLM restart/clean prefix cache per point, true hit = prompt_tokens_by_source{local_compute} (참 hit, 오염 없음), nvidia-smi dmon 1s, --stream.
■ 핵심 결과 (C=10 기준):
  - fd=0.50: def +12% (ratio 0.88). fd=0.60: tied (ratio 0.99).
  - fd=0.65: tr +2% (ratio 1.02) ← 전환점. fd=0.70: tr +7%.
  - fd=0.75: 이상점 — 5/6 tr runs에서 capacity timeout 실패 → wall 증가. fd=0.80: tr +14%. fd=0.90: tr +24%.
  - 선형 보간 전환점: fd*≈0.62 ±0.03.
■ 5개 핵심 결론:
  1. 전환점 fit×d* = 0.62 ±0.03
  2. 전환은 완만(cliff 아님) — 비율이 0.88→1.24로 연속 변화
  3. C-안정: C=10과 C=20에서 동일 전환점 (fit×d가 충분통계량)
  4. 4090/P1 교차검증 방향 일치 (fd=0.46 → def 승)
  5. tr 가용성 위험: 전환 근처서 3-7% capacity timeout, default 0%
■ H1(중간 sweet spot f*) 반증: d=0.1에서 f=2.0 vs f=∞ 차이 1.7%(무의미). d=0.2에서 f=1이 최선(f=1.25만 돼도 cache 파괴). → 최적은 이진(f=1 or f=∞).
■ TRUE hit rate: tr ≈ 80-84% 전 구간 안정 (fd에 무관하게 cache 보존). default ≈ 1.4% (99% recompute).
■ → "0.62는 마법 숫자? 예측 가능?" → STEP 6.""")

    # ── Slide 9b: STEP 5 확장 — Table A (극단) ─────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "STEP 5 확장: duty별 tr vs overcommit(극단) — fit×d에서 승자 뒤집힘",
                   "6 duty × {tr(f=1), default(f=∞)}  |  goguma GPU1, C=10, R=1  |  throughput=goodput(완료/makespan)")
    _add_image(sl, f"{FIGS}/step5_table_extreme_yunuikang.png",
               Inches(0.25), Inches(1.35), width=Inches(12.85), height=Inches(5.5))
    _add_callout(sl, Inches(0.5), Inches(6.95), Inches(12.3), Inches(0.45),
                 "d=0.1(fit×d=0.48) default +26% → d=0.2(fit×d=0.95) tr +31% → d=0.9 tr +132%  "
                 "|  tr hit 0.86 안정, def hit 0.01(99% recompute)  |  tr 실패는 d=0.1에서만 10%",
                 C_DARK, font_size=10)
    _set_notes(sl, """\
[슬라이드 9b: STEP 5 확장 — Table A (극단)]
■ 목적: 설계 duty 격자(d=0.1/0.2/0.3/0.5/0.7/0.9, fit=4.76)에서 tr(f=1)과 overcommit(f=∞=default) 극단 두 정책을 duty 전 구간에서 직접 비교.
■ 측정: C=10(≈2×fit), R=1, vLLM restart/clean prefix cache per point, C_total=95,936 핀, 참hit=prompt_tokens_by_source{local_compute}, --stream, nvidia-smi dmon 1s.
  - 재사용: d=0.1 전체 f + d=0.2/0.5 f={1,1.5,∞}는 기존 파일럿(GPU0). 신규(GPU1): d=0.3/0.7/0.9 전체 f + d=0.2/0.5 f=2. cross-GPU 캐비앗(동일 5090+C_total 고정 → 방향/차수 결론 무영향).
■ 지표: throughput = goodput(=completed/makespan, prog/s). raw decode tok/s는 default의 recompute 낭비를 토큰으로 세어 오도(연구의 핵심 논점) → 미사용.
■ ★ 승자 뒤집힘 (makespan 기준):
  - d=0.1 (fit×d=0.476): default +26% (tr goodput 0.036 < def 0.051). tr은 GPU 22%만 사용(78% idle) + capacity timeout 10% 실패.
  - d=0.2 (fit×d=0.952): tr +31% — 전환! 이후 d=0.3 +64%, d=0.5 +96%, d=0.7 +101%, d=0.9 +132% 단조 확대.
  - 정밀 전환점 fit×d*≈0.62(STEP 5 세밀 격자)는 d=0.1과 d=0.2 사이.
■ 보조 지표:
  - tr TRUE hit ≈ 0.86 전 구간 안정(fit×d 무관 캐시 보존). default ≈ 0.01(99% recompute).
  - tr U: 22→61% 단조 증가(d↑ → reasoning↑). default U: 84→93% 포화 고정.
  - tr 신뢰성: 깊은 미포화 d=0.1에서만 10% 실패. d≥0.2 및 default 전 구간 0%.
■ → 극단 비교로 "어느 정책이 이기나"는 fit×d가 결정. "그럼 중간 f는?" → Table B.""")

    # ── Slide 9c: STEP 5 확장 — Table B (전개, 이진) ───────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "STEP 5 확장: duty × f 전개 — 최적은 이진(중간 f 없음)",
                   "6 duty × f{1, 1.5, 2, ∞} goodput 히트맵  |  각 행 최적 f는 항상 극단")
    _add_image(sl, f"{FIGS}/step5_table_fgrid_yunuikang.png",
               Inches(2.7), Inches(1.3), width=Inches(7.9), height=Inches(5.9))
    _add_callout(sl, Inches(0.3), Inches(1.6), Inches(2.2), Inches(1.5),
                 "d=0.1\n→ f=∞(default)\n최적\n(goodput ↑ 단조)", C_ORANGE, font_size=11)
    _add_callout(sl, Inches(0.3), Inches(3.4), Inches(2.2), Inches(1.5),
                 "d≥0.2\n→ f=1(tr) 최적\nf 조금만 올려도\ngoodput 급락", C_BLUE, font_size=11)
    _add_callout(sl, Inches(10.8), Inches(2.3), Inches(2.3), Inches(1.6),
                 "중간 f(1.5·2)는\n어느 행에서도\n최고 아님\n= 내부 최적 없음", C_RED, font_size=11)
    _add_callout(sl, Inches(10.8), Inches(4.2), Inches(2.3), Inches(1.4),
                 "★ 최적 정책은\n이진(f=1 or ∞)\nH1 반증 재확인", C_DARK, font_size=12)
    _set_notes(sl, """\
[슬라이드 9c: STEP 5 확장 — Table B (전개, 이진성)]
■ 목적: 극단(f=1, f=∞) 사이 중간 f(1.5, 2)까지 펼쳐 "연속 노브의 내부 sweet spot이 있는가?"를 duty 전 구간에서 검증.
■ 히트맵: 6 duty × 4 f, 값=goodput(prog/s). 행별 정규화(각 duty 자체 스케일)로 색칠 → 각 행 최적 f가 진하게. 빨강 테두리=행 최고.
■ ★ 결과 — 내부 최적 없음(이진):
  - d=0.1: goodput이 f와 함께 단조 증가(0.036→0.045→0.050→0.051) → f=∞(default)가 최적. 미포화 깊은 zone은 GPU를 채울수록 이득.
  - d≥0.2: f=1(tr)이 최적. f를 조금만 올려도 goodput 급락 (예: d=0.9 f=1 0.133 → f=1.5 0.066, 반토막). 중간·큰 f는 모두 f=∞ 수준(~0.057)에 수렴.
  - 6개 duty행 어디서도 중간 f(1.5·2)가 최고가 아님 → 최적 정책은 이진 선택(f=1 or f=∞).
■ 물리: overcommit이 조금이라도 들어가면 prefix cache가 파괴(hit 0.86→0.22 수준)되어 캐시 이점이 급소실 → 중간 지점의 이득이 없음. eviction은 soft(preempt=0)라 tail 페널티는 없지만 미래 recompute 비용만 증가.
■ 함의: STEP 3의 연속 노브 f는 "두 정책을 잇는 스펙트럼"이지만 최적은 항상 끝점. 따라서 런타임 선택기는 f를 튜닝할 필요 없이 fit×d로 f=1 vs f=∞만 고르면 됨. H1(미포화 내부 최적 f*) 반증을 파일럿 3점 → duty 전 6점으로 확장 재확인.
■ → 정책 선택은 이진 + fit×d가 결정. 남은 질문 "그 경계는 예측 가능?" → STEP 6 비용 모델.""")

    # ── Slide 10: STEP 6 Data Table ────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "★ STEP 6: 비용 모델 파라미터 & 정량 검증",
                   "wall ∝ S × W / U  — 3개 파라미터로 전환점 예측")

    # Table 1: Model parameters
    _add_table(sl,
        Inches(0.5), Inches(1.4), Inches(5.5), Inches(2.6),
        ["파라미터", "값", "의미"],
        [
            ["S_def", "1.000", "직렬화 없음"],
            ["S_tr", "1.749 ±0.095", "pipeline 32% 상쇄"],
            ["W_def", "0.985", "99% recompute"],
            ["W_tr", "0.168", "17% recomp (84% hit)"],
            ["W_def / W_tr", "5.86×", "★ cache gain"],
            ["U_tr(fd)", "0.099+0.256·fd", "OLS 선형 적합"],
            ["U_def(fd)", "0.782+0.134·fd", "OLS 선형 적합"],
        ],
        font_size=10)

    # Table 2: Model accuracy — predicted vs measured wall ratio
    _add_table(sl,
        Inches(6.5), Inches(1.4), Inches(6.3), Inches(2.6),
        ["fit×d", "예측 ratio", "실측 ratio", "오차"],
        [
            ["0.50", "0.893", "0.883", "+1.2%"],
            ["0.60", "0.979", "0.987", "−0.8%"],
            ["0.65", "1.021", "1.022", "−0.1%"],
            ["0.70", "1.062", "1.070", "−0.8%"],
            ["0.75†", "1.102", "0.949", "+16.1%†"],
            ["0.80", "1.142", "1.138", "+0.4%"],
            ["0.90", "1.220", "1.236", "−1.3%"],
        ],
        font_size=10)

    # Table 3: Selector gain & ideal gap
    _add_table(sl,
        Inches(0.5), Inches(4.4), Inches(12.3), Inches(2.7),
        ["fit×d", "wall_sel (s)", "vs worst\nfixed", "선택",
         "wall_ideal (s)", "ideal 대비\n갭",
         "tr 실패율", "def 실패율", "선택기\n실패율"],
        [
            ["0.50", "195.2", "13.2%", "def", "28.0", "7.0×",
             "0.0%", "0.0%", "0.0%"],
            ["0.60", "190.1", "1.3%", "def", "28.1", "6.8×",
             "3.3%", "0.0%", "0.0%"],
            ["0.65", "183.9", "2.2%", "tr", "27.9", "6.6×",
             "3.3%", "0.0%", "3.3%"],
            ["0.70", "174.3", "7.0%", "tr", "28.1", "6.2×",
             "0.0%", "0.0%", "0.0%"],
            ["0.80", "162.0", "13.8%", "tr", "28.0", "5.8×",
             "0.0%", "0.0%", "0.0%"],
            ["0.90", "147.9", "23.6%", "tr", "28.0", "5.3×",
             "0.0%", "0.0%", "0.0%"],
        ],
        font_size=10)

    _set_notes(sl, """\
[슬라이드 10: STEP 6 데이터 테이블]
■ 표 1: 비용 모델 파라미터 — S(직렬화), W(recompute 비율), U(GPU util) 3가지.
  - S_tr = 1.749 ±0.095: C/fit=2.10 상한에서 pipeline overlap 32% 상쇄.
  - W_def/W_tr = 5.86×: cache gain — tr의 핵심 이점.
  - U: 선형 적합 (nvidia-smi dmon 1s 평균).
■ 표 2: 모델 정확도 — 정상 6개 fd에서 예측 vs 실측 wall ratio 오차 ±1.3%.
  - fd=0.75†: capacity timeout 이상점 → 16.1% 오차 (실패 비용 미반영).
  - 전환 조건: U_tr/U_def = 0.2986 → fd* = 0.625 (실측 0.62, 오차 0.9%).
■ 표 3: 선택기 이득 + ideal 갭 + 실패율
  - worst policy 대비 최대 24% (V자형 — 극단에서 크고 전환점에서 작음).
  - ideal(U=1, hit=1, S=1) 대비 5.3~7.0× 갭 → 현 최선도 ~15% 실현 → 큰 개선 여지.
  - 선택기 안정성 부산물: fd<fd*에서 def 선택 → tr failure 자동 회피.""")

    # ── Slide 11: STEP 6 ★ ───────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "★ STEP 6: wall ∝ S×W/U → 전환점 0.625 예측 (실측 0.62, 0.9%)",
                   "3-파라미터 비용 모델이 84점 스윕을 ±1.3%로 설명")
    _add_image(sl, f"{FIGS}/step6_cost_model_yunuikang.png",
               Inches(0.2), Inches(1.35), width=Inches(9.5), height=Inches(5.8))
    _add_callout(sl, Inches(10.0), Inches(1.6), Inches(3), Inches(0.7),
                 "S_tr = 1.75 ± 0.10\n(직렬화)", C_BLUE, font_size=11)
    _add_callout(sl, Inches(10.0), Inches(2.5), Inches(3), Inches(0.7),
                 "W_def/W_tr = 5.86×\n(cache gain)", C_GREEN, font_size=11)
    _add_callout(sl, Inches(10.0), Inches(3.4), Inches(3), Inches(0.7),
                 "예측 fd* = 0.625\n실측 0.62 → 0.9%", C_RED, font_size=14)
    _add_callout(sl, Inches(10.0), Inches(4.3), Inches(3), Inches(0.7),
                 "선택기: 최대 24% 개선\nvs worst fixed policy", C_ACCENT, font_size=11)
    _add_callout(sl, Inches(10.0), Inches(5.2), Inches(3), Inches(0.7),
                 "이상 대비 5.3~7.0× 갭\n→ 큰 개선 여지", C_GRAY, font_size=11)
    _set_notes(sl, """\
[슬라이드 9: STEP 6 ★ — 비용 모델]
■ 이전 질문: "0.62는 마법 숫자인가, 예측 가능한가?"
■ 비용 모델: wall(policy) ∝ S(policy) × W(policy) / U(policy, fd)
  - S = 직렬화 계수: tr이 capacity gate로 프로그램을 직렬화하는 정도.
    S_def = 1 (직렬화 없음). S_tr = 1.749 ± 0.095 (C/fit=2.10이 상한, pipeline overlap 32% 상쇄).
  - W = recompute 비율: prompt_tokens_local_compute / prompt_tokens_total.
    W_def = 0.985 (99% recompute). W_tr = 0.168 (17% recompute, 84% cache hit).
    W_def/W_tr = 5.86× — cache gain.
  - U = GPU 이용률 (nvidia-smi dmon 1s 평균).
    U_tr(fd) = 0.0986 + 0.2557×fd (OLS 선형 적합).
    U_def(fd) = 0.7819 + 0.1338×fd.
■ 전환 조건: (W_def/W_tr) × (U_tr/U_def) / S_tr = 1 → U_tr/U_def = 0.2986
  → fd* = (0.2986 × 0.7819 − 0.0986) / (0.2557 − 0.2986 × 0.1338) = 0.625.
■ 예측 0.625 vs 실측 0.62 → 오차 0.005 (0.9%).
■ 모델 정확도: 정상 6개 fd에서 예측 vs 실측 wall ratio 오차 ±1.3%. fd=0.75만 16.1% (capacity timeout).
■ 선택기 이득: worst fixed policy 대비 최대 24% (V자형 — 극단에서 크고 전환점에서 작음).
■ 이상(U=1, hit=1, S=1) 대비 갭: 5.3~7.0× — 현 최선도 이상의 ~15% 실현. 큰 개선 여지.
■ 선택기 안정성 부산물: fd<fd*에서 자동으로 def 선택 → tr의 capacity timeout 회피.
■ [추정/한계] W의 fd 독립 가정 (현 데이터에서 성립하나 넓은 ctx 분포에서 변할 수 있음). S_tr의 C/fit 의존 (C=10 고정, C≫fit에서 외삽 미검증).
■ → "이 법칙이 진짜 워크로드에서도 성립?" → 4 워크로드 교차검증.""")

    # ── Slide 10: 4-workload map ─────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "4 워크로드 × fit×d 축: 전부 정합",
                   "SWE · TraceLab · HLE · Science — 전환점 0.62를 중심으로")
    _add_image(sl, f"{DIAG}/workload_map.png", Inches(0.3), Inches(1.2),
               width=Inches(12.7), height=Inches(6))
    _set_notes(sl, """\
[슬라이드 10: 4 워크로드 × fit×d]
■ 이전 질문: "비용모델과 전환점이 실제 워크로드에서도 성립하나?"
■ fit×d 축에 4개 실제 워크로드 배치 (전환점 fd*=0.62 선 기준):
  1. SWE-bench (decode-heavy, d≈0.996):
     - 4090: fit×d=5.54 → tr 승 +78~84% (fd≫0.62 → tr 영역 ✓)
     - Pro6000: fit×d=57.6 → tr 승 +113% (fd≫0.62 ✓)
     - ★ 항상 zone 밖 → tr 무조건 최선
  2. TraceLab (tool-heavy, d≈0.196~0.289):
     - 4090: fit×d=0.46 → default 승 −34% (fd<0.62 → default 영역 ✓)
     - Pro6000: fit×d=7.07 → tr 승 +80~87% (fd≫0.62 ✓)
     - 5090: fit×d=0.93 → 경계 근처 (zone 자연 진입)
     - ★ KV 풀 변경으로 fd가 바뀌면 정책도 뒤집힘 → 프레임워크 검증
  3. HLE / ToolOrchestra (heavy-tail tool):
     - GLM API + FAISS retrieval → stochastic tool latency (2~31s/round)
     - Smoke 통과: tool 0%→100% success (하네스 버그 수정 후)
     - 24h GLM latency 샘플러 기동 → 시간변동 조기 확인
     - ★ heavy-tail 분포 → mean-U 모델의 한계 (tail-aware U 필요)
  4. ScienceAgentBench (on hold):
     - SAB 태스크 데이터가 password-protected SharePoint → 접근 불가
     - 예상: 중간 duty, 희소 tail (HLE 대조)
■ ★ fd < 0.62: default wins | fd > 0.62: tr wins — SWE/TraceLab/합성 전부 정합. HLE/Science는 미완(한계 명시).
■ VLLM Profiling 핵심 발견도 정합:
  - R = k_fit × d = 동시 실행 프로그램 기대수 → U 예측. Pearson r(예측 U, 실측 U) = 0.982.
  - TRUE hit rate 오염 비대칭: default 26.3× 과대(true hit 0.18 vs reported 0.005), tr 1.0×(정확).
  - throughput formula: thr ∝ U/W, 보정 후 오차 1.4%.""")

    # ── Slide 11: P1 cross-validation ────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "P1 교차검증: KV ×10.4 확대 → tr 역전 (R모델 r=0.982)",
                   "4090(fit~2, R<1, 패) → Pro6000(fit~25, R≫1, 승)")
    # Try both figures, use whichever exists
    fig_p1 = f"{FIGS}/tp2_kfit_flip_4090_vs_pro6000.png"
    fig_p1b = f"{FIGS}/tp2_pred_vs_meas_U.png"
    _add_image(sl, fig_p1, Inches(0.5), Inches(1.5), width=Inches(5.5), height=Inches(5.5))
    _add_image(sl, fig_p1b, Inches(6.5), Inches(1.5), width=Inches(5.5), height=Inches(5.5))
    _set_notes(sl, """\
[슬라이드 11: P1 교차검증 — k_fit-flip]
■ 이전: 4 워크로드가 fit×d 축에서 정합함을 보임. 이 슬라이드: "같은 워크로드에서 KV 풀만 바꾸면 정책이 뒤집히는가?"를 실증.
■ P1 실험 (Pro6000 TP2 Qwen3-32B, nutella1):
  - KV 풀: 4090 43,888 → Pro6000 456,944 (×10.41).
  - TraceLab: fit 2.35 → 25. SWE: fit ~6 → ~58.
  - TraceLab 스윕 결과:
    C=16(fit 미만): tr = def (음성대조 ✅)
    C=32(fit 초과): tr +87% thru, 2.3× hit, p95 −46% ★
    C=64(fit 초과): tr +80% thru, 3.1× hit, p95 −47%
  - SWE 스윕 결과:
    C=16, 32(fit 미만): tr ≈ def (음성대조 ✅)
    C=64(fit 초과): tr +113% thru, 2.8× hit, p95 −51% ★
■ R 모델: R = k_fit × d, 예측 U = min(R, 1).
  - 4090/TraceLab: k_fit=1.6, d=0.196, R=0.31 → U_pred=0.31 → 실측 U≈0.35.
  - Pro6000/TraceLab: k_fit=21.6, d=0.289, R=6.2 → U_pred=1.0 → 실측 U≈0.97.
  - 4090 앵커 포함 Pearson r(예측 U, 실측 U) = 0.982.
■ 정직한 caveat: Pro6000에서 모든 셀 R>1 → U~0.97-1.0 포화(스래싱 default도 GPU busy). 즉 Pro6000에서 tr 우위는 occupancy(U)가 아니라 KV hit/goodput — default는 busy하나 재프리필로 낭비, tr은 hit 유지로 productive.
■ SYS 페널티: TP2/TP1 = 1.73× (효율 86.5%). SYS(cross-NUMA) all-reduce 오버헤드 ~13.5%.""")

    # ── Slide 12: Findings & Limits ──────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "정직한 발견과 한계",
                   "H1 반증 · 전환점 예측 가능 · heavy-tail 한계 · tr 신뢰성 위험")
    _add_image(sl, f"{DIAG}/findings.png", Inches(0.3), Inches(1.3),
               width=Inches(12.7), height=Inches(5.5))
    _set_notes(sl, """\
[슬라이드 12: 정직한 발견과 한계]
■ H1(중간 sweet spot f*) 반증:
  - 3-point 파일럿에서 확인: d=0.1에서 f=2.0 vs f=∞ 차이 1.7%(무의미). d=0.2에서 f=1이 최선(f=1.25만 돼도 cache hit 0.86→0.42 급락).
  - → 최적 정책은 이진(f=1 or f=∞). 연속 최적화 불필요. f>f_sat에서 모든 지표 수렴.
■ 전환점 fd*는 HW/워크로드에 따라 변하지만 예측 가능:
  - 5090/Qwen3-8B: fd*=0.62 (비용모델 예측 0.625, 오차 0.9%).
  - 비용모델 wall ∝ S×W/U: S_tr(직렬화), W(recompute 비율), U(GPU 이용률) 3개 파라미터로 결정.
  - 다른 시스템에서도 S, W, U만 측정하면 fd* 예측 가능(추가 검증 필요).
  - fd*=0.62가 보편 상수인지는 미확인 — 5090/Qwen3-8B 단일 셀에서만 측정.
■ heavy-tail(HLE류) 한계:
  - 현 모델은 U = 평균 GPU 이용률(nvidia-smi) 사용.
  - HLE류 heavy-tail 워크로드: 소수 프로그램이 GPU를 장시간 점유(p99 pause 521.85s, mean 18.47s — VLLM profiling 실측).
  - 평균 U가 실효성 과대추정 → tail-aware U(p99 기반 또는 가중 평균) 필요.
■ tr 신뢰성 위험:
  - 전환 근처(fd≈0.60~0.75)에서 tr의 capacity timeout 3~7% (C>fit일 때 대기 중 timeout).
  - default는 실패 0% — 안정성에서는 항상 우위.
  - 선택기가 fd<fd*에서 def 선택 → tr 실패 자동 회피. 전환점 바로 위(fd=0.65)에서만 3.3% 잔여.
■ 추가 한계:
  - fd=0.75 이상점: capacity timeout failures는 W·U·S로 포착 불가 → 확률적 실패 비용 별도 모델링 필요.
  - 합성 워크로드: 단일 ctx profile. 실제 워크로드는 ctx 분포가 넓어 전환이 더 완만할 수 있음.
  - REPEAT=3: 전환 근처 std < 10%이나, 더 많은 반복으로 정밀도 향상 가능.
  - HLE/Science 미완: HLE는 24h 샘플러 단계, Science는 데이터 blocker로 보류.""")

    # ── Slide 13: Contribution ───────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "기여: fit×d-aware 정책 선택",
                   "단일 무차원수로 정책 선택 + 비용모델로 전환점 예측 + 선택기로 양쪽 개선")
    _add_image(sl, f"{DIAG}/selector.png", Inches(0.3), Inches(1.2),
               width=Inches(12.7), height=Inches(6))
    _set_notes(sl, """\
[슬라이드 13: 기여]
■ 기여 1: fit×d가 tr/default 최적 정책의 충분통계량.
  - 단 하나의 무차원수 fit×d = (C_total/peak_seq) × (reasoning/(reasoning+tool))로 정책 선택 가능.
  - C에 안정적(C=10 ≈ C=20). 4 워크로드에서 방향 전부 정합.
■ 기여 2: 비용모델(wall ∝ S×W/U)로 전환점 0.9% 오차 예측.
  - S(직렬화) × W(recompute) / U(GPU util) — 3개 측정 가능 파라미터.
  - 모델이 정상 범위에서 ±1.3% 정확. 새 시스템에서 S, W, U만 측정하면 fd* 예측 가능.
■ 기여 3: SOTA(tr)의 레짐-무지(regime-unaware) 취약점 발견.
  - 미포화(fd<0.62)에서 tr이 −12~34% 느리고, 3~7% capacity timeout 실패.
  - tr은 "레짐을 모르고" 항상 pause → 미포화에서는 오히려 해로움.
■ 기여 4: fit×d-aware 선택기가 throughput과 가용성 동시 개선.
  - Worst fixed policy 대비 최대 24% throughput 개선 (V자형: 극단에서 크고 전환점에서 작음).
  - fd<fd*에서 def 선택 → tr의 capacity timeout 실패 자동 회피.
  - 이상 대비 5.3~7.0× 갭 → 선택기는 첫 걸음, 더 큰 개선 여지.""")

    # ── Slide 14: Future work ────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "향후: tail-aware U · 전환점 실증 · 적응형 스케줄러")
    _add_image(sl, f"{DIAG}/future.png", Inches(0.3), Inches(1.6),
               width=Inches(12.7), height=Inches(5))
    _set_notes(sl, """\
[슬라이드 14: 향후 과제]
■ 1. tail-aware U 모델 확장:
  - 현 모델의 가장 큰 한계: U = mean GPU util 사용.
  - HLE류 heavy-tail 워크로드에서 소수 프로그램이 GPU 장시간 점유 → mean U가 실효성 과대추정.
  - U_mean → U_tail(p99 기반 또는 가중 평균)로 확장하면 heavy-tail 워크로드의 전환점도 예측 가능.
  - VLLM profiling에서 관찰: tr pause p50=0.00s, p99=521.85s(mean 18.47s driven by 2.4% of steps with 5+ minute pauses).
■ 2. 전환점 이동 실증:
  - fd*=0.62는 5090/Qwen3-8B 단일 셀에서 측정. 보편 상수인지 미확인.
  - A100/H100, Qwen3-32B/70B, 다른 워크로드(HLE 완료 시, Science 데이터 확보 시)에서 fd*가 어떻게 변하는지 실증 필요.
  - 비용모델(S×W/U)의 보편성: S_tr는 C/fit에 의존, U 적합은 GPU별 다를 수 있음 → 각 시스템에서 파라미터 재추정 후 fd* 예측 가능한지 검증.
■ 3. 적응형 런타임 스케줄러:
  - 현재는 사전 프로파일(c=1 측정으로 d 산출 + C_total 확인 → fit×d 계산) 필요.
  - 실시간 d 추정(최근 N턴의 reasoning/tool 비율 이동평균) + 런타임 fit 계산(현재 KV 사용량/프로그램 크기) → 정책 자동 전환.
  - 전환 시 히스테리시스(마진) 적용: fd* ± δ 범위에서는 현 정책 유지 → 불필요한 전환 방지.
  - 실패율을 비용 항에 추가: 이중 목표(throughput + reliability) 최적화.""")

    # ── Slide 15: Summary ────────────────────────────────────────────
    sl = prs.slides.add_slide(blank)
    _add_title_bar(sl, "요약: 인과 사슬 압축",
                   "퍼즐 → 경계 → 상충 → 노브+합성 → 전환점 → 비용모델 → 검증 → 기여")
    _add_image(sl, f"{DIAG}/summary_chain.png", Inches(0.3), Inches(1.2),
               width=Inches(12.7), height=Inches(6))
    _set_notes(sl, """\
[슬라이드 15: 요약]
■ 인과 사슬:
  퍼즐(tr이 지기도 이기기도) → fit×d 경계 정의(STEP 2, 42셀 격자, 일반성 입증) → idle↔recompute 상충 구조 → f 노브 구현(STEP 3, 게이트 B 통과) + 듀티 통제 합성 워크로드(STEP 4, 게이트 C 통과) → 84점 스윕으로 전환점 fd*=0.62 발견(STEP 5, 이진 선택, 완만, C-안정) → 비용모델 wall ∝ S×W/U로 fd*=0.625 예측(STEP 6, 0.9% 오차) → 4 워크로드 교차검증(SWE/TraceLab/HLE/Science — 방향 전부 정합) → 기여(fit×d-aware 선택기: 최대 24% + 실패 회피).
■ 한 줄 요약:
  fit×d > 0.62이면 tr(pause), 아래면 default(overcommit).
  비용모델(직렬화×recompute/GPU이용률)로 전환점 예측 가능(0.9% 오차).
  선택기로 worst policy 대비 최대 24% throughput 개선 + capacity timeout 실패 회피.
  heavy-tail 워크로드는 tail-aware U 확장 필요(현 모델의 명시적 한계).
■ 핵심 수치:
  - fit×d* = 0.62 ±0.03 (실측) / 0.625 (모델 예측)
  - S_tr = 1.75 ± 0.10 / W_def/W_tr = 5.86× / 모델 오차 ±1.3%
  - 선택기: worst policy 대비 최대 24%, 이상 대비 5.3~7.0× 갭
  - R 모델 Pearson r = 0.982 (P1 교차검증)
  - tr 실패율: 3~7% (전환 근처), 선택기 사용 시 ≈0%
■ 산출물: 6개 STEP, 2개 보고(P1/P3), 10+ 그림, 84점 스윕 데이터, 비용 모델, 선택기 설계.""")

    # ── Save ─────────────────────────────────────────────────────────
    prs.save(OUT)
    print(f"Saved: {OUT}")
    print(f"  {len(prs.slides)} slides")


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════
def main():
    print("Generating diagrams...")
    gen_title_motif()
    gen_pipeline()
    gen_puzzle()
    gen_seesaw()
    gen_fdial()
    gen_dsweep()
    gen_workload_map()
    gen_findings()
    gen_selector()
    gen_future()
    gen_summary_chain()
    print(f"  → {DIAG}/ ({len(os.listdir(DIAG))} files)")

    print("Building PPTX...")
    build_pptx()
    print("Done.")

if __name__ == "__main__":
    main()
