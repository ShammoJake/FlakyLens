"""Tier-1 feature extraction over FlakeBench — flaky AND non-flaky, one row per test.

    python extract_features_fb.py [--runs runs_fb] [--out fb_features.csv]

This is NOT the paired extractor. `extract_features.py` works on before/after
pairs and asks whether a flag survives a repair. There are no pairs here and no
sides: the unit is a single test, and the question is the opposite one — how
often does the liberal lexicon flag a test that is NOT flaky? That number is the
whole reason FlakeBench is in this study, and it needs the negative class treated
as a first-class subject rather than a control.

WHERE EACH SCOPE COMES FROM, AND WHY THAT MATTERS FOR COVERAGE

    test_body   FlakeBench's own `full_code`. Available for all 8,574 rows with
                no checkout at all, so the body-scope measurement never depends
                on whether a repository cloned or a commit still exists. This is
                also the text the label was assigned to, which makes it the right
                text to judge.

    fixtures    the Spoon model at the recorded commit: @Before / @After / @Rule
    fields      the Spoon model: declared fields of the test class and its
                superclasses

The two class-level scopes are gated on `usable_for_class_scopes` from
tests_resolved.csv. FlakeBench's recorded SHA is not always the commit its
`full_code` came from, so without the gate these scopes would attribute one
version of a class to a body labelled at another commit. Tests that fail the gate
keep their body-scope result and report the class scopes as unavailable, which is
the honest state rather than a silent zero.

The production scope is absent by construction: it needs JaCoCo, and whether that
run is worth its cost is exactly what this measurement decides.
"""
import argparse
import collections
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import extract_features as ef                                    # noqa: E402
from run_spoon_fb import stream_model                            # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
SCOPES = ["test_body", "fixtures", "fields"]


def class_scopes(model_by_class, qualified_class, want, fams):
    """Fixtures and fields for one test class, following the superclass chain."""
    chain, cur, guard = [], qualified_class, 0
    while cur and cur in model_by_class and guard < 10:
        chain.append(cur)
        sup = next((m.get("superclass") for m in model_by_class[cur]
                    if m.get("superclass")), "")
        cur = sup if sup and sup != "java.lang.Object" else ""
        guard += 1
    members = [m for c in chain for m in model_by_class[c]]

    fixtures, fields = [], []
    for m in members:
        kind = m.get("kind", "method")
        if kind == "field":
            fields.append(m)
        elif kind in ("static_init", "instance_init"):
            fixtures.append(m)
        elif m.get("method") != want:
            annots = m.get("annotations") or []
            if any(ef.FIXTURE_ANNOT.match("@" + a) for a in annots) or (
                    not annots and ef.FIXTURE_ANNOT.search(m.get("raw_body") or "")):
                fixtures.append(m)
    return chain, fixtures, fields


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs_fb")
    ap.add_argument("--dataset",
                    default=os.path.join(ROOT, "FlakeBench", "FlakeBench_dataset.csv"))
    ap.add_argument("--lexicon",
                    default=os.path.join(ROOT, "docs", "investigation2", "lexicon.json"))
    ap.add_argument("--out", default="fb_features.csv")
    args = ap.parse_args()

    fams, _ = ef.load_lexicon(args.lexicon)
    dataset = list(csv.DictReader(open(args.dataset, encoding="utf-8")))

    # best resolution per (project, test_name): a test in a multi-SHA project is a
    # candidate at every SHA, and one build point resolving it is enough
    best = {}
    for f in glob.glob(os.path.join(args.runs, "_bp", "*", "tests_resolved.csv")):
        bp = os.path.basename(os.path.dirname(f))
        for r in csv.DictReader(open(f, encoding="utf-8")):
            k = (r["test_name"],)
            rank = (r.get("usable_for_class_scopes") == "yes",
                    r["method_found"] == "yes")
            if k not in best or rank > best[k][0]:
                best[k] = (rank, bp, r)

    # Which classes each build point is actually asked about. Loading whole
    # models would repeat the mistake that killed the first sweep: json.load
    # costs about 9x the file size in Python objects, and caching 172 of them is
    # far beyond this machine. Stream each model once, keep only the classes
    # needed, and close over the superclass chain in a couple of extra passes.
    needed = collections.defaultdict(set)
    for (_tn,), (_rank, bp, r) in best.items():
        if r.get("qualified_class"):
            needed[bp].add(r["qualified_class"])

    models = {}

    def model_for(bp):
        if bp not in models:
            path = os.path.join(args.runs, "_bp", bp, "spoon_methods.json")
            by_class = collections.defaultdict(list)
            want = set(needed.get(bp, ()))
            for _pass in range(4):
                if not want:
                    break
                try:
                    for m in stream_model(path):
                        if m.get("qualified_class") in want:
                            by_class[m["qualified_class"]].append(m)
                except Exception:
                    break
                # a superclass we have not collected yet is another pass's work
                supers = {sup for c in list(by_class)
                          for sup in (rec.get("superclass") for rec in by_class[c])
                          if sup and sup != "java.lang.Object"}
                want = supers - set(by_class)
            models[bp] = by_class
        return models[bp]

    rows = []
    for t in dataset:
        label = t["label"]
        row = {
            "id": t["id"], "project": t["project"], "test_name": t["test_name"],
            "label": label, "category": t["category"],
            "is_flaky": "no" if label == "non-flaky" else "yes",
        }
        texts = {"test_body": t["full_code"], "fixtures": "", "fields": ""}

        hit = best.get((t["test_name"],))
        rec = hit[2] if hit else None
        row["located"] = rec["method_found"] if rec else "no"
        row["body_match"] = (rec or {}).get("body_match", "")
        # kept so the class-scope gate can be re-tuned in analysis without
        # re-running the sweep; "similar" is a threshold call, not a fact
        row["body_similarity"] = (rec or {}).get("body_similarity", "")
        usable = bool(rec) and rec.get("usable_for_class_scopes") == "yes"
        row["class_scopes_available"] = "yes" if usable else "no"

        if usable and rec.get("qualified_class"):
            by_class = model_for(hit[1])
            want = ef.BRACKET.sub("", rec["test_method"])
            chain, fx, fl = class_scopes(by_class, rec["qualified_class"], want, fams)
            texts["fixtures"] = "\n".join(ef.body_of(m) for m in fx)
            texts["fields"] = "\n".join(ef.body_of(m) for m in fl)
            row["class_chain"] = len(chain)
            row["fixtures_found"] = len(fx)
            row["fields_found"] = len(fl)
        else:
            row["class_chain"] = row["fixtures_found"] = row["fields_found"] = 0

        allh = set()
        for sc in SCOPES:
            h = ef.hits(texts[sc], fams)
            allh.update(h)
            row[f"{sc}_flagged"] = "yes" if h else "no"
            row[f"{sc}_hits"] = ";".join(sorted(h))
        row["any_flagged"] = "yes" if allh else "no"
        row["total_families"] = len(allh)
        rows.append(row)

    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    report(rows)
    print(f"\nwritten to {args.out}")
    return 0


def rate(rows, pred):
    n = sum(1 for r in rows if pred(r))
    return n, (100.0 * n / len(rows)) if rows else 0.0


def report(rows):
    flaky = [r for r in rows if r["is_flaky"] == "yes"]
    nonf = [r for r in rows if r["is_flaky"] == "no"]
    print(f"tests: {len(rows)}   flaky {len(flaky)}   non-flaky {len(nonf)}")

    print()
    print("=== SCOPE AVAILABILITY (both classes, so neither is measured on less) ===")
    for name, grp in (("flaky", flaky), ("non-flaky", nonf)):
        loc, lp = rate(grp, lambda r: r["located"] == "yes")
        usable, up = rate(grp, lambda r: r["class_scopes_available"] == "yes")
        print(f"  {name:10s} body 100%   located {loc:5d} ({lp:4.1f}%)   "
              f"class scopes {usable:5d} ({up:4.1f}%)")

    print()
    print("=== TIER-1 LIBERAL FLAG RATE ===")
    print(f"  {'scope':12s} {'flaky':>16s} {'non-flaky':>16s}")
    for sc in SCOPES + ["any"]:
        col = "any_flagged" if sc == "any" else f"{sc}_flagged"
        fn, fp = rate(flaky, lambda r: r[col] == "yes")
        nn, np_ = rate(nonf, lambda r: r[col] == "yes")
        print(f"  {sc:12s} {fn:6d} ({fp:5.1f}%) {nn:8d} ({np_:5.1f}%)")

    tp = sum(1 for r in flaky if r["any_flagged"] == "yes")
    fp = sum(1 for r in nonf if r["any_flagged"] == "yes")
    fn = len(flaky) - tp
    base = 100.0 * len(flaky) / len(rows)
    prec = 100.0 * tp / (tp + fp) if tp + fp else 0.0
    rec = 100.0 * tp / (tp + fn) if tp + fn else 0.0
    print()
    print(f"  as a classifier: precision {prec:.1f}%  recall {rec:.1f}%  "
          f"(base rate {base:.2f}%)")
    print(f"  flagging everything would give precision {base:.2f}% at recall 100%")

    print()
    print("=== BODY-SCOPE FLAG RATE BY CATEGORY (no checkout needed) ===")
    by = collections.defaultdict(list)
    for r in rows:
        by[r["label"]].append(r)
    for k in sorted(by, key=lambda x: -len(by[x])):
        n, p = rate(by[k], lambda r: r["test_body_flagged"] == "yes")
        print(f"  {k:26s} {n:5d}/{len(by[k]):5d} = {p:5.1f}%")


if __name__ == "__main__":
    sys.exit(main())
