"""Join JaCoCo-executed methods to the Spoon model, so every covered method
carries its source body.

    python join_spoon_coverage.py <executed_methods.csv> <spoon_methods.json> <out.json>

Matching is tiered, because the two sides disagree in known ways:

  exact       (class, method, descriptor)  — the normal case
  arity       (class, method, param count) — Spoon erases type variables to
              java.lang.Object, so a generic method's descriptor can differ from
              the one in the bytecode
  simple      (simple class name, method, param count) — last resort, only when
              the qualified names disagree

A fourth level, `synthetic`, marks methods javac generated and Spoon therefore
cannot see: `<clinit>`, enum constructors with their implicit (String, int)
prefix, `lambda$...`, `access$...`. Those are excluded from the match-rate
denominator.

`match_level` records which tier fired, so a later analysis can drop anything
below `exact` if it wants to. Rows that match nothing are kept with an empty body
rather than dropped: a covered, non-synthetic method Spoon cannot see is a
finding, not a nuisance.
"""
import csv
import json
import re
import sys

# Methods javac generates and Spoon can never see, because they have no
# declaration in the source. Counting these as misses makes the join look far
# worse than it is: in the first pair tested, all 8 "unmatched" rows were these.
SYNTH_NAME = re.compile(r"^(lambda\$|access\$|\$SWITCH_TABLE|\$values|values$|valueOf$)")


ANON_CLASS = re.compile(r"\$\d+$")


def is_synthetic(cls, meth, desc):
    if meth == "<clinit>":
        return True
    if SYNTH_NAME.search(meth):
        return True
    # enum constructors carry an implicit (String name, int ordinal) prefix
    if meth == "<init>" and desc.startswith("(Ljava/lang/String;I"):
        return True
    # an anonymous class declares no constructor in source; javac synthesises one.
    # Its other methods do match — in the zerocode pair, Adapter$1.create(..) matched
    # exactly while Adapter$1.<init>() did not — so this is about the constructor
    # alone, not about anonymous classes being invisible.
    if meth == "<init>" and ANON_CLASS.search(cls):
        return True
    return False


def param_count(desc):
    """Count parameters in a JVM descriptor: (Ljava/lang/String;I[J)V -> 3."""
    if not desc or not desc.startswith("("):
        return -1
    i, n = 1, 0
    while i < len(desc) and desc[i] != ")":
        while desc[i] == "[":
            i += 1
        if desc[i] == "L":
            i = desc.index(";", i) + 1
        else:
            i += 1
        n += 1
    return n


def build_indexes(spoon):
    exact, arity, simple = {}, {}, {}
    for m in spoon:
        cls, meth = m["qualified_class"], m["method"]
        exact.setdefault((cls, meth, m["descriptor"]), m)
        arity.setdefault((cls, meth, m["arity"]), m)
        simple.setdefault((m["simple_class"], meth, m["arity"]), m)
    return exact, arity, simple


def main(cov_csv, spoon_json, out_json):
    spoon = json.load(open(spoon_json, encoding="utf-8"))
    exact, arity, simple = build_indexes(spoon)

    out, stats = [], {"exact": 0, "arity": 0, "simple": 0,
                      "synthetic": 0, "unmatched": 0}
    for row in csv.DictReader(open(cov_csv, encoding="utf-8")):
        cls, meth, desc = row["class"], row["method"], row["descriptor"]
        n = param_count(desc)
        hit, level = exact.get((cls, meth, desc)), "exact"
        if hit is None:
            hit, level = arity.get((cls, meth, n)), "arity"
        if hit is None:
            hit, level = simple.get((cls.rsplit(".", 1)[-1], meth, n)), "simple"
        if hit is None:
            level = "synthetic" if is_synthetic(cls, meth, desc) else "unmatched"
        stats[level] += 1

        out.append({
            "class": cls,
            "method": meth,
            "descriptor": desc,
            "nesting": row["nesting"],
            "lines_covered": int(row["lines_covered"]),
            "lines_total": int(row["lines_total"]),
            "branches_covered": int(row["branches_covered"]),
            "branches_missed": int(row["branches_missed"]),
            "match_level": level,
            "file": hit["file"] if hit else "",
            "line_start": hit["line_start"] if hit else -1,
            "line_end": hit["line_end"] if hit else -1,
            "is_anonymous": hit["is_anonymous"] if hit else row["nesting"] == "anonymous",
            "is_test": hit["is_test"] if hit else False,
            "signature": hit["signature"] if hit else "",
            "modifiers": hit["modifiers"] if hit else [],
            "invokes": hit["invokes"] if hit else [],
            "annotations": (hit.get("annotations") if hit else []) or [],
            # Both bodies, because they are not interchangeable. `body` is Spoon's
            # pretty-print of the block: every type fully qualified, modifiers and
            # annotations gone. A lexicon run over it reports tokens the author
            # never wrote (java.util.concurrent.* fired the concurrency family on
            # 100% of sides) and misses ones they did (`synchronized` lives on the
            # declaration, so it showed on 2% instead of 91%). `raw_body` is the
            # original declaration text and is what any token-level feature wants.
            "body": hit["body"] if hit else "",
            "raw_body": (hit.get("raw_body") if hit else "") or "",
        })

    json.dump(out, open(out_json, "w", encoding="utf-8"), indent=1)
    total = len(out)
    matched = stats["exact"] + stats["arity"] + stats["simple"]
    # synthetic rows are excluded from the denominator: they are unmatchable by
    # construction, so counting them as failures understates the real join rate
    denom = total - stats["synthetic"]
    print("joined={} matched={} of {} ({:.1f}%) exact={} arity={} simple={} "
          "synthetic={} unmatched={}".format(
              total, matched, denom, (100.0 * matched / denom) if denom else 0.0,
              stats["exact"], stats["arity"], stats["simple"],
              stats["synthetic"], stats["unmatched"]))
    return stats


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
