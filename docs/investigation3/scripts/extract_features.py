"""Tier-1 feature extractor over a runs directory produced by run_group.py.

For every pair-side that has run, this resolves four scopes of source text and
applies the investigation-2 lexicon to each one separately:

    test_body     the flaky test method itself
    fixtures      @Before / @After / setUp / tearDown of the test class
    fields        declared fields of the test class          (see GAPS below)
    prod          production methods JaCoCo recorded as executed by this test

The point of keeping the scopes separate is that "the test body is clean but a
field it reads is a HashMap" and "the test body is clean and nothing it touches
is hazardous" are different claims, and only the second one is evidence.

Scopes degrade rather than lie. A model written by the current SpoonExtract
carries `kind`, `annotations`, `superclass` and field records; one written before
that carries methods only, and the run is reported as such instead of being
silently scored on a scope that was never collected:

    fields          "MISSING (model predates field extraction)" on an old model.
                    On a current one, the declared fields of the test class and
                    every superclass in the model.
    fixtures        annotation list if the model has one, else the annotations
                    that `raw_body` carries anyway, else a name heuristic. Static
                    and instance initialiser blocks count as fixtures — they run
                    on class load and do the same job.
    test_body       resolved by stripping the parameterised-instance suffix from
                    the IDoFT selector (`foo[ARRAY]` -> `foo`). The runner used to
                    match it literally, which is why test_method.json was empty on
                    103 of the first 115 sides.

This re-resolves everything from the Spoon model rather than trusting the
runner's own test_method.json, so it gives the right answer on runs collected
before those fixes landed.

Usage:
    python extract_features.py <runs_dir> [--lexicon path] [--out features.csv]
                               [--report report.json]
"""
import argparse
import collections
import csv
import json
import os
import re
import sys

BRACKET = re.compile(r"\[.*\]$")
STR = re.compile(r'"(?:\\.|[^"\\])*"')
CHR = re.compile(r"'(?:\\.|[^'\\])'")
LINE_COMMENT = re.compile(r"//[^\n]*")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)

# raw_body starts at the declaration, so the annotations are in it even though the
# model carries no annotation list; the name list below is the fallback.
FIXTURE_ANNOT = re.compile(
    r"@(?:Before|After)(?:Class|All|Each)?\b|@(?:Class)?Rule\b|@TestInstance\b")

FIXTURE_NAMES = re.compile(
    r"^(setUp|setup|tearDown|teardown|before|after|beforeEach|afterEach|"
    r"beforeAll|afterAll|beforeClass|afterClass|init|initialize|cleanUp|cleanup)",
    re.I)

TEST_PATH = re.compile(r"[\\/]src[\\/]test[\\/]|[\\/]test[\\/]java[\\/]", re.I)

SCOPES = ["test_body", "fixtures", "fields", "prod"]


def strip_source(s):
    """Remove comments and string/char literals so a token inside a message or a
    javadoc line does not raise a flag."""
    if not s:
        return ""
    return STR.sub('""', CHR.sub("' '", BLOCK_COMMENT.sub(" ", LINE_COMMENT.sub(" ", s))))


def load_lexicon(path):
    lex = json.load(open(path, encoding="utf-8"))
    fams, fam_label = {}, {}
    for cat, cd in lex["categories"].items():
        for fn, rx in cd["families"].items():
            key = f"{cat}.{fn}"
            fams[key] = re.compile(rx)
            fam_label[key] = cd["label"]
    return fams, fam_label


def hits(text, fams):
    t = strip_source(text)
    if not t.strip():
        return []
    return [k for k, rx in fams.items() if rx.search(t)]


def body_of(m):
    """Prefer the original source text; fall back to Spoon's pretty-print.

    raw_body is what a lexicon should see — it carries the writer's own idiom
    (`new HashMap<>()`), whereas `body` is fully qualified and reformatted.
    """
    return m.get("raw_body") or m.get("body") or ""


class SpoonCache:
    def __init__(self, runs):
        self.runs = runs
        self.cache = {}

    def get(self, rel):
        path = rel if os.path.isabs(rel) else os.path.join(self.runs, rel)
        path = os.path.normpath(path)
        if path not in self.cache:
            try:
                self.cache[path] = json.load(open(path, encoding="utf-8"))
            except Exception:
                self.cache[path] = []
        return self.cache[path]


def resolve_side(runs, pair_dir, side, meta, spoon_cache, fams):
    """Return one row of features, plus the per-scope availability flags."""
    side_dir = os.path.join(pair_dir, side)
    status_path = os.path.join(side_dir, "status.json")
    if not os.path.isfile(status_path):
        return None
    st = json.load(open(status_path, encoding="utf-8"))

    row = {
        "pair_id": meta.get("pair_id", ""),
        "side": side,
        "project_slug": meta.get("project_slug", ""),
        "test_class": meta.get("test_class", ""),
        "test_method": meta.get("test_method", ""),
        "flakebench_label": meta.get("flakebench_label", ""),
        "pr_touch": meta.get("pr_touch", ""),
        "run_status": st.get("status", ""),
    }

    spoon = spoon_cache.get(st.get("spoon_methods", "")) if st.get("spoon_methods") else []
    tc = meta.get("test_class", "")
    short = tc.rsplit(".", 1)[-1]
    want = BRACKET.sub("", meta.get("test_method", ""))

    # A model written by the current SpoonExtract tags every record with `kind`
    # and carries fields, annotations and the superclass link. Runs collected
    # before that only hold methods, so the scopes degrade rather than lie.
    has_fields = any(m.get("kind") == "field" for m in spoon)

    by_class = collections.defaultdict(list)
    for m in spoon:
        by_class[m.get("qualified_class")].append(m)

    # Walk up the superclass chain: an abstract test base class is a normal place
    # to keep @Before and the shared fields, and attributing them to the subclass
    # is the whole point of following the link.
    chain, cur, guard = [], tc, 0
    while cur and cur in by_class and guard < 10:
        chain.append(cur)
        sup = next((m.get("superclass") for m in by_class[cur] if m.get("superclass")), "")
        cur = sup if sup and sup != "java.lang.Object" else ""
        guard += 1
    if chain:
        in_class = [m for c in chain for m in by_class[c]]
    else:
        # no qualified-name match (a model built over a different module layout);
        # fall back to the simple name, which is what the runner used to do
        in_class = [m for m in spoon if m.get("simple_class") == short]
    row["class_chain"] = len(chain)

    executables = [m for m in in_class
                   if m.get("kind", "method") in ("method", "constructor",
                                                  "static_init", "instance_init")]

    # ---- scope 1: the test body
    tm = [m for m in executables if m.get("method") == want]
    row["test_body_available"] = "yes" if tm else "no"
    test_text = "\n".join(body_of(m) for m in tm)
    row["test_body_chars"] = len(test_text)

    # ---- scope 2: fixtures. Annotation list first, then the annotations that
    # raw_body carries anyway, then names.
    def is_fixture(m):
        if m.get("method") == want:
            return False
        if m.get("kind") in ("static_init", "instance_init"):
            return True            # runs on class load / construction, same role
        annots = m.get("annotations")
        if annots:
            return any(FIXTURE_ANNOT.match("@" + a) for a in annots)
        return bool(FIXTURE_ANNOT.search(m.get("raw_body") or ""))

    by_annot = [m for m in executables if is_fixture(m)]
    ids = {id(m) for m in by_annot}
    by_name = [m for m in executables
               if m.get("method") != want and id(m) not in ids
               and FIXTURE_NAMES.match(m.get("method") or "")]
    fx = by_annot + by_name
    fixture_text = "\n".join(body_of(m) for m in fx)
    row["fixtures_found"] = len(fx)
    row["fixtures_available"] = ("annotation" if by_annot
                                 else "name_only" if by_name else "none_found")

    # ---- scope 3: declared fields of the test class and its bases
    flds = [m for m in in_class if m.get("kind") == "field"]
    fields_text = "\n".join(body_of(m) for m in flds)
    row["fields_found"] = len(flds)
    row["fields_available"] = ("yes" if flds else "none_found" if has_fields
                               else "MISSING (model predates field extraction)")

    # ---- scope 4: executed production methods
    ewb = os.path.join(side_dir, "executed_with_bodies.json")
    prod_text, n_prod, n_prod_body = "", 0, 0
    if os.path.isfile(ewb):
        try:
            ex = json.load(open(ewb, encoding="utf-8"))
        except Exception:
            ex = []
        # join_spoon_coverage.py kept only `body` (Spoon's fully-qualified
        # pretty-print of the block). That is the wrong text for a lexicon: it
        # invents tokens by qualifying types (java.util.concurrent.* fires the
        # concurrency families) and drops the ones on the declaration line
        # (`synchronized`, annotations). Re-join raw_body from the model.
        by_desc = {(m["qualified_class"], m["descriptor"]): m for m in spoon}
        parts = []
        for m in ex:
            if m.get("match_level") == "unmatched":
                continue
            if TEST_PATH.search(m.get("file") or ""):
                continue
            if m.get("class") == tc:
                continue
            n_prod += 1
            src = by_desc.get((m.get("class"), m.get("descriptor")))
            b = (m.get("raw_body") or (src or {}).get("raw_body")
                 or m.get("body") or "")
            if b.strip() and b.strip() != "{}":
                n_prod_body += 1
                parts.append(b)
        prod_text = "\n".join(parts)
    row["prod_methods"] = n_prod
    row["prod_with_body"] = n_prod_body
    row["prod_available"] = "yes" if n_prod_body else "no"

    # ---- lexicon over each scope
    texts = {"test_body": test_text, "fixtures": fixture_text,
             "fields": fields_text, "prod": prod_text}
    all_hits = set()
    for sc in SCOPES:
        h = hits(texts[sc], fams)
        all_hits.update(h)
        row[f"{sc}_flagged"] = "yes" if h else "no"
        row[f"{sc}_families"] = len(h)
        row[f"{sc}_hits"] = ";".join(sorted(h))
    row["any_flagged"] = "yes" if all_hits else "no"
    row["total_families"] = len(all_hits)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs")
    ap.add_argument("--lexicon",
                    default=os.path.join("docs", "investigation2", "lexicon.json"))
    ap.add_argument("--out", default="features.csv")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    fams, _ = load_lexicon(args.lexicon)
    cache = SpoonCache(args.runs)

    rows = []
    for name in sorted(os.listdir(args.runs)):
        pair_dir = os.path.join(args.runs, name)
        meta_path = os.path.join(pair_dir, "meta.json")
        if not os.path.isfile(meta_path):
            continue
        meta = json.load(open(meta_path, encoding="utf-8")).get("pair", {})
        for side in ("before", "after"):
            r = resolve_side(args.runs, pair_dir, side, meta, cache, fams)
            if r:
                rows.append(r)

    if not rows:
        print("no pair sides found under", args.runs)
        return 1

    with open(args.out, "w", newline="\n", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # ---- availability report: what the runner actually delivered
    print(f"pair sides: {len(rows)}   families: {len(fams)}")
    print()
    print("=== SCOPE AVAILABILITY (can the extractor even see this scope?) ===")
    for key in ("test_body_available", "fixtures_available",
                "fields_available", "prod_available"):
        c = collections.Counter(r[key] for r in rows)
        print(f"  {key:22s} {dict(c)}")
    print()
    print("=== FLAG RATE PER SCOPE ===")
    for sc in SCOPES:
        n = sum(1 for r in rows if r[f"{sc}_flagged"] == "yes")
        print(f"  {sc:12s} flagged {n:4d}/{len(rows)}  "
              f"({100.0 * n / len(rows):5.1f}%)")
    n_any = sum(1 for r in rows if r["any_flagged"] == "yes")
    print(f"  {'ANY':12s} flagged {n_any:4d}/{len(rows)}  "
          f"({100.0 * n_any / len(rows):5.1f}%)")
    print()
    print("=== BEFORE vs AFTER (does the flag survive the fix?) ===")
    by_pair = collections.defaultdict(dict)
    for r in rows:
        by_pair[r["pair_id"]][r["side"]] = r
    both = {k: v for k, v in by_pair.items() if "before" in v and "after" in v}
    tally = collections.Counter()
    for k, v in both.items():
        tally[(v["before"]["any_flagged"], v["after"]["any_flagged"])] += 1
    for (b, a), n in sorted(tally.items()):
        print(f"  before={b:3s} after={a:3s}  {n:4d} pairs")
    print(f"  pairs with both sides: {len(both)}")

    if args.report:
        json.dump({"rows": len(rows), "pairs": len(both),
                   "availability": {k: dict(collections.Counter(r[k] for r in rows))
                                    for k in ("test_body_available",
                                              "fixtures_available",
                                              "fields_available",
                                              "prod_available")}},
                  open(args.report, "w", encoding="utf-8"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
