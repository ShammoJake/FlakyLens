from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
import os

INK   = RGBColor(0x15,0x1A,0x21)
INK2  = RGBColor(0x3D,0x46,0x53)
MUTED = RGBColor(0x6B,0x76,0x84)
ACC   = RGBColor(0x2F,0x48,0x58)
MISS  = RGBColor(0xA8,0x45,0x2B)
HIT   = RGBColor(0x3A,0x66,0x50)
RULE  = RGBColor(0xDC,0xE0,0xE7)
CODEBG= RGBColor(0xF1,0xF3,0xF6)
SUNK  = RGBColor(0xED,0xEF,0xF3)
WHITE = RGBColor(0xFF,0xFF,0xFF)
MARK  = RGBColor(0xFB,0xEB,0xD2)

BODY="Calibri"; MONO="Consolas"; DISP="Calibri"

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
W = 13.333; H = 7.5
M = 0.72                      # left margin

def slide():
    s = prs.slides.add_slide(BLANK)
    bg = s.background.fill; bg.solid(); bg.fore_color.rgb = WHITE
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
    from pptx.enum.shapes import MSO_SHAPE
    sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line; sh.line.width = Pt(lw)
    sh.shadow.inherit = False
    return sh

def eyebrow(s, text):
    tf = tb(s, M, 0.42, 11, 0.3)
    para(tf, text.upper(), 10.5, MUTED, MONO, first=True)

def title(s, text, color=INK, y=0.78, size=30):
    tf = tb(s, M, y, 11.9, 0.9)
    para(tf, text, size, color, DISP, bold=True, first=True, line=1.05)

def rule_line(s, y, x=M, w=W-2*M, color=RULE, thick=1.0):
    rect(s, x, y, w, thick/72.0, color)

RENDER = 1.23   # PowerPoint renders a "multiple" line-space taller than pt*lh/72

def code(s, x, y, w, lines, size=12.5, pad=0.16, lh=1.30):
    """lines: list of (text, style) with style in plain|hi|dim|com"""
    n = len(lines)
    h = pad*2 + n*(size*lh*RENDER/72.0)
    rect(s, x, y, w, h, CODEBG, RULE)
    tf = tb(s, x+pad, y+pad, w-2*pad, h-2*pad)
    for i,(t,st) in enumerate(lines):
        col  = {"plain":INK2,"hi":MISS,"dim":MUTED,"com":MUTED,"acc":ACC}[st]
        bold = st in ("hi","acc")
        ital = st == "com"
        para(tf, t if t else " ", size, col, MONO, bold=bold, italic=ital,
             first=(i==0), line=lh)
    return y + h

def pill(s, x, y, text, fg, bg, w=None):
    ww = w or (0.105*len(text) + 0.22)
    rect(s, x, y, ww, 0.30, bg)
    tf = tb(s, x, y, ww, 0.30, MSO_ANCHOR.MIDDLE)
    para(tf, text, 11, fg, MONO, bold=True, first=True, align=PP_ALIGN.CENTER)
    return x + ww

def verdict(s, x, y, truth, pred):
    cur = pill(s, x, y, truth, HIT, RGBColor(0xE3,0xED,0xE7))
    tf = tb(s, cur+0.10, y, 0.85, 0.30, MSO_ANCHOR.MIDDLE)
    para(tf, "read as", 11, MUTED, BODY, first=True, italic=True)
    pill(s, cur+0.92, y, pred, MISS, RGBColor(0xF6,0xE7,0xE2))

def footer(s, n):
    tf = tb(s, W-1.5, H-0.52, 0.9, 0.3)
    para(tf, str(n), 10, MUTED, MONO, first=True, align=PP_ALIGN.RIGHT)

def note(s, y, text, color=INK2, size=15, x=M, w=W-2*M):
    tf = tb(s, x, y, w, 0.9)
    para(tf, text, size, color, BODY, first=True, line=1.28)

# ============================================================ 1 title
s = slide()
rect(s, 0, 0, 0.18, H, ACC)
tf = tb(s, M+0.20, 1.65, 11.2, 0.4)
para(tf, "FLAKYLENS · PROGRAM-ANALYSIS INVESTIGATION", 12, MUTED, MONO, first=True)
tf = tb(s, M+0.20, 2.20, 11.4, 1.5)
para(tf, "Where the Evidence Lives", 46, INK, DISP, bold=True, first=True, line=1.0)
tf = tb(s, M+0.20, 3.55, 9.6, 1.4)
para(tf, "Every flaky test the model gets wrong in Hadoop is one whose true cause is "
         "written somewhere the model never reads. The signal is not missing from the "
         "project. It is missing from the lines we feed the encoder.",
     17, INK2, BODY, first=True, line=1.32)
rule_line(s, 5.35, M+0.20, 9.6)
tf = tb(s, M+0.20, 5.55, 11, 0.9)
para(tf, "apache/hadoop  ·  3 pinned commits  ·  33 flaky tests, 27 located",
     13, MUTED, MONO, first=True, line=1.5)
para(tf, "4 September 2026", 13, MUTED, MONO, space_before=3)

# ============================================================ 2 what we did
s = slide(); eyebrow(s, "Method"); title(s, "What we did")
rule_line(s, 1.68)
steps = [
 ("Started from predictions already in the repo",
  "The shipped per-project results file carries prediction and ground truth for all 8,574 tests. "
  "No model run was needed."),
 ("Localised the error",
  "All 105 errors sit inside the 280 flaky tests. Hadoop misses 20 of its 33, a 61% error rate "
  "against 37.5% benchmark-wide, and has classes containing both hits and misses."),
 ("Fetched real source at the pinned commits",
  "Blobless partial clone at the three SHAs in the benchmark. Matched each test method by name "
  "inside its class. 27 of 33 resolved."),
 ("Asked one question per test",
  "Where in the project is the fact that makes the true label true? Assigned to one of five "
  "places, then compared against whether the model got it right."),
]
y = 2.00
for i,(t,d) in enumerate(steps,1):
    tf = tb(s, M, y, 0.45, 0.4)
    para(tf, str(i), 15, MUTED, MONO, first=True)
    tf = tb(s, M+0.48, y-0.03, 11.3, 0.45)
    para(tf, t, 17, INK, BODY, bold=True, first=True)
    tf = tb(s, M+0.48, y+0.34, 11.1, 0.75)
    para(tf, d, 14, INK2, BODY, first=True, line=1.26)
    y += 1.24
    if i < 4: rule_line(s, y-0.20)
footer(s, 2)

# ============================================================ 3 headline
s = slide(); eyebrow(s, "Result"); title(s, "The finding")
rule_line(s, 1.68)
cards = [
 ("17/17", MISS, "Misclassified tests whose true-category evidence sits OUTSIDE the test body"),
 ("6/10",  HIT,  "Correctly classified tests whose evidence is INSIDE the body"),
 ("0.0007", ACC, "Fisher exact two-sided p for that split"),
 ("7 → 0", ACC, "Tests in a class holding a shared static cluster: all wrong, none right"),
]
cw = (W - 2*M - 3*0.22)/4
for i,(n,c,l) in enumerate(cards):
    x = M + i*(cw+0.22)
    rect(s, x, 2.05, cw, 2.15, SUNK)
    tf = tb(s, x+0.24, 2.30, cw-0.4, 0.9)
    para(tf, n, 44, c, DISP, bold=True, first=True, line=1.0)
    tf = tb(s, x+0.24, 3.22, cw-0.48, 0.9)
    para(tf, l, 13, INK2, BODY, first=True, line=1.24)
rect(s, M, 4.65, W-2*M, 1.30, RGBColor(0xE3,0xEA,0xEF))
rect(s, M, 4.65, 0.05, 1.30, ACC)
tf = tb(s, M+0.34, 4.88, W-2*M-0.7, 0.9)
para(tf, "The 4 correct answers with no body evidence are best read as the model landing on "
         "order dependency because it is the most common flaky label in this project.",
     15.5, INK2, BODY, first=True, line=1.3)
note(s, 6.25, "Median test body: 9 lines for misses, 17 lines for hits.", MUTED, 14)
footer(s, 3)

# ============================================================ 4 confusions
s = slide(); eyebrow(s, "Where the error concentrates")
title(s, "The confusions are directed, not random")
rule_line(s, 1.68)
note(s, 1.92, "8,293 of 8,294 non-flaky tests are classified correctly. Every error lives in the "
              "280 flaky tests. Per-category F1: non-flaky 1.00, unordered collections 0.75, "
              "concurrency 0.36.", INK2, 15)
conf = [("concurrency","async wait",20),("order dependency","async wait",13),
        ("order dependency","concurrency",11),("order dependency","unordered coll.",10),
        ("async wait","order dependency",10),("async wait","concurrency",7),
        ("order dependency","time",6),("async wait","unordered coll.",5)]
y = 3.00; barx = 5.55; barw = 5.2
for a,b,n in conf:
    tf = tb(s, M, y-0.03, 3.4, 0.3)
    para(tf, a, 13, INK2, MONO, first=True, align=PP_ALIGN.RIGHT)
    tf = tb(s, M+3.48, y-0.03, 0.7, 0.3)
    para(tf, "read as", 11, MUTED, BODY, first=True, italic=True, align=PP_ALIGN.CENTER)
    tf = tb(s, M+4.22, y-0.03, 1.25, 0.3)
    para(tf, b, 13, MISS, MONO, first=True)
    rect(s, barx, y+0.02, barw, 0.20, SUNK)
    rect(s, barx, y+0.02, barw*n/20.0, 0.20, ACC)
    tf = tb(s, barx+barw+0.16, y-0.03, 0.5, 0.3)
    para(tf, str(n), 13, MUTED, MONO, first=True)
    y += 0.42
note(s, 6.35, "Order dependency is the largest flaky category and bleeds into every other. "
              "By definition it is a property of what happens BETWEEN tests, which a body-only "
              "encoder can never see.", INK, 15)
footer(s, 4)

# ============================================================ 5 DFSIO
s = slide(); eyebrow(s, "Exhibit 1 · TestDFSIO · 5 tests, all wrong")
title(s, "The fixture states the dependency in a comment")
verdict(s, M, 1.55, "order dependency", "time")
note(s, 2.08, "What the encoder receives — five lines, one local named execTime.",
     MUTED, 14, x=M, w=5.85)
yy = code(s, M, 2.46, 5.85, [
 ("@Test (timeout = 10000)","dim"),
 ("public void testRead() throws Exception {","plain"),
 ("  FileSystem fs = cluster.getFileSystem();","plain"),
 ("  long execTime = bench.readTest(fs);","plain"),
 ("  bench.analyzeResult(fs, TEST_TYPE_READ, execTime);","plain"),
 ("}","plain"),
], size=12.5)
note(s, 2.08, "Forty lines higher in the same file.", MUTED, 14, x=M+6.20, w=5.8)
code(s, M+6.20, 2.46, 6.0, [
 ("private static MiniDFSCluster cluster;","hi"),
 ("private static TestDFSIO bench;","hi"),
 ("","plain"),
 ("@BeforeClass","hi"),
 ("public static void beforeClass() throws Exception {","plain"),
 ("  cluster = new MiniDFSCluster.Builder(...).build();","plain"),
 ("  bench.createControlFile(fs, ...);","plain"),
 ("","plain"),
 ("  /** Check write here, as it is","com"),
 ("      required for other tests */","com"),
 ("  testWrite();","hi"),
 ("}","plain"),
], size=12)
note(s, 4.62, "Static cluster, built once, no per-test reset. The files testRead reads are "
              "produced by testWrite. A sibling test compounds it:", INK2, 14.5, x=M, w=5.85)
code(s, M, 5.42, 5.85, [
 ("public void testReadRandom() throws Exception {","plain"),
 ("  bench.getConf().setLong(\"test.io.skip.size\", 0);","hi"),
 ("  ...","plain"),
 ("}","plain"),
], size=12)
tf = tb(s, M, 6.92, 12, 0.35)
para(tf, "EVIDENCE AT:  class fixture and static fields. Zero hops into production code.",
     12.5, ACC, MONO, bold=True, first=True)
footer(s, 5)

# ============================================================ 6 PathData
s = slide(); eyebrow(s, "Exhibit 2 · TestPathData · 4 wrong, 3 right, same class")
title(s, "A helper that refutes the prediction outright")
verdict(s, M, 1.55, "order dependency", "unordered collections")
note(s, 2.08, "The three misses list a directory and compare against an expected set.",
     MUTED, 14, x=M, w=6.0)
code(s, M, 2.46, 6.0, [
 ("public void testCwdContents() throws Exception {","plain"),
 ("  PathData item = new PathData(Path.CUR_DIR, conf);","plain"),
 ("  PathData[] items = item.getDirectoryContents();","plain"),
 ("  assertEquals(sortedString(\"d1\", \"d2\"),","plain"),
 ("               sortedString(items));","plain"),
 ("}","plain"),
], size=12)
note(s, 2.08, "The helper it calls twice, same file, private.", MUTED, 14, x=M+6.35, w=5.6)
code(s, M+6.35, 2.46, 5.85, [
 ("private static String sortedString(Object ... list) {","plain"),
 ("  String[] strings = new String[list.length];","plain"),
 ("  for (int i=0; i < list.length; i++)","plain"),
 ("    strings[i] = String.valueOf(list[i]);","plain"),
 ("  Arrays.sort(strings);","hi"),
 ("  ...","plain"),
 ("}","plain"),
], size=12)
note(s, 4.78, "The test sorts BOTH sides. Iteration order cannot flake it. The real dependency "
              "is in the fixture, on a FileSystem that Hadoop hands out from a process-wide cache:",
     INK, 15)
code(s, M, 5.36, 8.4, [
 ("public void initialize() throws Exception {   // @Before","plain"),
 ("  fs = FileSystem.getLocal(conf);      // process-wide cache","com"),
 ("  FileSystem.setDefaultUri(conf, fs.getUri());","hi"),
 ("  fs.setWorkingDirectory(testDir);","hi"),
 ("}","plain"),
], size=12, lh=1.22)
tf = tb(s, M, 6.98, 12, 0.35)
para(tf, "EVIDENCE AT:  same-file helper rules OUT the prediction; fixture supplies the truth.",
     12.5, ACC, MONO, bold=True, first=True)
footer(s, 6)

# ============================================================ 7 MetricsSystemImpl
s = slide(); eyebrow(s, "Exhibit 3 · TestMetricsSystemImpl")
title(s, "Two hops from the body to the hash map")
verdict(s, M, 1.55, "unordered collections", "async wait")
note(s, 2.08, "Body ends on a Mockito timeout, a strong async token, and holds no collection.",
     MUTED, 14)
code(s, M, 2.44, 11.9, [
 ("verify(sink1, timeout(200).times(2)).putMetrics(r1.capture());","plain"),
 ("List<MetricsRecord> mr1 = r1.getAllValues();","plain"),
 ("checkMetricsRecords(mr1);","acc"),
], size=12.5, lh=1.22)
note(s, 3.56, "Hop 1 — the helper asserts against fixed positions in that list.", MUTED, 14)
code(s, M, 3.92, 11.9, [
 ("private void checkMetricsRecords(List<MetricsRecord> recs) {","plain"),
 ("  MetricsRecord r = recs.get(0);","hi"),
 ("  assertEquals(\"name\", \"s1rec\", r.name());","plain"),
 ("  r = recs.get(1);","hi"),
 ("}","plain"),
], size=12.5, lh=1.22)
note(s, 5.50, "Hop 2 — the production class says what fills those positions.", MUTED, 14)
code(s, M, 5.86, 11.9, [
 ("// MetricsSystemImpl.java","com"),
 ("allSources = Maps.newHashMap();","hi"),
 ("for (Entry<String, MetricsSourceAdapter> entry : sources.entrySet()) { ... }","hi"),
], size=12.5, lh=1.22)
tf = tb(s, M, 6.98, 12, 0.35)
para(tf, "A hash map decides which record lands at index zero, and the test asserts on index zero.",
     13, ACC, BODY, bold=True, first=True)
footer(s, 7)

# ============================================================ 8 PeerCache
s = slide(); eyebrow(s, "Exhibit 4 · TestPeerCache · 3 tests, all wrong")
title(s, "Nothing in the test class carries it")
verdict(s, M, 1.55, "order dependency", "async wait")
note(s, 2.08, "No static field, no fixture, no threading vocabulary in the test class.",
     MUTED, 14, x=M, w=5.85)
code(s, M, 2.46, 5.85, [
 ("public void testAddAndRetrieve() throws Exception {","plain"),
 ("  PeerCache cache = new PeerCache(3, 100000);","plain"),
 ("  cache.put(dnId, peer);","plain"),
 ("  assertEquals(1, cache.size());","plain"),
 ("  assertEquals(peer, cache.get(dnId, false));","plain"),
 ("}","plain"),
], size=12)
note(s, 2.08, "PeerCache.java, one call away.", MUTED, 14, x=M+6.20, w=5.8)
code(s, M+6.20, 2.46, 6.0, [
 ("private synchronized void startExpiryDaemon() {","hi"),
 ("  if (isDaemonStarted()) return;","plain"),
 ("  daemon = new Daemon(new Runnable() { ... });","hi"),
 ("  daemon.start();","hi"),
 ("}","plain"),
 ("","plain"),
 ("private void run() throws InterruptedException {","plain"),
 ("  for(long t = Time.monotonicNow();","plain"),
 ("      !Thread.interrupted();","plain"),
 ("      Thread.sleep(expiryPeriod)) {","hi"),
 ("    evictExpired(expiryPeriod);","plain"),
 ("  }","plain"),
 ("}","plain"),
], size=12)
note(s, 4.90, "A background daemon evicts on a timer, every accessor is synchronized, and only "
              "one of the three tests calls close() to stop its daemon.", INK, 15, x=M, w=5.85)
rect(s, M, 5.95, 5.85, 0.95, RGBColor(0xF6,0xE7,0xE2))
tf = tb(s, M+0.24, 6.12, 5.4, 0.7)
para(tf, "From the body alone, this is indistinguishable from an async-wait test. "
         "No body-derived feature can separate them.", 14, MISS, BODY, first=True, line=1.26)
footer(s, 8)

# ============================================================ 9 fixtures
s = slide(); eyebrow(s, "Exhibit 5 · TestRPCCompatibility and TestDelegationTokenForProxyUser")
title(s, "Two fixtures that name the dependency almost outright")
rule_line(s, 1.68)
note(s, 1.92, "Resetting a global cache each test implies it leaks across tests.",
     MUTED, 14, x=M, w=5.85)
code(s, M, 2.32, 5.85, [
 ("@Before","dim"),
 ("public void setUp() {","plain"),
 ("  ProtocolSignature.resetCache();","hi"),
 ("}","plain"),
], size=13)
note(s, 1.92, "Five static fields, and process-global registries written once for the class.",
     MUTED, 14, x=M+6.20, w=5.8)
code(s, M+6.20, 2.32, 6.0, [
 ("private static MiniDFSCluster cluster;","hi"),
 ("private static Configuration config;","hi"),
 ("private static UserGroupInformation ugi, proxyUgi;","hi"),
 ("","plain"),
 ("@BeforeClass","dim"),
 ("public static void setUp() throws Exception {","plain"),
 ("  config.setLong(TOKEN_MAX_LIFETIME_KEY, 10000);","hi"),
 ("  FileSystem.setDefaultUri(config, \"hdfs://...\");","hi"),
 ("  ProxyUsers.refreshSuperUserGroups(config);","hi"),
 ("}","plain"),
], size=12)
verdict(s, M, 4.12, "order dependency", "async wait")
verdict(s, M+6.20, 5.55, "order dependency", "concurrency")
rect(s, M, 6.28, W-2*M, 0.86, RGBColor(0xE3,0xEA,0xEF))
rect(s, M, 6.28, 0.05, 0.86, ACC)
tf = tb(s, M+0.32, 6.48, 12.0, 0.5)
para(tf, "Both are the cheapest possible extraction: static field declarations and fixture "
         "bodies. No symbol resolution, no call graph, no successful build.",
     15.5, ACC, BODY, bold=True, first=True, line=1.26)
footer(s, 9)

# ============================================================ 10 table
s = slide(); eyebrow(s, "All 17 misses")
title(s, "Where the deciding fact sits")
rule_line(s, 1.68)
rows = [
 ("TestDFSIO", "5 tests", "OD", "time", "Fixture + static field / sibling test"),
 ("TestPathData", "4 tests", "OD", "UC", "Same-file helper + fixture"),
 ("TestPeerCache", "3 tests", "OD", "async", "Production callee, depth 1"),
 ("TestDelegationTokenForProxyUser", "2 tests", "OD", "conc", "Fixture + static field"),
 ("TestRPCCompatibility", "1 test", "OD", "async", "Class fixture"),
 ("TestMetricsSystemImpl", "1 test", "UC", "async", "Helper + production callee"),
 ("TestDelegationToken", "1 test", "conc", "async", "Production callee, depth 1"),
]
hdr = ["Class","Count","True","Predicted","Evidence location"]
cols = [M, M+4.35, M+5.45, M+6.55, M+7.95]
widths = [4.2, 1.0, 1.0, 1.3, 4.0]
rect(s, M, 2.02, W-2*M, 0.40, SUNK)
for x,h in zip(cols,hdr):
    tf = tb(s, x+0.12, 2.10, 3.9, 0.28)
    para(tf, h.upper(), 11, MUTED, MONO, bold=True, first=True)
y = 2.50
for c,n,t,p,e in rows:
    tf = tb(s, cols[0]+0.12, y, 4.1, 0.3); para(tf, c, 13.5, INK, MONO, first=True)
    tf = tb(s, cols[1]+0.12, y, 1.0, 0.3); para(tf, n, 13.5, MUTED, BODY, first=True)
    tf = tb(s, cols[2]+0.12, y, 1.0, 0.3); para(tf, t, 13.5, HIT, MONO, bold=True, first=True)
    tf = tb(s, cols[3]+0.12, y, 1.3, 0.3); para(tf, p, 13.5, MISS, MONO, bold=True, first=True)
    tf = tb(s, cols[4]+0.12, y, 4.2, 0.3); para(tf, e, 13.5, INK2, BODY, first=True)
    y += 0.44
    rule_line(s, y-0.09)
tallies = [("9 of 17","reachable from the class fixture and static fields alone"),
           ("4 of 17","need a same-file private helper"),
           ("4 of 17","need a production callee at depth 1")]
yy = y + 0.22
for n,d in tallies:
    tf = tb(s, M, yy, 1.3, 0.3); para(tf, n, 14, ACC, MONO, bold=True, first=True)
    tf = tb(s, M+1.35, yy, 10, 0.3); para(tf, d, 14, INK2, BODY, first=True)
    yy += 0.36
footer(s, 10)

# ============================================================ 11 what to extract
s = slide(); eyebrow(s, "Implication")
title(s, "What to extract, cheapest first")
rule_line(s, 1.68)
items = [
 ("Static fields and fixture bodies", "9 of 17",
  "Static field declarations, every setup and teardown body, and whether a per-test reset exists "
  "at all. A parse away. No symbol resolution, no call graph, no build."),
 ("Same-file helper bodies", "+4",
  "Private methods the test invokes. Includes the one case where the helper actively refutes the "
  "predicted category. Name-and-arity matching inside one file is enough."),
 ("Sibling-test writes to shared state", "—",
  "Which other tests in the class assign to the static fields this test reads. The single feature "
  "no body-only representation can approximate."),
 ("Production callees at depth 1", "+4",
  "The focal-method expansion already in the plan. All four hinge on a background thread, a "
  "synchronized accessor, or a hash container in the class under test."),
]
y = 2.02
for i,(t,n,d) in enumerate(items,1):
    tf = tb(s, M, y+0.02, 0.4, 0.35); para(tf, str(i), 15, MUTED, MONO, first=True)
    tf = tb(s, M+0.45, y, 8.6, 0.35); para(tf, t, 17.5, INK, BODY, bold=True, first=True)
    if n != "—":
        pill(s, W-M-1.15, y+0.02, n, ACC, RGBColor(0xE3,0xEA,0xEF), w=1.15)
    tf = tb(s, M+0.45, y+0.40, 11.1, 0.72)
    para(tf, d, 14, INK2, BODY, first=True, line=1.26)
    y += 1.22
    if i < 4: rule_line(s, y-0.18)
rect(s, M, 6.35, W-2*M, 0.72, RGBColor(0xE3,0xEA,0xEF))
rect(s, M, 6.35, 0.05, 0.72, ACC)
tf = tb(s, M+0.32, 6.53, 12, 0.4)
para(tf, "Steps 1 to 3 use only the test file already downloaded for the benchmark. "
         "Only step 4 needs Spoon, and only to depth 1.", 15, ACC, BODY, bold=True, first=True)
footer(s, 11)

# ============================================================ 12 verify
s = slide(); eyebrow(s, "Next"); title(s, "How to test whether it actually helps")
rule_line(s, 1.68)
rect(s, M, 2.05, 5.9, 3.05, SUNK)
tf = tb(s, M+0.30, 2.30, 5.3, 0.4)
para(tf, "Cheap · this week", 12, MUTED, MONO, bold=True, first=True)
tf = tb(s, M+0.30, 2.70, 5.3, 0.5)
para(tf, "No training, no GPU", 20, INK, BODY, bold=True, first=True)
tf = tb(s, M+0.30, 3.28, 5.3, 1.6)
para(tf, "Run the existing zero-shot prompt on the 280 flaky tests twice: body alone, then body "
         "plus class fixture, static fields and called helpers. Count how many of the 105 errors "
         "flip. The prompt is already in the repo.", 14, INK2, BODY, first=True, line=1.28)
rect(s, M+6.20, 2.05, 5.9, 3.05, SUNK)
tf = tb(s, M+6.50, 2.30, 5.3, 0.4)
para(tf, "Real · after that", 12, MUTED, MONO, bold=True, first=True)
tf = tb(s, M+6.50, 2.70, 5.3, 0.5)
para(tf, "Retrain on the same folds", 20, INK, BODY, bold=True, first=True)
tf = tb(s, M+6.50, 3.28, 5.3, 1.6)
para(tf, "Fine-tune the same encoder with context appended and report the delta. The existing "
         "weights cannot be reused: they were trained on bodies only, so feeding them context "
         "measures distribution shift, not information gain.", 14, INK2, BODY, first=True, line=1.28)
rect(s, M, 5.40, W-2*M, 0.95, RGBColor(0xFB,0xEB,0xD2))
rect(s, M, 5.40, 0.05, 0.95, RGBColor(0xD9,0xA4,0x41))
tf = tb(s, M+0.32, 5.60, 12.0, 0.7)
para(tf, "Both must report flaky-subset macro-F1 and full-benchmark macro-F1 separately. "
         "The 8,294 non-flaky tests are already perfect, so context can only cost accuracy there.",
     15, INK, BODY, bold=True, first=True, line=1.26)
footer(s, 12)

# ============================================================ 13 caveats
s = slide(); eyebrow(s, "Caveats"); title(s, "What this does not yet show")
rule_line(s, 1.68)
cav = [
 ("6 of 33 did not resolve",
  "TestHftpFileSystem (3) and TestBlockFixer name classes absent from all three commits, "
  "TestFairScheduler.testContinuousScheduling is missing from a class that exists, and one "
  "benchmark row carries a bare method name with no class. An 18% localisation failure on one "
  "project is a schedule risk for extraction at scale."),
 ("One project",
  "Hadoop is the worst project in the benchmark and was chosen for that reason. cdap misses "
  "8 of 11 and is the obvious second."),
 ("Evidence location is my reading",
  "Each assignment traces to lines quoted here, but a second reader should check the 17 before "
  "this becomes a paper claim."),
 ("Label noise is not ruled out",
  "TestPeerCache is labelled order dependency, yet the production code reads closer to "
  "concurrency. If some labels are wrong, no program analysis recovers them. Worth sampling "
  "before the extraction work is scoped."),
]
y = 2.02
for t,d in cav:
    rect(s, M, y, 0.05, 0.92, MISS)
    tf = tb(s, M+0.28, y-0.02, 11.4, 0.35)
    para(tf, t, 16.5, INK, BODY, bold=True, first=True)
    tf = tb(s, M+0.28, y+0.34, 11.3, 0.75)
    para(tf, d, 13.5, INK2, BODY, first=True, line=1.24)
    y += 1.20
tf = tb(s, M, 6.95, 12.2, 0.35)
para(tf, "Full report, tables and extracted sources:  docs/investigation/", 12.5, MUTED, MONO,
     first=True)
footer(s, 13)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "FlakyLens_evidence_investigation.pptx")
prs.save(out)
print("saved", out, os.path.getsize(out), "bytes,", len(prs.slides.__iter__.__self__._sldIdLst), "slides")
