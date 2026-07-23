"""Reusable python-pptx helpers for the full-study deck (P2, yunuikang).

House style: 16:9 (13.333 x 7.5 in). Figure-centric slides: minimal text on the
slide face (title + one-line takeaway + labels), full detail lives in speaker notes.
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from PIL import Image
import os

# palette
INK   = RGBColor(0x1A, 0x1A, 0x2E)
BLUE  = RGBColor(0x2E, 0x5E, 0xAA)   # tr / positive
RED   = RGBColor(0xC0, 0x39, 0x2B)   # default / thrash
GREEN = RGBColor(0x1E, 0x7D, 0x4F)
GRAY  = RGBColor(0x6B, 0x6B, 0x7B)
LT    = RGBColor(0xF2, 0xF4, 0xF8)
AMBER = RGBColor(0xB8, 0x7A, 0x1E)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SW, SH = Inches(13.333), Inches(7.5)
FIGDIR = "/home/yunuikang/yunuikang_work/distserving/figures"


def new_deck():
    p = Presentation()
    p.slide_width, p.slide_height = SW, SH
    return p


def _blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _tf(shape, size, color=INK, bold=False, align=PP_ALIGN.LEFT, italic=False):
    tf = shape.text_frame
    tf.word_wrap = True
    for p in tf.paragraphs:
        p.alignment = align
        for r in p.runs:
            r.font.size = Pt(size); r.font.color.rgb = color
            r.font.bold = bold; r.font.italic = italic
            r.font.name = "Arial"


def add_title(slide, text, y=0.28, size=27, color=INK, w=12.6, x=0.42):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.9))
    tb.text_frame.text = text
    _tf(tb, size, color, bold=True)
    return tb


def add_takeaway(slide, text, y=1.12, size=15, color=BLUE, w=12.6, x=0.42):
    """One-line key message under the title."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.55))
    tb.text_frame.text = text
    _tf(tb, size, color, bold=True, italic=True)
    return tb


def add_text(slide, text, x, y, w, h, size=13, color=INK, bold=False, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tb.text_frame.text = text
    _tf(tb, size, color, bold=bold, align=align)
    return tb


def add_bullets(slide, items, x, y, w, h, size=13, gap=6):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    for i, (txt, lvl, col, bold) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = ("•  " if lvl == 0 else "–  ") + txt
        p.level = lvl
        p.space_after = Pt(gap)
        for r in p.runs:
            r.font.size = Pt(size); r.font.color.rgb = col
            r.font.bold = bold; r.font.name = "Arial"
    return tb


def add_figure(slide, name, x, y, max_w, max_h, frame=True):
    """Place figures/<name>.png fit within (max_w,max_h) box, centered, preserving AR."""
    path = os.path.join(FIGDIR, name if name.endswith(".png") else name + ".png")
    iw, ih = Image.open(path).size
    ar = iw / ih
    box_ar = max_w / max_h
    if ar > box_ar:
        w = max_w; h = max_w / ar
    else:
        h = max_h; w = max_h * ar
    cx = x + (max_w - w) / 2
    cy = y + (max_h - h) / 2
    pic = slide.shapes.add_picture(path, Inches(cx), Inches(cy), Inches(w), Inches(h))
    if frame:
        pic.line.color.rgb = RGBColor(0xD5, 0xD8, 0xDE); pic.line.width = Pt(0.75)
    return pic


def add_caption(slide, text, x, y, w, size=10.5, color=GRAY, align=PP_ALIGN.CENTER):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.35))
    tb.text_frame.text = text
    _tf(tb, size, color, italic=True, align=align)
    return tb


def add_table(slide, rows, x, y, w, h, header=True, fs=12, hdr_fs=12,
              col_widths=None, highlight_rows=None, highlight_col=None,
              zebra=True, hdr_bg=INK, hdr_fg=WHITE):
    """rows: list[list[str]]. highlight_rows: {rowidx: RGBColor} tints a data row."""
    nr, nc = len(rows), len(rows[0])
    gt = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(h)).table
    if col_widths:
        for j, cw in enumerate(col_widths):
            gt.columns[j].width = Inches(cw)
    highlight_rows = highlight_rows or {}
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = gt.cell(i, j)
            c.text = str(val)
            c.margin_left = Inches(0.05); c.margin_right = Inches(0.05)
            c.margin_top = Inches(0.02); c.margin_bottom = Inches(0.02)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            para = c.text_frame.paragraphs[0]
            para.alignment = PP_ALIGN.CENTER if j > 0 else PP_ALIGN.LEFT
            run = para.runs[0] if para.runs else para.add_run()
            run.font.name = "Arial"
            if header and i == 0:
                c.fill.solid(); c.fill.fore_color.rgb = hdr_bg
                run.font.size = Pt(hdr_fs); run.font.bold = True; run.font.color.rgb = hdr_fg
            else:
                run.font.size = Pt(fs); run.font.color.rgb = INK
                if i in highlight_rows:
                    c.fill.solid(); c.fill.fore_color.rgb = highlight_rows[i]
                    run.font.bold = True
                elif zebra and i % 2 == 0:
                    c.fill.solid(); c.fill.fore_color.rgb = LT
                else:
                    c.fill.solid(); c.fill.fore_color.rgb = WHITE
                if highlight_col is not None and j == highlight_col and i > 0:
                    run.font.bold = True
    return gt


def set_notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def band(slide, y, h, color, x=0.0, w=13.333):
    """decorative horizontal band (e.g., title underline / footer)."""
    from pptx.enum.shapes import MSO_SHAPE
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color; sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def chip(slide, text, x, y, w, color, fg=WHITE, size=11, h=0.34):
    from pptx.enum.shapes import MSO_SHAPE
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color; sh.line.fill.background()
    sh.shadow.inherit = False
    sh.text_frame.text = text
    _tf(sh, size, fg, bold=True, align=PP_ALIGN.CENTER)
    sh.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    return sh
