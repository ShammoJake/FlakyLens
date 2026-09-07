"""Mine candidate lexicon tokens from FlakeBench, held out from the study sample.

Two problems with lexicon v1.0 that this addresses.

  1. Some families name project-specific identifiers (MiniDFSCluster, MiniYARN,
     GenericTestUtils.waitFor, TEST_ROOT). Our sample is Hadoop-heavy, so those
     inflate the result and will not transfer.
  2. The families were written from the literature rather than from the data.

This ranks tokens by how much they are enriched in one flaky category against
all others, and keeps only tokens that appear in several distinct projects, so a
token that works for one repository cannot survive.

**The 80 tests used in the study are excluded from the mining**, so the
vocabulary is discovered on data the evaluation never sees.
"""
import os, re, sys, json, math, collections
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(BASE, "..", ".."))
sys.path.insert(0, HERE)
from slice_and_count import strip_noise  # noqa: E402

MIN_PROJECTS = 5        # a token must work in at least this many repositories
MIN_TESTS = 6           # and appear in at least this many tests of its category
TOP_N = 18              # candidates to print per category

# Java and JUnit vocabulary that carries no category information.
STOP = set("""
public private protected static final void int long boolean double float char byte
short String Object class new return if else for while try catch finally throw throws
this super null true false import package extends implements interface enum assert
Test Before After Override Exception RuntimeException IOException System out println
assertEquals assertTrue assertFalse assertNull assertNotNull assertSame fail assertThat
get set add put size length value name test o e i j k n s t x y result actual expected
""".split())

TOKEN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")


def tokens(code):
    return {t for t in TOKEN.findall(strip_noise(code)) if t not in STOP}


def main():
    bench = pd.read_csv(os.path.join(ROOT, "FlakeBench", "FlakeBench_dataset.csv"))
    used = pd.read_csv(os.path.join(BASE, "sources", "index.csv"))
    used = set(zip(used.project, used.test))
    held = bench[[(p, t) not in used for p, t in zip(bench.project, bench.test_name)]]
    flaky = held[held.label != "non-flaky"]
    print("FlakeBench: %d tests, %d flaky" % (len(bench), (bench.label != "non-flaky").sum()))
    print("held out from the study sample: %d flaky tests across %d projects\n"
          % (len(flaky), flaky.project.nunique()))

    # token -> category -> set(tests) and set(projects)
    per_cat = collections.defaultdict(lambda: collections.defaultdict(set))
    per_cat_proj = collections.defaultdict(lambda: collections.defaultdict(set))
    cat_size = collections.Counter()
    for _, r in flaky.iterrows():
        cat_size[r.label] += 1
        for tok in tokens(r.full_code):
            per_cat[tok][r.label].add(r.test_name)
            per_cat_proj[tok][r.label].add(r.project)

    total = sum(cat_size.values())
    for cat in sorted(cat_size):
        n_cat = cat_size[cat]
        scored = []
        for tok, byc in per_cat.items():
            a = len(byc.get(cat, ()))                       # tests in this category
            b = sum(len(v) for c, v in byc.items() if c != cat)
            if a < MIN_TESTS:
                continue
            if len(per_cat_proj[tok].get(cat, ())) < MIN_PROJECTS:
                continue
            # log-odds with add-one smoothing, against the rest of the flaky pool
            p_in = (a + 1) / (n_cat + 2)
            p_out = (b + 1) / (total - n_cat + 2)
            scored.append((math.log(p_in / p_out), a, len(per_cat_proj[tok][cat]), tok))
        scored.sort(reverse=True)
        print("=" * 74)
        print("%s   (%d held-out tests)" % (cat, n_cat))
        print("=" * 74)
        print("  %-28s %6s %9s  %s" % ("token", "tests", "projects", "log-odds"))
        for lo, a, np_, tok in scored[:TOP_N]:
            print("  %-28s %6d %9d  %+.2f" % (tok, a, np_, lo))
        print()


if __name__ == "__main__":
    main()
