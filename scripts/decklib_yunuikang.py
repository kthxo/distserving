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


def _md_runs(para, text, bold_default=False):
    """`**...**` 구간을 굵은 run 으로 쪼개 para 에 채운다.

    파서가 없으면 별표가 슬라이드에 그대로 찍힌다 — 이 함수가 유일한 처리 지점이다.
    반환: [(run, is_bold_marked)] — 색·크기는 호출자(_tf)가 나중에 입힌다.
    """
    out = []
    for k, seg in enumerate(text.split("**")):
        if not seg:
            continue
        r = para.add_run()
        r.text = seg
        marked = (k % 2 == 1)          # 홀수 조각 = ** 사이
        out.append((r, marked or bold_default))
    if not out:                        # 빈 문자열도 run 하나는 있어야 서식이 붙는다
        out.append((para.add_run(), bold_default))
    return out


def _set_md_text(tf, text, bold_default=False):
    """텍스트프레임 전체를 줄 단위 문단 + 마크다운 굵기로 채운다."""
    tf.clear()
    marks = []
    for i, line in enumerate(str(text).split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        for r in p.runs:               # clear() 후에도 남는 빈 run 정리
            r._r.getparent().remove(r._r)
        marks += _md_runs(p, line, bold_default)
    return marks


def _tf(shape, size, color=INK, bold=False, align=PP_ALIGN.LEFT, italic=False):
    tf = shape.text_frame
    tf.word_wrap = True
    for p in tf.paragraphs:
        p.alignment = align
        for r in p.runs:
            r.font.size = Pt(size); r.font.color.rgb = color
            r.font.bold = bold; r.font.italic = italic
            r.font.name = "Arial"


def _fill(shape, text, size, color=INK, bold=False, align=PP_ALIGN.LEFT, italic=False):
    """마크다운 굵기를 살려 텍스트프레임을 채우고 서식을 입힌다."""
    tf = shape.text_frame
    tf.word_wrap = True
    marks = _set_md_text(tf, text, bold_default=bold)
    for p in tf.paragraphs:
        p.alignment = align
    for r, is_bold in marks:
        r.font.size = Pt(size); r.font.color.rgb = color
        r.font.bold = is_bold; r.font.italic = italic
        r.font.name = "Arial"
    return shape


def add_title(slide, text, y=0.28, size=27, color=INK, w=12.6, x=0.42):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.9))
    return _fill(tb, text, size, color, bold=True)


def add_takeaway(slide, text, y=1.12, size=15, color=BLUE, w=12.6, x=0.42):
    """One-line key message under the title."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(0.55))
    return _fill(tb, text, size, color, bold=True, italic=True)


def add_text(slide, text, x, y, w, h, size=13, color=INK, bold=False, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    return _fill(tb, text, size, color, bold=bold, align=align)


def add_bullets(slide, items, x, y, w, h, size=13, gap=6):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    tf.clear()
    for i, (txt, lvl, col, bold) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        for r in p.runs:
            r._r.getparent().remove(r._r)
        p.level = lvl
        p.space_after = Pt(gap)
        for r, is_bold in _md_runs(p, ("•  " if lvl == 0 else "–  ") + txt, bold):
            r.font.size = Pt(size); r.font.color.rgb = col
            r.font.bold = is_bold; r.font.name = "Arial"
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
    return _fill(tb, text, size, color, italic=True, align=align)


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
            c.margin_left = Inches(0.05); c.margin_right = Inches(0.05)
            c.margin_top = Inches(0.02); c.margin_bottom = Inches(0.02)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            is_hdr = header and i == 0
            force_bold = is_hdr or (i in highlight_rows and i > 0) or \
                (highlight_col is not None and j == highlight_col and i > 0)
            marks = _set_md_text(c.text_frame, val, bold_default=force_bold)
            for para in c.text_frame.paragraphs:
                para.alignment = PP_ALIGN.CENTER if j > 0 else PP_ALIGN.LEFT
            if is_hdr:
                c.fill.solid(); c.fill.fore_color.rgb = hdr_bg
            elif i in highlight_rows:
                c.fill.solid(); c.fill.fore_color.rgb = highlight_rows[i]
            elif zebra and i % 2 == 0:
                c.fill.solid(); c.fill.fore_color.rgb = LT
            else:
                c.fill.solid(); c.fill.fore_color.rgb = WHITE
            for run, is_bold in marks:
                run.font.name = "Arial"
                run.font.size = Pt(hdr_fs if is_hdr else fs)
                run.font.color.rgb = hdr_fg if is_hdr else INK
                run.font.bold = is_bold
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
    _fill(sh, text, size, fg, bold=True, align=PP_ALIGN.CENTER)
    return sh
