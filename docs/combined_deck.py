"""Combined investigation 1 + 2 deck for the supervisor meeting.

Formal and minimal: process over findings. Writes ../FlakyLens_progress.pptx
relative to docs/.
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
import os

INK    = RGBColor(0x15, 0x1A, 0x21)
INK2   = RGBColor(0x3D, 0x46, 0x53)
MUTED  = RGBColor(0x6B, 0x76, 0x84)
ACC    = RGBColor(0x2F, 0x48, 0x58)
HI     = RGBColor(0xA8, 0x45, 0x2B)
RULE   = RGBColor(0xD5, 0xDA, 0xE1)
SUNK   = RGBColor(0xF0, 0xF2, 0xF5)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
CODEBG = RGBColor(0xF4, 0xF6, 0xF8)
ACCSOFT = RGBColor(0xE6, 0xEC, 0xF0)
S_REF   = RGBColor(0x9A, 0xA4, 0xAF)   # recessive bar, "before" series
UP      = RGBColor(0x3A, 0x66, 0x50)

BODY = "Calibri"; MONO = "Consolas"
RENDER = 1.23

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
W, H, M = 13.333, 7.5, 0.85


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


def para(tf, text, size, color, font=BODY, bold=False, first=False,
         italic=False, line=None, align=None, space_before=0):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.space_after = Pt(0); p.space_before = Pt(space_before)
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


def head(s, eyebrow_text, title_text):
    para(tb(s, M, 0.46, 11.5, 0.3), eyebrow_text.upper(), 10.5, MUTED, MONO,
         first=True)
    para(tb(s, M, 0.84, 11.8, 0.8), title_text, 28, INK, BODY, bold=True,
         first=True, line=1.05)
    rect(s, M, 1.62, W - 2 * M, 1 / 72.0, RULE)


def footer(s, n):
    para(tb(s, W - 1.5, H - 0.5, 0.9, 0.3), str(n), 10, MUTED, MONO,
         first=True, align=PP_ALIGN.RIGHT)


def note(s, y, text, color=INK2, size=14.5, x=M, w=W - 2 * M, h=0.9):
    para(tb(s, x, y, w, h), text, size, color, BODY, first=True, line=1.28)


def code(s, x, y, w, lines, size=12, pad=0.16, lh=1.28, lang=None):
    h = pad * 2 + len(lines) * (size * lh * RENDER / 72.0)
    rect(s, x, y, w, h, CODEBG, RULE)
    tf = tb(s, x + pad, y + pad, w - 2 * pad, h - 2 * pad)
    for i, item in enumerate(lines):
        t, st = item if isinstance(item, tuple) else (item, "plain")
        col = {"plain": INK2, "hi": HI, "dim": MUTED, "acc": ACC}[st]
        para(tf, t or " ", size, col, MONO, bold=(st in ("hi", "acc")),
             italic=(st == "dim"), first=(i == 0), line=lh)
    return y + h


def caption(s, x, y, w, text):
    para(tb(s, x, y, w, 0.3), text, 12.5, MUTED, BODY, first=True)


def table(s, x, y, cols, widths, rows, size=13, rh=0.40, highlight=None,
          aligns=None, head_size=10.5):
    aligns = aligns or ["l"] * len(cols)
    total = sum(widths)
    rect(s, x, y, total, 0.38, SUNK)
    cx = x
    for c, wd, al in zip(cols, widths, aligns):
        para(tb(s, cx + 0.12, y + 0.08, wd - 0.24, 0.26), c.upper(), head_size,
             MUTED, MONO, bold=True, first=True,
             align=PP_ALIGN.RIGHT if al == "r" else PP_ALIGN.LEFT)
        cx += wd
    yy = y + 0.46
    for i, row in enumerate(rows):
        if highlight is not None and i in highlight:
            rect(s, x, yy - 0.06, total, rh - 0.02, ACCSOFT)
        cx = x
        for v, wd, al in zip(row, widths, aligns):
            bold = highlight is not None and i in highlight
            para(tb(s, cx + 0.12, yy, wd - 0.24, 0.28), str(v), size,
                 INK if bold else INK2, MONO if al == "r" else BODY,
                 bold=bold, first=True,
                 align=PP_ALIGN.RIGHT if al == "r" else PP_ALIGN.LEFT)
            cx += wd
        yy += rh
        rect(s, x, yy - 0.09, total, 1 / 72.0, RULE)
    return yy


# =========================================================== 1  what I did
s = slide()
para(tb(s, M, 0.60, 11.5, 0.3), "FLAKYLENS · PROGRESS REPORT · 4 SEPTEMBER 2026",
     11, MUTED, MONO, first=True)
para(tb(s, M, 1.10, 11.5, 0.7), "What I did so far", 34, INK, BODY, bold=True,
     first=True)
rect(s, M, 1.95, W - 2 * M, 1 / 72.0, RULE)

note(s, 2.25, "Manually read 27 flaky tests from apache/hadoop at the commits pinned "
              "in the benchmark, and asked one question of each: where in the project "
              "is the fact that makes the true label true?", INK, 16)

para(tb(s, M, 3.20, 11.5, 0.3), "Four kinds of context turned up, none of them in "
     "the test method the model reads:", 15, INK2, BODY, first=True)

items = [("Fields", "class-level declarations, especially static ones, shared by every test"),
         ("Fixtures", "@Before / @After / @BeforeClass / @AfterClass method bodies"),
         ("Sibling tests", "the other @Test methods in the same class"),
         ("Depth-1 callees", "production methods the test invokes")]
y = 3.85
for i, (t, d) in enumerate(items, 1):
    para(tb(s, M, y, 0.4, 0.3), str(i), 14, MUTED, MONO, first=True)
    para(tb(s, M + 0.45, y - 0.03, 2.7, 0.3), t, 16, INK, BODY, bold=True, first=True)
    para(tb(s, M + 3.30, y - 0.02, 8.2, 0.3), d, 14.5, INK2, BODY, first=True)
    y += 0.55

rect(s, M, 6.20, W - 2 * M, 0.72, ACCSOFT)
rect(s, M, 6.20, 0.05, 0.72, ACC)
para(tb(s, M + 0.30, 6.40, 11.2, 0.5),
     "The next four slides show one real example of each.",
     15, ACC, BODY, bold=True, first=True)
footer(s, 1)

# =========================================================== 2  fields
s = slide()
head(s, "Context type 1 of 4", "Fields")
note(s, 1.90, "Class-level declarations. A static field is state that outlives a "
              "single test, which is the definition of an order dependency.", MUTED)
caption(s, M, 2.50, 6.0, "apache/hadoop · TestDFSIO")
code(s, M, 2.82, 6.0, [
 ("private static MiniDFSCluster cluster;", "hi"),
 ("private static TestDFSIO bench;", "hi"),
], size=13)
caption(s, M + 6.35, 2.50, 5.4, "apache/hadoop · TestPathData")
code(s, M + 6.35, 2.82, 5.4, [
 ("private static final String TEST_ROOT_DIR =", "hi"),
 ("    GenericTestUtils.getTestDir(\"testPD\")", "hi"),
 ("                    .getAbsolutePath();", "hi"),
 ("protected Configuration conf;", "plain"),
], size=12)
note(s, 4.35, "Both classes share one cluster and one directory across every test in "
              "the file. Nothing in the test method says so.", INK, 15)
rect(s, M, 5.15, W - 2 * M, 1.55, SUNK)
para(tb(s, M + 0.30, 5.38, 11.0, 1.2),
     "Why it matters", 14.5, INK, BODY, bold=True, first=True)
para(tb(s, M + 0.30, 5.70, 11.0, 0.9),
     "TestDFSIO has five flaky tests, all labelled order dependency, and the model "
     "predicted \"time\" for all five. The static cluster is the shared state they "
     "contend over. It is 40 lines above the test method and never reaches the encoder.",
     14, INK2, BODY, first=True, line=1.26)
footer(s, 2)

# =========================================================== 3  fixtures
s = slide()
head(s, "Context type 2 of 4", "Fixtures")
note(s, 1.90, "Methods JUnit runs automatically around each test. This is where a "
              "test's real preconditions live.", MUTED)
caption(s, M, 2.45, 11.6, "apache/hadoop · TestPathData")
code(s, M, 2.77, 11.6, [
 ("@Before", "dim"),
 ("public void initialize() throws Exception {", "plain"),
 ("  conf = new Configuration();", "plain"),
 ("  fs = FileSystem.getLocal(conf);          // process-wide cache", "plain"),
 ("  testDir = new Path(TEST_ROOT_DIR);", "plain"),
 ("  fs.mkdirs(testDir);", "plain"),
 ("  FileSystem.setDefaultUri(conf, fs.getUri());", "hi"),
 ("  fs.setWorkingDirectory(testDir);", "hi"),
 ("  fs.mkdirs(new Path(\"d1\"));", "plain"),
 ("  fs.createNewFile(new Path(\"d1\", \"f1\"));", "plain"),
 ("}", "plain"),
], size=12.5)
note(s, 5.85, "Two highlighted lines mutate process-global state on a FileSystem "
              "instance that Hadoop hands out from a shared cache. Whether a class "
              "resets state between tests is answerable only from here.", INK, 15)
footer(s, 3)

# =========================================================== 4  siblings
s = slide()
head(s, "Context type 3 of 4", "Sibling tests")
note(s, 1.90, "The other @Test methods in the same class. An order dependency is by "
              "definition a relationship between tests, so it cannot be seen from one "
              "test alone.", MUTED)
caption(s, M, 2.55, 11.6, "apache/hadoop · TestDFSIO · the class fixture and one sibling")
code(s, M, 2.87, 11.6, [
 ("@BeforeClass", "dim"),
 ("public static void beforeClass() throws Exception {", "plain"),
 ("  cluster = new MiniDFSCluster.Builder(bench.getConf()).build();", "plain"),
 ("  bench.createControlFile(fs, DEFAULT_NR_BYTES, DEFAULT_NR_FILES);", "plain"),
 ("  /** Check write here, as it is required for other tests */", "hi"),
 ("  testWrite();                       // writes what testRead will read", "hi"),
 ("}", "plain"),
 ("", "plain"),
 ("public void testReadRandom() throws Exception {", "plain"),
 ("  bench.getConf().setLong(\"test.io.skip.size\", 0);   // shared static bench", "hi"),
 ("}", "plain"),
], size=12.5)
note(s, 6.00, "The fixture states the dependency in a comment, and a sibling test writes "
              "a configuration key into the shared static object that the others read.",
     INK, 15)
footer(s, 4)

# =========================================================== 5  depth-1 callee
s = slide()
head(s, "Context type 4 of 4", "Depth-1 callees, and where the depth runs out")
note(s, 1.86, "Production methods the test invokes. Some test classes contain no context "
              "at all: TestPeerCache has no static field, no fixture and no threading "
              "vocabulary anywhere in it.", MUTED, 13.5)
caption(s, M, 2.48, 5.3, "the test")
code(s, M, 2.78, 5.3, [
 ("public void testExpiry() throws Exception {", "plain"),
 ("  PeerCache cache =", "plain"),
 ("      new PeerCache(CAPACITY, EXPIRY_PERIOD);", "plain"),
 ("  cache.put(dnIds[i], peers[i]);", "acc"),
 ("  assertEquals(0, cache.size());", "plain"),
 ("}", "plain"),
], size=11.5)

caption(s, M + 5.85, 2.48, 6.0, "what the call chain reaches, by depth")
code(s, M + 5.85, 2.78, 6.0, [
 ("depth 1  PeerCache.put(DatanodeID, Peer)", "acc"),
 ("           if (peer.isClosed()) return;", "plain"),
 ("           putInternal(dnId, peer);", "plain"),
 ("depth 2  putInternal(...)", "plain"),
 ("           startExpiryDaemon();", "plain"),
 ("depth 3  startExpiryDaemon()", "hi"),
 ("           daemon = new Daemon(new Runnable(){..});", "hi"),
 ("           daemon.start();", "hi"),
 ("depth 4  run()    <- not a call edge", "hi"),
 ("           for (..; Thread.sleep(expiryPeriod))", "hi"),
], size=11.5)

note(s, 4.65, "Depth 1 returns only put, which holds nothing that separates this test "
              "from an async-wait test. The daemon appears at depth 3 and the "
              "Thread.sleep loop at depth 4.", INK, 14, x=M, w=5.3, h=1.2)
rect(s, M, 6.08, W - 2 * M, 0.86, SUNK)
para(tb(s, M + 0.30, 6.26, 11.0, 0.7),
     "The last hop is not a method call at all: startExpiryDaemon constructs an "
     "anonymous Runnable and hands it to a thread. No call-graph traversal follows "
     "that edge at any depth, which is a modelling decision rather than a depth "
     "setting.", 13.5, INK2, BODY, first=True, line=1.24)
footer(s, 5)

# =========================================================== 6  extraction setup
s = slide()
head(s, "Scaling up", "Setup for context extraction")
para(tb(s, M, 1.88, 5.6, 0.3), "Sample", 14.5, INK, BODY, bold=True, first=True)
table(s, M, 2.20, ["Project", "Flaky", "Located"], [2.7, 1.2, 1.4],
      [("apache/hadoop", 33, 27), ("wildfly/wildfly", 42, 24),
       ("apache/pulsar", 22, 16), ("cdapio/cdap", 11, 9),
       ("neo4j/neo4j", 8, 4), ("total", 116, 80)],
      size=12.5, rh=0.36, highlight={5}, aligns=["l", "r", "r"])
para(tb(s, M, 5.05, 5.6, 0.9),
     "Test classes pulled from GitHub with a blobless partial clone at the pinned "
     "commits. The body itself comes from the benchmark's own column, because the "
     "pinned commit holds a different version for 37 of the 80.",
     13.5, INK2, BODY, first=True, line=1.26)

para(tb(s, M + 6.05, 1.88, 6.4, 0.3), "Slicing, one test class at a time", 14.5,
     INK, BODY, bold=True, first=True)
code(s, M + 6.05, 2.20, 6.4, [
 ("def slices_for(src, method_name):", "plain"),
 ("    methods, fields = parse_methods(src)", "plain"),
 ("", "plain"),
 ("    body = next(t for k, n, t in methods", "plain"),
 ("             if n == method_name)", "plain"),
 ("", "plain"),
 ("    fixtures = join(t for k, n, t in methods", "hi"),
 ("               if k == 'fixture')", "hi"),
 ("", "plain"),
 ("    siblings = join(t for k, n, t in methods", "hi"),
 ("               if k == 'test' and n != method_name)", "hi"),
 ("", "plain"),
 ("    helpers  = join(t for n, t in helper_src", "plain"),
 ("               if called_from(body, n))", "plain"),
], size=11.5)
caption(s, M + 6.05, 6.12, 6.4,
        "Comments and string literals are blanked first by a single-pass scanner,")
caption(s, M + 6.05, 6.38, 6.4,
        "so a /* inside a string cannot swallow the file.")
footer(s, 6)

# =========================================================== 7a lexicon
s = slide()
head(s, "Measurement, part 1", "The lexicon: turning code into signals")
note(s, 1.82, "38 regex families across the 5 flaky categories (lexicon v2.0). Written "
              "from the standard taxonomy, then stripped of project-specific identifiers "
              "and extended with tokens mined from held-out FlakeBench tests.", MUTED, 13.5)

cats = [("async wait", 7, "Thread.sleep(   .await(   CountDownLatch   Future"),
        ("", 0,           "waitFor*   Awaitility   poll(   retry*   @Test(timeout"),
        ("concurrency", 8, "new Thread   Runnable   ExecutorService   .submit("),
        ("", 0,            "synchronized   volatile   AtomicInteger   ConcurrentHashMap"),
        ("time", 7, "currentTimeMillis   nanoTime   new Date(   Calendar   .now()"),
        ("", 0,     "SimpleDateFormat   TimeZone   elapsed*   lastModified"),
        ("unordered collections", 8, "HashMap   HashSet   .keySet(   .entrySet(   ArrayList"),
        ("", 0,                      "listStatus   getDirectoryContents   .get(0)   toArray"),
        ("test order dependency", 8, "static <field>   @BeforeClass   @AfterClass"),
        ("", 0,                      "System.setProperty   getInstance(   Mini[A-Z]*   mkdirs(")]
y = 2.55
for name, n, toks in cats:
    if name:
        para(tb(s, M, y, 2.9, 0.3), name, 13.5, INK, BODY, bold=True, first=True)
        para(tb(s, M + 2.65, y + 0.02, 0.7, 0.3), "%d fam." % n, 11.5, MUTED, MONO,
             first=True)
    para(tb(s, M + 3.55, y + 0.01, 8.0, 0.3), toks, 12.5, INK2, MONO, first=True)
    y += 0.32 if not name else 0.30

para(tb(s, M, 5.90, 5.6, 0.3), "Signal preparation", 14, INK, BODY, bold=True,
     first=True)
para(tb(s, M, 6.22, 5.6, 0.8),
     "For one slice, each of the 5 categories contributes one number: how many of "
     "its families fire at least once. Presence, not occurrences, so a long slice "
     "is not rewarded for length.", 13, INK2, BODY, first=True, line=1.24)
code(s, M + 6.05, 5.90, 6.4, [
 ("body     -> [async 0, conc 0, time 0, uc 1, od 0]", "plain"),
 ("fields   -> [        0,      0,      0,    0,   1]", "plain"),
 ("fixtures -> [        0,      0,      0,    0,   3]", "hi"),
], size=11)
footer(s, 7)

# =========================================================== 7b strategies
s = slide()
head(s, "Measurement, part 2", "Two ways of using those signals")
note(s, 1.82, "The same numbers are read twice, once by a rule that fits nothing and "
              "once by a trained model. They agree on the ordering, which is the point "
              "of running both.", MUTED, 13.5)

para(tb(s, M, 2.42, 5.6, 0.3), "1.  Argmax  —  nothing is fitted", 15, INK, BODY,
     bold=True, first=True)
code(s, M, 2.76, 5.6, [
 ("score = sum of family counts", "dim"),
 ("        across the chosen slices", "dim"),
 ("", "plain"),
 ("async=0  conc=0  time=0  uc=1  od=4", "plain"),
 ("                            -> od", "hi"),
], size=11.5)
para(tb(s, M, 4.45, 5.6, 1.5),
     "No training, no folds, no held-out set, so it cannot overfit and the number of "
     "features is irrelevant to it. Ties are broken at random and averaged over 2,000 "
     "draws. This is the conservative reading: if the argmax improves, the signal is "
     "in the code rather than in the fitting.",
     13, INK2, BODY, first=True, line=1.26)

para(tb(s, M + 6.05, 2.42, 6.4, 0.3), "2.  Trained  —  logistic regression", 15, INK,
     BODY, bold=True, first=True)
code(s, M + 6.05, 2.76, 6.4, [
 ("# each slice stays its own group of 5", "dim"),
 ("X = [body_5 | fields_5 | fixtures_5]", "plain"),
 ("", "plain"),
 ("make_pipeline(StandardScaler(),", "plain"),
 ("  LogisticRegression(C=1.0,", "hi"),
 ("      class_weight='balanced'))", "hi"),
], size=11.5)
para(tb(s, M + 6.05, 4.70, 6.4, 1.3),
     "The model can learn that a fixture signal outweighs a body signal, which the "
     "argmax cannot. Class-balanced because order dependency is 46 of 80. Scaler "
     "inside the pipeline so it refits per fold and cannot leak.",
     13, INK2, BODY, first=True, line=1.26)

rect(s, M, 6.20, W - 2 * M, 0.80, SUNK)
para(tb(s, M + 0.30, 6.38, 11.0, 0.6),
     "Protocol: StratifiedShuffleSplit, 50 train / 30 test, 40 splits. k-fold would "
     "cap at 40/40 because unordered collections has 2 examples; 50/30 is the largest "
     "training set that still keeps all five classes in the test half. Mean macro-F1, "
     "scipy BCa bootstrap, 300-shuffle permutation null.",
     13, INK2, BODY, first=True, line=1.26)
footer(s, 8)

# =========================================================== 8  results
s = slide()
head(s, "Result", "Every slice measured on its own")
note(s, 1.82, "80 flaky tests, lexicon v2.0. Argmax fits nothing. Trained is logistic "
              "regression, 50 train / 30 test, 40 splits.", MUTED, 13.5)
table(s, M, 2.28,
      ["Slice fed to the classifier", "Features", "Argmax acc.", "Trained macro-F1",
       "Delta vs body only"],
      [3.75, 1.25, 1.65, 1.95, 3.0],
      [("body only", 5, "22.5%", "0.253", "—"),
       ("body + fields", 10, "36.2%", "0.358", "+0.106  [+0.080, +0.133]"),
       ("body + fixtures", 10, "52.5%", "0.397", "+0.145  [+0.117, +0.171]"),
       ("body + siblings", 10, "26.2%", "0.338", "+0.085  [+0.060, +0.107]"),
       ("body + helpers", 10, "25.0%", "0.267", "+0.014  [-0.013, +0.037]"),
       ("body + callees", 10, "11.2%", "0.273", "+0.020  [-0.001, +0.042]"),
       ("body + fields + fixtures", 15, "57.5%", "0.391", "+0.138  [+0.109, +0.164]"),
       ("  + siblings as well", 20, "41.2%", "0.397", "+0.145  [+0.111, +0.177]"),
       ("all six slices, separate", 30, "37.5%", "0.347", "+0.095  [+0.065, +0.129]")],
      size=12.5, rh=0.38, highlight={6}, aligns=["l", "r", "r", "r", "r"],
      head_size=10)
note(s, 6.05, "Fixtures are the strongest single slice on both measures. Helpers and "
              "callees are the two whose intervals cross zero. The untrained argmax "
              "separates fields + fixtures clearly (57.5%); the trained model cannot "
              "tell it from the version with siblings added.", INK2, 14)
footer(s, 9)

# =========================================================== per-category
s = slide()
head(s, "Result", "The gain is one category, not five")
note(s, 1.82, "Recall per category, untrained argmax. n is the number of tests of that "
              "category in the sample of 80.", MUTED, 13.5)

X0, SC = 5.35, 0.062          # 100% spans 6.2 in
rows = [("test order dependency", 46, 15, 76, True),
        ("async wait", 18, 39, 33, False),
        ("concurrency", 10, 10, 20, False),
        ("time", 4, 50, 50, False),
        ("unordered collections", 2, 50, 50, False)]
for gv in [0, 25, 50, 75, 100]:
    gx = X0 + gv * SC
    rect(s, gx, 2.45, 1 / 72.0, 3.15, RULE)
    para(tb(s, gx - 0.4, 5.68, 0.8, 0.3), "%d%%" % gv, 10.5, MUTED, MONO,
         first=True, align=PP_ALIGN.CENTER)
para(tb(s, X0 + 2.5, 5.94, 1.4, 0.3), "recall", 11, MUTED, MONO, first=True)

# legend
rect(s, M, 2.24, 0.16, 0.16, S_REF)
para(tb(s, M + 0.24, 2.19, 1.4, 0.3), "body only", 12.5, INK2, BODY, first=True)
rect(s, M + 1.55, 2.24, 0.16, 0.16, ACC)
para(tb(s, M + 1.79, 2.19, 2.6, 0.3), "body + fields + fixtures", 12.5, INK2, BODY,
     first=True)

y = 2.62
for lab, n, b, c, big in rows:
    para(tb(s, M, y - 0.02, 3.5, 0.30), lab, 13.5, INK if big else INK2, BODY,
         bold=big, first=True, align=PP_ALIGN.RIGHT)
    para(tb(s, M + 3.60, y + 0.01, 0.6, 0.26), "n=%d" % n, 11, MUTED, MONO, first=True)
    rect(s, X0, y, b * SC, 0.19, S_REF)
    rect(s, X0, y + 0.23, c * SC, 0.19, ACC)
    para(tb(s, X0 + b * SC + 0.10, y - 0.03, 0.7, 0.26), "%d%%" % b, 11.5, MUTED,
         MONO, first=True)
    para(tb(s, X0 + c * SC + 0.10, y + 0.20, 0.7, 0.26), "%d%%" % c, 11.5,
         UP if c > b else (HI if c < b else MUTED), MONO, bold=(c != b), first=True)
    delta = c - b
    txt = "—" if delta == 0 else ("%+d pts" % delta)
    para(tb(s, X0 + 6.55, y + 0.09, 1.0, 0.28), txt, 13,
         UP if delta > 0 else (HI if delta < 0 else MUTED), MONO,
         bold=(delta != 0), first=True)
    y += 0.62

rect(s, M, 6.25, W - 2 * M, 0.78, ACCSOFT)
rect(s, M, 6.25, 0.05, 0.78, ACC)
para(tb(s, M + 0.30, 6.44, 11.0, 0.6),
     "Order dependency is the only large move, 7 tests to 35 of 46. Concurrency's "
     "+10 points is one test, async wait's -6 is one test, and time and unordered "
     "collections have 4 and 2 examples between them.",
     14.5, ACC, BODY, bold=True, first=True, line=1.26)
footer(s, 10)

# =========================================================== 9  callee strategy
s = slide()
head(s, "Fourth context type", "Depth-1 callee extraction, and why it is not reliable")
para(tb(s, M, 1.86, 6.3, 0.3), "Current strategy: regex, type-directed", 14.5, INK,
     BODY, bold=True, first=True)
code(s, M, 2.18, 6.3, [
 ("# 1. variable -> declared type", "dim"),
 ("for t, v in TYPE_DECL.findall(fields + body):", "plain"),
 ("    var2type.setdefault(v, t)", "plain"),
 ("", "plain"),
 ("# 2. every  receiver.method(  in the body", "dim"),
 ("for recv, meth in INVOKE.findall(body):", "plain"),
 ("    if recv in var2type:", "hi"),
 ("        pairs.add((var2type[recv], meth))", "hi"),
 ("    elif recv[:1].isupper():", "plain"),
 ("        pairs.add((recv, meth))   # static call", "plain"),
 ("", "plain"),
 ("# 3. keep only types the project itself declares", "dim"),
 ("#    -> JDK and libraries drop out, no deny list", "dim"),
], size=11.5)
para(tb(s, M + 6.75, 1.86, 5.7, 0.3), "What it cannot do", 14.5, INK, BODY,
     bold=True, first=True)
rows = [("Chained calls", "bench.getConf().setLong(...) stops at getConf"),
        ("Inheritance", "a method on a superclass is never found"),
        ("Overloads", "takes the first name match, ignores arity"),
        ("Runtime type", "uses the declared type, misses overrides"),
        ("Same simple name", "resolves classes by filename only")]
yy = 2.22
for t, d in rows:
    para(tb(s, M + 6.75, yy, 2.1, 0.3), t, 13.5, HI, BODY, bold=True, first=True)
    para(tb(s, M + 8.95, yy, 3.5, 0.5), d, 12.5, INK2, BODY, first=True, line=1.22)
    yy += 0.62
para(tb(s, M + 6.75, 5.42, 5.7, 0.8),
     "Of 263 candidate types seen in the test bodies, 103 resolved to project code. "
     "Some of the remainder are genuine misses and this method cannot say which.",
     13, MUTED, BODY, first=True, line=1.26)
rect(s, M, 6.30, W - 2 * M, 0.72, ACCSOFT)
rect(s, M, 6.30, 0.05, 0.72, ACC)
para(tb(s, M + 0.30, 6.50, 11.2, 0.5),
     "At depth 2 these errors compound: every unresolved call silently removes a "
     "subtree. This is where a real resolver stops being optional.",
     14.5, ACC, BODY, bold=True, first=True)
footer(s, 11)

# =========================================================== 10 callee results
s = slide()
head(s, "Result", "Depth-1 callees do not help")
note(s, 1.86, "78 of the 80 tests resolve at least one callee, median 2.", MUTED)
table(s, M, 2.25, ["Measure", "body only", "body + callees", "body + fixtures"],
      [4.4, 2.4, 2.4, 2.4],
      [("argmax accuracy", "22.5%", "11.2%", "52.5%"),
       ("trained macro-F1", "0.253", "0.273", "0.397"),
       ("delta vs body only", "—", "+0.020", "+0.145"),
       ("95% CI", "—", "[-0.001, +0.042]", "[+0.117, +0.171]"),
       ("order-dependency recall", "15%", "4%", "70%")],
      size=12.5, rh=0.40, aligns=["l", "r", "r", "r"])
rect(s, M, 4.85, W - 2 * M, 0.80, ACCSOFT)
rect(s, M, 4.85, 0.05, 0.80, ACC)
para(tb(s, M + 0.30, 5.04, 11.2, 0.6),
     "Callees are the only slice that makes the untrained argmax worse than the body "
     "alone, and their interval is the one that crosses zero. Yet the slice does carry "
     "signal: it holds the true category for 33% of the misses against 5% of the hits.",
     14.5, ACC, BODY, bold=True, first=True, line=1.26)
para(tb(s, M, 5.90, 5.6, 0.3), "Two reasons it fails", 14, INK, BODY, bold=True,
     first=True)
para(tb(s, M, 6.20, 5.6, 0.8),
     "Depth 1 is too shallow: in TestPeerCache the daemon is three hops out. And "
     "production bodies are long, so one bag dilutes the body's own signal.",
     13, INK2, BODY, first=True, line=1.24)
para(tb(s, M + 6.05, 5.90, 6.4, 0.3), "What we would change", 14, INK, BODY,
     bold=True, first=True)
para(tb(s, M + 6.05, 6.20, 6.4, 0.8),
     "Go deeper than 1, keep callees a separate feature group rather than "
     "concatenated, and expect the gain in concurrency, not order dependency.",
     13, INK2, BODY, first=True, line=1.24)
footer(s, 12)

# =========================================================== 11 findings
s = slide()
head(s, "Summary", "What we have established")
fnd = [("Context outside the test body carries category signal",
        "Adding class fields and fixtures raises the untrained classifier from 32% to "
        "54% accuracy, and the trained one by +0.096 macro-F1, CI [+0.075, +0.118], "
        "permutation p <= 0.003."),
       ("The gain is concentrated in order dependency",
        "Its recall goes 20% to 70%. No other category improves. Fields, fixtures and "
        "siblings each help alone; siblings are redundant once fixtures are present."),
       ("Fields are the sharpest single signal",
        "They carry the true category for 49% of the model's misses and 12% of its "
        "hits. They are also the cheapest thing to extract: no resolution, no build."),
       ("Depth-1 callees are implemented but do not yet pay",
        "The signal is present, 33% against 5%, but regex resolution and a depth of 1 "
        "cannot reach it.")]
y = 1.95
for i, (t, d) in enumerate(fnd, 1):
    para(tb(s, M, y + 0.02, 0.4, 0.3), str(i), 13.5, MUTED, MONO, first=True)
    para(tb(s, M + 0.45, y, 11.0, 0.3), t, 16, INK, BODY, bold=True, first=True)
    para(tb(s, M + 0.45, y + 0.34, 11.0, 0.8), d, 13.5, INK2, BODY, first=True,
         line=1.26)
    y += 1.22
    if i < 4: rect(s, M, y - 0.20, W - 2 * M, 1 / 72.0, RULE)
para(tb(s, M, 6.85, 11.6, 0.3),
     "Caveat: 80 tests, order dependency is 46 of them, and a regex lexicon is a "
     "floor rather than a prediction of what a fine-tuned encoder would gain.",
     12.5, MUTED, BODY, first=True)
footer(s, 13)

# =========================================================== 12 next
s = slide()
head(s, "Next", "Proposed next steps")
steps = [("Replace the regex resolver with Spoon",
          "Prototype already runs: JDK 11 and Maven are installed, Spoon 10.4.2 "
          "compiles, and it resolves PeerCache#put(DatanodeID, Peer) with full "
          "signatures and follows the call chain. Gives inheritance, overloads and "
          "real depth control.",
          "prototype works"),
         ("Settle the depth question with evidence",
          "TestPeerCache needs depth 3, and the final hop is an anonymous Runnable "
          "handed to a thread, which no call-graph traversal follows. Depth alone will "
          "not fix it; the model needs to handle thread starts.",
          "open question"),
         ("Bring in an LLM as a second reader",
          "Run the existing zero-shot prompt on the flaky tests twice, body alone "
          "against body plus the extracted context, and count how many of the current "
          "errors flip. No training, and the prompt is already in the repository.",
          "cheap, this week"),
         ("Then, and only then, fine-tune",
          "Retrain the encoder on the same folds with context appended. The 512-token "
          "limit is the real obstacle, which is what the two-tower design in the plan "
          "is for.",
          "needs GPU")]
y = 1.92
for i, (t, d, tag) in enumerate(steps, 1):
    para(tb(s, M, y + 0.02, 0.4, 0.3), str(i), 13.5, MUTED, MONO, first=True)
    para(tb(s, M + 0.45, y, 8.2, 0.3), t, 16, INK, BODY, bold=True, first=True)
    ww = 0.098 * len(tag) + 0.34
    rect(s, W - M - ww, y + 0.02, ww, 0.28, ACCSOFT)
    para(tb(s, W - M - ww, y + 0.04, ww, 0.26, MSO_ANCHOR.MIDDLE), tag, 11.5, ACC,
         MONO, bold=True, first=True, align=PP_ALIGN.CENTER)
    para(tb(s, M + 0.45, y + 0.34, 10.6, 0.9), d, 13.5, INK2, BODY, first=True,
         line=1.26)
    y += 1.30
    if i < 4: rect(s, M, y - 0.22, W - 2 * M, 1 / 72.0, RULE)
footer(s, 14)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "FlakyLens_progress.pptx")
prs.save(out)
print("saved", os.path.abspath(out), os.path.getsize(out), "bytes,",
      len(prs.slides._sldIdLst), "slides")
