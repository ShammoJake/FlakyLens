"""Walk one test through the whole step-2 pipeline and print every stage.

Usage:  python trace_one.py TestPathData.testCwdContents
        python trace_one.py                      # lists available tests
"""
import os, re, sys, json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from slice_and_count import strip_noise, slices_for, CATS, count  # noqa: E402

BASE = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(BASE, "sources")
NAME = {"async": "async wait", "conc": "concurrency", "time": "time",
        "uc": "unordered collections", "od": "test order dependency"}
TRUTH2CAT = {"async": "async", "conc": "conc", "time": "time",
             "UC": "uc", "OD": "od"}


def hr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def matched(text, cat):
    """[(family, [matched strings])] for the families that fire."""
    out = []
    for fam, pat in CATS[cat]["families"].items():
        hits = re.findall(pat, text, re.M)
        hits = [h if isinstance(h, str) else h[0] for h in hits]
        hits = [" ".join(h.split())[:46] for h in hits if h and h.strip()]
        if hits:
            seen, uniq = set(), []
            for h in hits:
                if h not in seen:
                    seen.add(h); uniq.append(h)
            out.append((fam, uniq))
    return out


def main(target):
    idx = pd.read_csv(os.path.join(SRC, "index.csv"))
    idx = idx[idx.file.notna()]
    if not target:
        print("\n".join(sorted(idx.test))); return
    row = idx[idx.test.str.endswith(target) | (idx.test == target)]
    if row.empty:
        sys.exit("not found: %s" % target)
    r = row.iloc[0]
    path = os.path.join(SRC, r.project, r.file)
    meth = r.test.split(".")[-1]

    hr("0. THE TEST")
    print("test        %s" % r.test)
    print("project     %s" % r.project)
    print("commit      %s" % r.sha)
    print("file        %s" % r.path)
    print("ground truth %-24s FlakyLens predicted %s" % (r.truth, r.pred))
    print("this is %s" % ("a MISS" if r.wrong else "a hit"))

    bench = pd.read_csv(os.path.join(BASE, "..", "..", "FlakeBench",
                                     "FlakeBench_dataset.csv"))
    bb = bench[(bench.project == r.project) & (bench.test_name == r.test)]

    raw = open(path, encoding="utf-8", errors="replace").read()
    hr("1. STRIP COMMENTS AND STRING CONTENTS")
    clean = strip_noise(raw)
    print("raw file      %5d lines, %6d chars" % (raw.count("\n") + 1, len(raw)))
    print("after strip   %5d lines, %6d chars" % (clean.count("\n") + 1, len(clean)))
    print("\nA single left-to-right scan, not a regex. Line structure is preserved so")
    print("line numbers still line up; only comment text and literal contents go.")

    hr("2. SPLIT THE CLASS INTO SLICES")
    sl = slices_for(clean, meth)
    if not bb.empty:
        cloned_body = sl["body"]
        sl["body"] = strip_noise(bb.iloc[0].full_code)
        sl["context"] = chr(10).join([sl["fields"], sl["fixtures"],
                                      sl["siblings"], sl["helpers"]])
        same = " ".join(cloned_body.split()) == " ".join(sl["body"].split())
        print("\nBody slice taken from FlakeBench full_code (what the model saw).")
        print("The copy at the pinned commit is %s."
              % ("identical" if same else "DIFFERENT - the test changed between them"))
    order = ["body", "fields", "fixtures", "siblings", "helpers", "context"]
    print("%-10s %6s   %s" % ("slice", "lines", "what it is"))
    what = {"body": "the test method under analysis, nothing else",
            "fields": "class-level field declarations",
            "fixtures": "@Before / @After / @BeforeClass / @AfterClass bodies",
            "siblings": "the other @Test methods in this class",
            "helpers": "non-test methods the body actually calls",
            "context": "fields + fixtures + siblings + helpers"}
    for k in order:
        n = len(sl[k].split("\n")) if sl[k].strip() else 0
        print("%-10s %6d   %s" % (k, n, what[k]))

    print("\n--- body -------------------------------------------------------------")
    print(sl["body"].strip())
    print("\n--- fields -----------------------------------------------------------")
    print(sl["fields"].strip() or "(none)")
    print("\n--- fixtures ---------------------------------------------------------")
    print(sl["fixtures"].strip()[:900] or "(none)")
    print("\n--- helpers called from the body -------------------------------------")
    print(sl["helpers"].strip()[:900] or "(none)")

    hr("3. MATCH THE LEXICON, SLICE BY SLICE")
    truth = TRUTH2CAT.get(r.truth)
    pred = TRUTH2CAT.get(r.pred)
    for k in ["body", "fields", "fixtures", "helpers"]:
        print("\n[%s]" % k)
        any_hit = False
        for cat in CATS:
            ms = matched(sl[k], cat)
            if not ms:
                continue
            any_hit = True
            tag = ""
            if cat == truth: tag = "   <- TRUE category"
            elif cat == pred: tag = "   <- what the model said"
            print("  %-22s %d families%s" % (NAME[cat], len(ms), tag))
            for fam, hits in ms:
                print("      %-16s %s" % (fam, ", ".join(hits[:4])))
        if not any_hit:
            print("  (no families fire)")

    hr("4. SCORE = DISTINCT FAMILIES PRESENT")
    print("Counting families, not occurrences: context is far longer than a body,")
    print("so raw counts would reward length instead of signal.\n")
    hdr = "%-10s" % "slice" + "".join("%9s" % c for c in CATS)
    print(hdr); print("-" * len(hdr))
    for k in order:
        line = "%-10s" % k
        for cat in CATS:
            _, f = count(sl[k], cat)
            line += "%9d" % f
        print(line)

    hr("5. ARGMAX, BODY ONLY vs BODY + CONTEXT")
    for tag, keys in [("body only", ["body"]),
                      ("body + fields/fixtures", ["body", "fields", "fixtures"]),
                      ("body + full context", ["body", "context"])]:
        score = {c: sum(count(sl[k], c)[1] for k in keys) for c in CATS}
        best = max(score.values())
        winners = [c for c in CATS if score[c] == best]
        pick = winners[0]
        verdict = "CORRECT" if pick == truth else "wrong"
        print("\n%s" % tag)
        print("  " + "  ".join("%s=%d" % (c, score[c]) for c in CATS))
        print("  argmax -> %-24s %s%s"
              % (NAME[pick], verdict,
                 "   (%d-way tie)" % len(winners) if len(winners) > 1 else ""))

    hr("6. WHAT THIS ONE TEST CONTRIBUTES")
    print("It is one row of 80. The reported numbers are what happens when the same")
    print("procedure runs over all of them:")
    print("  - coverage        does the TRUE category fire at all, per slice")
    print("  - argmax proxy    the step-5 decision, ties broken at random")
    print("  - flip analysis   did adding context move this test toward the truth")
    print("  - trained model   family-presence vector as features, cross-validated")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
