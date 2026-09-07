"""Build the investigation-2 slide deck. Writes ../FlakyLens_token_proxy.pptx"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
import os

INK   = RGBColor(0x15, 0x1A, 0x21)
INK2  = RGBColor(0x3D, 0x46, 0x53)
MUTED = RGBColor(0x6B, 0x76, 0x84)
ACC   = RGBColor(0x2F, 0x48, 0x58)
UP    = RGBColor(0x3A, 0x66, 0x50)
DOWN  = RGBColor(0xA8, 0x45, 0x2B)
RULE  = RGBColor(0xDC, 0xE0, 0xE7)
SUNK  = RGBColor(0xED, 0xEF, 0xF3)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CODEBG = RGBColor(0xF1, 0xF3, 0xF6)
# validated categorical pair, light surface
S_BODY = RGBColor(0x00, 0x78, 0x9C)
S_CTX  = RGBColor(0xC2, 0x5B, 0x22)
S_REF  = RGBColor(0x8B, 0x95, 0xA1)
ACCSOFT = RGBColor(0xE3, 0xEA, 0xEF)
UPSOFT  = RGBColor(0xE3, 0xED, 0xE7)
DOWNSOFT = RGBColor(0xF6, 0xE7, 0xE2)

BODY = "Calibri"; MONO = "Consolas"; DISP = "Calibri"
RENDER = 1.23

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
W, H, M = 13.333, 7.5, 0.72


def slide():
    s = prs.slides.add_slide(BLANK)
    f = s.background.fill; f.solid(); f.fore_color.rgb = WHITE
    return s


def tb(s, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    b = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = b.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    return tf


def para(tf, text, size, color, font=BODY, bold=False, space_after=0,
         space_before=0, first=False, italic=False, line=None, align=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.space_after = Pt(space_after); p.space_before = Pt(space_before)
    if line: p.line_spacing = line
    if align is not None: p.alignment = align
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.color.rgb = color
    r.font.name = font; r.font.bold = bold; r.font.italic = italic
    return p


def rect(s, x, y, w, h, fill, line=None, lw=0.75):
    sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                            Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line; sh.line.width = Pt(lw)
    sh.shadow.inherit = False
    return sh


def dot(s, cx, cy, r, fill, ring=None):
    sh = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - r), Inches(cy - r),
                            Inches(2 * r), Inches(2 * r))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    if ring is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = ring; sh.line.width = Pt(1.5)
    sh.shadow.inherit = False
    return sh


def eyebrow(s, text):
    para(tb(s, M, 0.42, 11.5, 0.3), text.upper(), 10.5, MUTED, MONO, first=True)


def title(s, text, y=0.78, size=30):
    para(tb(s, M, y, 11.9, 0.9), text, size, INK, DISP, bold=True, first=True,
         line=1.05)


def rule_line(s, y, x=M, w=W - 2 * M, color=RULE, thick=1.0):
    rect(s, x, y, w, thick / 72.0, color)


def code(s, x, y, w, lines, size=12.5, pad=0.16, lh=1.28):
    h = pad * 2 + len(lines) * (size * lh * RENDER / 72.0)
    rect(s, x, y, w, h, CODEBG, RULE)
    tf = tb(s, x + pad, y + pad, w - 2 * pad, h - 2 * pad)
    for i, (t, st) in enumerate(lines):
        col = {"plain": INK2, "hi": DOWN, "dim": MUTED, "acc": ACC}[st]
        para(tf, t or " ", size, col, MONO, bold=st in ("hi", "acc"),
             first=(i == 0), line=lh)
    return y + h


def footer(s, n):
    para(tb(s, W - 1.5, H - 0.52, 0.9, 0.3), str(n), 10, MUTED, MONO,
         first=True, align=PP_ALIGN.RIGHT)


def note(s, y, text, color=INK2, size=15, x=M, w=W - 2 * M, h=0.9):
    para(tb(s, x, y, w, h), text, size, color, BODY, first=True, line=1.28)


def table(s, x, y, cols, widths, rows, size=13.5, rh=0.42, head_size=11,
          highlight=None, dim=None, aligns=None):
    """cols: header strings. rows: list of tuples. widths: inches per column."""
    aligns = aligns or ["l"] * len(cols)
    total = sum(widths)
    rect(s, x, y, total, 0.40, SUNK)
    cx = x
    for c, wd, al in zip(cols, widths, aligns):
        tf = tb(s, cx + 0.12, y + 0.09, wd - 0.24, 0.28)
        para(tf, c.upper(), head_size, MUTED, MONO, bold=True, first=True,
             align=PP_ALIGN.RIGHT if al == "r" else PP_ALIGN.LEFT)
        cx += wd
    yy = y + 0.48
    for i, row in enumerate(rows):
        if highlight is not None and i in highlight:
            rect(s, x, yy - 0.06, total, rh - 0.02, ACCSOFT)
        cx = x
        for j, (v, wd, al) in enumerate(zip(row, widths, aligns)):
            col = MUTED if (dim is not None and i in dim) else (
                INK if (highlight is not None and i in highlight) else INK2)
            bold = highlight is not None and i in highlight
            fnt = MONO if al == "r" else BODY
            tf = tb(s, cx + 0.12, yy, wd - 0.24, 0.30)
            para(tf, str(v), size, col, fnt, bold=bold, first=True,
                 align=PP_ALIGN.RIGHT if al == "r" else PP_ALIGN.LEFT)
            cx += wd
        yy += rh
        rule_line(s, yy - 0.09, x, total)
    return yy



def pill(s, x, y, text, fg, bg):
    ww = 0.105 * len(text) + 0.30
    rect(s, x, y, ww, 0.30, bg)
    para(tb(s, x, y + 0.02, ww, 0.28, MSO_ANCHOR.MIDDLE), text, 12, fg, MONO,
         bold=True, first=True, align=PP_ALIGN.CENTER)
    return x + ww


# ============================================================== 1 title
s = slide()
rect(s, 0, 0, 0.18, H, S_BODY)
para(tb(s, M + 0.20, 1.62, 11.2, 0.4),
     "FLAKYLENS · INVESTIGATION 2 · TOKEN-PROXY CHECK", 12, MUTED, MONO, first=True)
para(tb(s, M + 0.20, 2.15, 11.4, 1.4), "What Context Is Worth", 46, INK, DISP,
     bold=True, first=True, line=1.0)
para(tb(s, M + 0.20, 3.50, 9.7, 1.5),
     "The class around a test carries category signal the test body does not. "
     "Measured with a fixed token lexicon on 80 flaky tests, it is worth about "
     "35 accuracy points to a classifier that was never trained. All of it is "
     "order dependency.", 17, INK2, BODY, first=True, line=1.32)
rule_line(s, 5.42, M + 0.20, 9.7)
tf = tb(s, M + 0.20, 5.62, 11, 0.9)
para(tf, "80 tests · 5 projects · 39 misclassified · lexicon v2.0, 38 families",
     13, MUTED, MONO, first=True, line=1.5)
para(tf, "4 September 2026", 13, MUTED, MONO, space_before=3)

# ============================================================== 2 what we did
s = slide(); eyebrow(s, "Method"); title(s, "What we did")
rule_line(s, 1.68)
steps = [
 ("Wrote the lexicon before opening the sources",
  "36 regex token families, 6 to 8 per category, from the standard empirical taxonomy "
  "of flaky-test root causes. Applied identically to every slice, so a body-versus-context "
  "difference is a property of the code, not of the lexicon."),
 ("Sliced each test class six ways",
  "body, static fields, fixture bodies, sibling tests, helpers the body actually calls, "
  "and context meaning the last four combined. Comments and string literals blanked by a "
  "single-pass scanner first."),
 ("Scored by distinct families present, not raw counts",
  "Context is far longer than a body. Counting occurrences would reward length rather than "
  "signal, so each family counts once."),
 ("Ran five tests, weakest to strongest",
  "coverage of the true category, a zero-training argmax proxy, a flip analysis on the "
  "model's errors, a scikit-learn linear classifier with cross-validation and a "
  "label-permutation null, and baselines with random tie-breaking."),
]
y = 1.98
for i, (t, d) in enumerate(steps, 1):
    para(tb(s, M, y, 0.45, 0.4), str(i), 15, MUTED, MONO, first=True)
    para(tb(s, M + 0.48, y - 0.03, 11.3, 0.45), t, 17, INK, BODY, bold=True, first=True)
    para(tb(s, M + 0.48, y + 0.34, 11.2, 0.85), d, 14, INK2, BODY, first=True, line=1.26)
    y += 1.28
    if i < 4: rule_line(s, y - 0.20)
footer(s, 2)

# ============================================================== worked example
s = slide(); eyebrow(s, "Worked example · TestDFSIO.testRead")
title(s, "One test, end to end")
cur = pill(s, M, 1.56, "order dependency", UP, UPSOFT)
para(tb(s, cur + 0.12, 1.58, 0.9, 0.28), "read as", 12, MUTED, BODY, italic=True,
     first=True)
pill(s, cur + 0.95, 1.56, "time", DOWN, DOWNSOFT)

para(tb(s, M, 2.10, 6.0, 0.3), "The body FlakyLens actually saw", 14, INK, BODY,
     bold=True, first=True)
code(s, M, 2.48, 6.1, [
 ("public void testRead() throws Exception {", "plain"),
 ("  FileSystem fs = cluster.getFileSystem();", "plain"),
 ("  long tStart = System.currentTimeMillis();", "hi"),
 ("  bench.readTest(fs);", "plain"),
 ("  long execTime = System.currentTimeMillis()", "hi"),
 ("                  - tStart;", "hi"),
 ("  bench.analyzeResult(fs, TEST_TYPE_READ,", "plain"),
 ("                      execTime);", "plain"),
 ("}", "plain"),
], size=11.5)

para(tb(s, M + 6.45, 2.10, 5.8, 0.3), "Score: distinct families present", 14,
     INK, BODY, bold=True, first=True)
code(s, M + 6.45, 2.48, 5.75, [
 ("slice        async  conc  time    uc    od", "dim"),
 ("body             0     0     1     0     1", "plain"),
 ("fields           0     0     0     0     2", "plain"),
 ("fixtures         0     0     0     0     3", "plain"),
 ("helpers          0     0     2     0     3", "plain"),
 ("", "plain"),
 ("body only            time=1 od=1  tie, wrong", "hi"),
 ("body + fields/fixtures      od=5  CORRECT", "acc"),
 ("body + full context         od=5  CORRECT", "acc"),
], size=11.5)

note(s, 5.45, "The body holds a wall-clock idiom twice, which is exactly why the model "
              "answers time. The static cluster and the @BeforeClass that calls testWrite "
              "hold five order-dependency families and never reach the model.",
     INK, 14.5, x=M, w=W - 2 * M)
rect(s, M, 6.28, W - 2 * M, 0.92, DOWNSOFT)
rect(s, M, 6.28, 0.05, 0.92, DOWN)
para(tb(s, M + 0.32, 6.44, W - 2 * M - 0.7, 0.7),
     "Provenance matters: the commit pinned in the benchmark holds a refactored version "
     "of this test reading \"long execTime = bench.readTest(fs)\", with no clock call at "
     "all. Scoring against that copy would have hidden why the model said time.",
     13.5, INK2, BODY, first=True, line=1.26)
footer(s, 3)

# ============================================================== 3 headline
s = slide(); eyebrow(s, "Result"); title(s, "The finding")
rule_line(s, 1.68)
cards = [("+0.138", UP, "Macro-F1 gained by adding fields and fixtures. 95% CI [+0.109, +0.164]"),
         ("49%", ACC, "Tests whose true category is absent from the body and present in the context"),
         ("15 → 76%", UP, "Order-dependency recall, body only against body plus fields and fixtures"),
         ("0 of 4", DOWN, "Other categories that improve. Two of them get worse")]
cw = (W - 2 * M - 3 * 0.22) / 4
for i, (n, c, l) in enumerate(cards):
    x = M + i * (cw + 0.22)
    rect(s, x, 2.05, cw, 2.20, SUNK)
    para(tb(s, x + 0.24, 2.30, cw - 0.4, 0.9), n, 40, c, DISP, bold=True,
         first=True, line=1.0)
    para(tb(s, x + 0.24, 3.20, cw - 0.48, 0.95), l, 13, INK2, BODY, first=True, line=1.24)
rect(s, M, 4.68, W - 2 * M, 1.02, DOWNSOFT)
rect(s, M, 4.68, 0.05, 1.02, DOWN)
para(tb(s, M + 0.32, 4.88, W - 2 * M - 0.7, 0.8),
     "Read this as \"context helps order dependency\", not \"context helps\". "
     "Nothing here shows a gain for async wait, concurrency, time or unordered "
     "collections. On this sample the first two get worse.",
     15.5, INK, BODY, bold=True, first=True, line=1.28)
note(s, 6.00, "Independent confirmation: of the 6 errors the proxy recovers, 5 are cases "
              "found by hand in investigation 1, by a different method answering a "
              "different question.", INK2, 15)
footer(s, 4)

# ============================================================== 4 macro-F1 chart
s = slide(); eyebrow(s, "Five-way flaky category task")
title(s, "Macro-F1 by what the classifier is fed")
rule_line(s, 1.68)
para(tb(s, M, 1.90, 8, 0.3),
     "Same 80 tests, same metric, ties broken at random over 2,000 draws.",
     14, MUTED, BODY, first=True)
# legend
rect(s, M, 2.32, 0.16, 0.16, S_BODY)
para(tb(s, M + 0.26, 2.26, 1.6, 0.3), "token proxy", 13, INK2, BODY, first=True)
rect(s, M + 1.85, 2.32, 0.16, 0.16, S_REF)
para(tb(s, M + 2.11, 2.26, 1.8, 0.3), "reference point", 13, INK2, BODY, first=True)

X0, SCALE = 4.30, 18.0          # inches; 0.40 macro-F1 spans 7.2 in
bars = [("majority class", 0.146, 57.5, S_REF),
        ("body only", 0.211, 22.5, S_BODY),
        ("body + full context", 0.326, 38.8, S_BODY),
        ("body + fields + fixtures", 0.442, 57.5, S_BODY),
        ("FlakyLens, shipped", 0.368, 51.2, S_REF)]
for gi, gv in enumerate([0.10, 0.20, 0.30, 0.40]):
    gx = X0 + gv * SCALE
    rect(s, gx, 2.72, 1 / 72.0, 3.05, RULE)
    para(tb(s, gx - 0.35, 5.83, 0.7, 0.3), "%.2f" % gv, 11, MUTED, MONO,
         first=True, align=PP_ALIGN.CENTER)
para(tb(s, X0 - 0.35, 5.83, 0.7, 0.3), "0", 11, MUTED, MONO, first=True,
     align=PP_ALIGN.CENTER)
para(tb(s, X0 + 3.2, 6.08, 1.4, 0.3), "macro-F1", 11.5, MUTED, MONO, first=True)
by = 2.82
for lab, v, acc, col in bars:
    best = lab.startswith("body + fields")
    para(tb(s, M, by - 0.02, 3.45, 0.32), lab, 14, INK if best else INK2, BODY,
         bold=best, first=True, align=PP_ALIGN.RIGHT)
    rect(s, X0, by, v * SCALE, 0.30, col)
    para(tb(s, X0 + v * SCALE + 0.12, by - 0.01, 1.9, 0.32),
         "%.3f" % v, 13, INK, MONO, bold=True, first=True)
    para(tb(s, X0 + v * SCALE + 0.80, by - 0.01, 1.9, 0.32),
         "· %.1f%% acc" % acc, 12, MUTED, MONO, first=True)
    by += 0.58
note(s, 6.45, "Trained macro-F1 (scikit-learn): 0.253 body only, 0.391 with fields "
              "and fixtures, 0.382 with full context; both beat a permutation null at p <= 0.007. "
              "The FlakyLens bar is not like-for-like: "
              "these 80 tests over-represent projects where classes could be located.",
     MUTED, 13.5)
footer(s, 5)

# ============================================================== 5 per category
s = slide(); eyebrow(s, "Per-category recall")
title(s, "All of the gain is one category")
rule_line(s, 1.68)
dot(s, M + 0.10, 2.05, 0.075, S_BODY)
para(tb(s, M + 0.30, 1.92, 1.5, 0.3), "body only", 13, INK2, BODY, first=True)
dot(s, M + 1.85, 2.05, 0.075, S_CTX)
para(tb(s, M + 2.05, 1.92, 2.8, 0.3), "body + fields + fixtures", 13, INK2, BODY, first=True)

X1, SC = 4.60, 0.072            # 100% spans 7.2 in
rows = [("test order dependency", 46, 15, 76, True),
        ("async wait", 18, 39, 33, False),
        ("concurrency", 10, 10, 20, False),
        ("time", 4, 50, 50, False),
        ("unordered collections", 2, 50, 50, False)]
for gv in [0, 25, 50, 75, 100]:
    gx = X1 + gv * SC
    rect(s, gx, 2.42, 1 / 72.0, 3.30, RULE)
    para(tb(s, gx - 0.4, 5.80, 0.8, 0.3), "%d%%" % gv if gv else "0", 11, MUTED,
         MONO, first=True, align=PP_ALIGN.CENTER)
para(tb(s, X1 + 3.0, 6.05, 1.4, 0.3), "recall", 11.5, MUTED, MONO, first=True)
ry = 2.60
for lab, n, b, c, big in rows:
    para(tb(s, M, ry - 0.10, 3.75, 0.30), lab, 14, INK if big else INK2, BODY,
         bold=big, first=True, align=PP_ALIGN.RIGHT)
    para(tb(s, M, ry + 0.16, 3.75, 0.26), "n=%d" % n, 11, MUTED, MONO,
         first=True, align=PP_ALIGN.RIGHT)
    xb, xc = X1 + b * SC, X1 + c * SC
    if b != c:
        lo, hi = sorted([xb, xc])
        rect(s, lo, ry + 0.045, hi - lo, 0.03, UP if c > b else DOWN)
    dot(s, xb, ry + 0.06, 0.085, S_BODY, WHITE)
    if b == c:
        dot(s, xc, ry + 0.06, 0.042, S_CTX)
        para(tb(s, xc + 0.20, ry - 0.06, 2.4, 0.3), "50%, unchanged", 12.5,
             MUTED, MONO, first=True)
    else:
        dot(s, xc, ry + 0.06, 0.085, S_CTX, WHITE)
        if c > b:
            para(tb(s, xc + 0.18, ry - 0.06, 1.0, 0.3), "%d%%" % c, 13, UP,
                 MONO, bold=True, first=True)
            para(tb(s, xb - 1.15, ry - 0.06, 1.0, 0.3), "%d%%" % b, 13, MUTED,
                 MONO, first=True, align=PP_ALIGN.RIGHT)
        elif xc - 1.15 > M + 3.90:
            para(tb(s, xc - 1.15, ry - 0.06, 1.0, 0.3), "%d%%" % c, 13, DOWN,
                 MONO, bold=True, first=True, align=PP_ALIGN.RIGHT)
            para(tb(s, xb + 0.18, ry - 0.06, 1.0, 0.3), "%d%%" % b, 13, MUTED,
                 MONO, first=True)
        else:
            # context dot sits too near the axis for a left-hand label
            tfc = tb(s, max(xb, xc) + 0.20, ry - 0.06, 2.2, 0.3)
            p = tfc.paragraphs[0]
            r1 = p.add_run(); r1.text = "%d%% → " % b
            r1.font.size = Pt(13); r1.font.name = MONO; r1.font.color.rgb = MUTED
            r2 = p.add_run(); r2.text = "%d%%" % c
            r2.font.size = Pt(13); r2.font.name = MONO; r2.font.bold = True
            r2.font.color.rgb = DOWN
    ry += 0.64
note(s, 6.30, "With the full context instead, order dependency reaches only 52% and concurrency "
              "drops to 0, because helper and sibling text pulls tests back. Async wait loses "
              "either way, so context must enter as separate feature groups. Time and "
              "unordered collections have 4 and 2 examples and carry no weight.", INK2, 14)
footer(s, 6)

# ============================================================== 6 coverage
s = slide(); eyebrow(s, "Coverage")
title(s, "Where the true category actually appears")
rule_line(s, 1.68)
note(s, 1.92, "Share of the 80 tests whose true category has at least one lexicon family "
              "present in a given slice.", MUTED, 14)
table(s, M, 2.42,
      ["Slice", "All 80", "Model wrong (39)", "Model right (41)", "Gap"],
      [4.4, 1.7, 2.3, 2.3, 1.2],
      [("body", "48%", "51%", "44%", "+7"),
       ("fields", "30%", "49%", "12%", "+37"),
       ("fixtures", "42%", "46%", "39%", "+7"),
       ("siblings", "75%", "74%", "76%", "−2"),
       ("helpers", "15%", "23%", "7%", "+16"),
       ("context, all four", "86%", "85%", "88%", "−3")],
      highlight={1}, aligns=["l", "r", "r", "r", "r"])
note(s, 5.55, "The fields row is the finding. Static field declarations carry the true "
              "category's vocabulary four times more often for the tests the model gets "
              "wrong than for the tests it gets right.", INK, 15.5)
note(s, 6.35, "Siblings carry it for three quarters of everything, so this measure does not "
              "separate them, though they still classify well alone. For 35 of 80 tests the "
              "true category is absent from the body and present in the context.", MUTED, 13.5)
footer(s, 7)

# ============================================================== 7 binary
s = slide(); eyebrow(s, "Binary task")
title(s, "Order dependency against everything else")
rule_line(s, 1.68)
note(s, 1.92, "Cleaner than the five-way task given the class skew, and here the full "
              "context wins by a wide margin.", MUTED, 14)
table(s, M, 2.42, ["Slice", "AUC", "Best accuracy"], [5.6, 2.0, 2.4],
      [("body only", "0.723", "72.5%"),
       ("body + fixtures", "0.834", "77.5%"),
       ("body + siblings", "0.824", "78.8%")],
      highlight={2}, aligns=["l", "r", "r"])
rect(s, M, 4.35, W - 2 * M, 1.02, ACCSOFT)
rect(s, M, 4.35, 0.05, 1.02, ACC)
para(tb(s, M + 0.32, 4.56, W - 2 * M - 0.7, 0.8),
     "Sibling tests and called helpers do carry order-dependency signal. They "
     "simply cannot be thrown into a single five-way bag without costing the "
     "other categories.", 15.5, ACC, BODY, bold=True, first=True, line=1.28)
note(s, 5.70, "Recovered by fields + fixtures among the 39 the model got wrong: 13 gained, 0 lost.",
     MUTED, 14)
code(s, M, 6.02, W - 2 * M - 0.95, [
 ("TestPathData.testCwdContents / testQualifiedUriContents / testUnqualifiedUriContents  OD, said UC", "hi"),
 ("TestRPCCompatibility.testVersion2ClientVersion2Server                                 OD, said async", "hi"),
 ("TestDelegationTokenForProxyUser.testDelegationTokenWithRealUser                       OD, said conc", "hi"),
 ("ProvisioningServiceTest.testCancelDeprovision                                         OD, said async", "hi"),
 ("lost: TestFrameworkTestRun.testAppWithServices                                        conc", "plain"),
], size=10.5)
footer(s, 8)

# ============================================================== 8 sample
s = slide(); eyebrow(s, "Sample")
title(s, "80 of 116 flaky tests located")
rule_line(s, 1.68)
table(s, M, 2.02,
      ["Project", "Flaky", "Located", "Analysed", "Model wrong"],
      [4.4, 1.7, 1.9, 1.9, 2.0],
      [("apache/hadoop", 33, 27, 27, 17),
       ("wildfly/wildfly", 42, 24, 24, 7),
       ("apache/pulsar", 22, 16, 16, 5),
       ("cdapio/cdap", 11, 9, 9, 7),
       ("neo4j/neo4j", 8, 4, 4, 3),
       ("total", 116, 80, 80, 39)],
      highlight={5}, aligns=["l", "r", "r", "r", "r"])
rect(s, M, 5.20, W - 2 * M, 1.30, DOWNSOFT)
rect(s, M, 5.20, 0.05, 1.30, DOWN)
tf = tb(s, M + 0.32, 5.40, W - 2 * M - 0.7, 1.0)
para(tf, "A benchmark data-quality problem worth raising on its own", 15.5, DOWN,
     BODY, bold=True, first=True)
para(tf, "Wildfly rows name each test as a commit hash followed by a method name, with no "
         "class at all. 24 were recovered by searching a checked-out tree for a unique "
         "@Test declaration, 11 matched several classes and were dropped as ambiguous, "
         "and 7 were not found.", 14, INK2, BODY, space_before=5, line=1.26)
footer(s, 9)

# ============================================================== callees
s = slide(); eyebrow(s, "Fourth extraction target")
title(s, "Production callees at depth 1 do not help")
rule_line(s, 1.68)
note(s, 1.90, "Calls resolved by receiver type against the project's own main tree. "
              "78 of 80 tests resolve a callee, median 2.", MUTED, 14)
table(s, M, 2.35, ["Measure", "fields + fixtures", "+ callees"],
      [5.2, 2.8, 2.2],
      [("argmax accuracy", "55.0%", "51.2%"),
       ("trained macro-F1", "0.389", "0.384"),
       ("binary order dependency, AUC", "0.697", "0.672"),
       ("order-dependency recall", "70%", "65%"),
       ("errors recovered of 39", "12", "11")],
      size=13.5, aligns=["l", "r", "r"])
rect(s, M + 10.6, 2.35, 1.9, 2.58, DOWNSOFT)
_tf = tb(s, M + 10.6, 3.20, 1.9, 0.9, MSO_ANCHOR.MIDDLE)
for _i, _w in enumerate(["every", "measure", "worse"]):
    para(_tf, _w, 15, DOWN, BODY, bold=True, first=(_i == 0),
         align=PP_ALIGN.CENTER, line=1.2)

rect(s, M, 5.08, W - 2 * M, 0.80, ACCSOFT)
rect(s, M, 5.08, 0.05, 0.80, ACC)
para(tb(s, M + 0.32, 5.24, W - 2 * M - 0.7, 0.65),
     "But the signal is there: callees carry the true category for 33% of the misses "
     "against 5% of the hits, the second largest gap of any slice. Concurrency recall "
     "is the one category that improves, 10% to 20%.",
     15, ACC, BODY, bold=True, first=True, line=1.26)

para(tb(s, M, 6.02, 5.9, 0.3), "Why it fails as a bag", 14, INK, BODY, bold=True,
     first=True)
para(tb(s, M, 6.32, 5.9, 0.7),
     "TestPeerCache at depth 1 resolves put, size and close: one synchronized keyword. "
     "The daemon and Thread.sleep sit at depth 2.", 13, INK2, BODY, first=True, line=1.24)
para(tb(s, M + 6.45, 6.02, 5.0, 0.3), "What to change", 14, INK, BODY, bold=True,
     first=True)
para(tb(s, M + 6.45, 6.32, 5.0, 0.7),
     "Expand to depth 2, keep callees a separate feature group, and expect the gain in "
     "concurrency rather than order dependency.", 13, INK2, BODY, first=True, line=1.24)
footer(s, 10)

# ============================================================== 9 plan
s = slide(); eyebrow(s, "Implication")
title(s, "What this changes about the extraction plan")
rule_line(s, 1.68)
note(s, 1.90, "Investigation 1 ranked extraction targets by how many misses they reach. "
              "This adds what each is worth, and one correction.", MUTED, 14)
items = [("Static fields and fixtures pay first and pay most", "+0.138",
          "They deliver the entire measured gain on their own, and they are the cheapest "
          "thing in the plan to extract. No symbol resolution, no call graph, no build."),
         ("Keep the slices as separate feature groups", "correction",
          "Concatenating everything into one token stream costs accuracy on async wait and "
          "concurrency. The ordering from investigation 1 stands; the packaging is what "
          "changes."),
         ("Sibling tests need a targeted feature, not their text", "0.66 → 0.81",
          "They lift the binary order-dependency AUC from 0.66 to 0.81 but dilute the five-way "
          "task. The feature that matters is which siblings write the static fields this test reads.")]
y = 2.35
for i, (t, tag, d) in enumerate(items, 1):
    para(tb(s, M, y + 0.02, 0.4, 0.35), str(i), 15, MUTED, MONO, first=True)
    para(tb(s, M + 0.45, y, 8.3, 0.35), t, 17.5, INK, BODY, bold=True, first=True)
    ww = 0.105 * len(tag) + 0.30
    rect(s, W - M - ww, y + 0.02, ww, 0.30, ACCSOFT)
    para(tb(s, W - M - ww, y + 0.04, ww, 0.28, MSO_ANCHOR.MIDDLE), tag, 12, ACC,
         MONO, bold=True, first=True, align=PP_ALIGN.CENTER)
    para(tb(s, M + 0.45, y + 0.42, 11.0, 0.8), d, 14, INK2, BODY, first=True, line=1.26)
    y += 1.42
    if i < 3: rule_line(s, y - 0.24)
footer(s, 11)

# ============================================================== stats slide
s = slide(); eyebrow(s, "Statistics and tooling")
title(s, "Why the library choice changed the numbers")
rule_line(s, 1.68)
note(s, 1.90, "scikit-learn 1.9.0 and scipy 1.18.1, both pinned in the project requirements. "
              "A numpy implementation is kept only as a cross-check.", MUTED, 14)
para(tb(s, M, 2.35, 5.9, 0.3), "Same data, same splits, two implementations", 14,
     INK, BODY, bold=True, first=True)
table(s, M, 2.70, ["Configuration", "numpy", "sklearn", "diff"],
      [3.0, 1.0, 1.1, 0.9],
      [("body only", "0.244", "0.261", "+0.017"),
       ("+ fields + fixtures", "0.392", "0.351", "-0.041"),
       ("+ full context", "0.305", "0.360", "+0.055")],
      size=13, aligns=["l", "r", "r", "r"])

para(tb(s, M + 6.45, 2.35, 5.8, 0.3), "Label-permutation null, 300 shuffles", 14,
     INK, BODY, bold=True, first=True)
table(s, M + 6.45, 2.70, ["Configuration", "Observed", "Null", "p"],
      [2.6, 1.3, 0.9, 1.0],
      [("body only", "0.305", "0.158", "0.007"),
       ("+ fields + fixtures", "0.423", "0.181", "<=0.003"),
       ("+ full context", "0.339", "0.178", "<=0.003")],
      size=13, highlight={1}, aligns=["l", "r", "r", "r"])

note(s, 4.60, "The two models disagree by up to 0.055 macro-F1 on identical data. A "
              "hand-rolled gradient-descent model is not reliable at the third decimal "
              "and cannot be defended in a paper. Everything reported now comes from "
              "scikit-learn.", INK, 14.5)
rect(s, M, 5.52, W - 2 * M, 1.42, DOWNSOFT)
rect(s, M, 5.52, 0.05, 1.42, DOWN)
tf = tb(s, M + 0.32, 5.68, W - 2 * M - 0.7, 1.2)
para(tf, "Three honest weaknesses in the statistics", 15.5, DOWN, BODY, bold=True,
     first=True)
para(tf, "The bootstrap resamples fold scores drawn from the same 80 tests, so it is "
         "correlated and optimistic. Folds collapse to 2, not 5, because the split count "
         "is capped by the smallest class and unordered collections has 2 examples. And "
         "\"best accuracy\" in the binary task fits its threshold in-sample, so quote the "
         "AUC and the Mann-Whitney p-value instead.",
     13.5, INK2, BODY, space_before=4, line=1.24)
footer(s, 12)

# ============================================================== 10 caveats
s = slide(); eyebrow(s, "Caveats"); title(s, "What this does not show")
rule_line(s, 1.68)
cav = [("A lexicon is not an encoder",
        "A 36-family regex bag is a floor. It shows the signal is present and "
        "machine-readable in the context slices. It does not predict what a fine-tuned "
        "transformer would gain and should not be quoted as an expected improvement."),
       ("The class distribution is badly skewed",
        "Order dependency is 46 of 80, unordered collections is 2, time is 4. Macro-F1 over "
        "five classes at those counts is unstable. The binary result is the more trustworthy "
        "summary of the same effect."),
       ("The proxy beating the shipped model is not a result",
        "57.5% against 51.2% on these 80 tests, but the subset over-represents projects "
        "where localisation succeeded and is order-dependency heavy. Not like for like."),
       ("Localisation loses a third of the sample",
        "Every conclusion is conditioned on tests whose class could be found, which may not "
        "be a random subset of the benchmark.")]
y = 2.02
for t, d in cav:
    rect(s, M, y, 0.05, 0.92, DOWN)
    para(tb(s, M + 0.28, y - 0.02, 11.4, 0.35), t, 16.5, INK, BODY, bold=True, first=True)
    para(tb(s, M + 0.28, y + 0.34, 11.3, 0.75), d, 13.5, INK2, BODY, first=True, line=1.24)
    y += 1.20
para(tb(s, M, 6.95, 12.2, 0.35),
     "Working files: docs/investigation2/   ·   Investigation 1: docs/investigation/",
     12.5, MUTED, MONO, first=True)
footer(s, 13)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   "FlakyLens_token_proxy.pptx")
prs.save(out)
print("saved", os.path.abspath(out), os.path.getsize(out), "bytes")
