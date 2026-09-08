"""Pilot 1: run SliceAnalysis over the `body` text already stored in the models.

No checkout. Pulls the stored Spoon pretty-print for every test we located, hands
it to SliceAnalysis in `snippets` mode, and reports the ablation:

    hazard anywhere   the tier-1 style baseline, but with typed sources
    hazard on path    the hazard actually feeds an assertion
    + exposure        through an operation that reveals the choice
    + uncontrolled    with nothing closing it

Restricted to unordered collections, which has the clearest hazard and control
vocabulary and 40 of its 41 flaky tests located.
"""
import collections
import csv
import glob
import json
import os
import subprocess
import sys

ROOT = r"D:\FSE-2027\FlakyLens"
SCRIPTS = os.path.join(ROOT, "docs", "investigation3", "scripts")
SP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)
from run_spoon_fb import stream_model                              # noqa: E402


def main():
    feats = {r["test_name"]: r for r in csv.DictReader(
        open(os.path.join(ROOT, "docs", "investigation3", "fb_features.csv"),
             encoding="utf-8"))}

    # which (build point, class, method) to pull, for tests we located
    want = {}
    for f in glob.glob(os.path.join(ROOT, "runs_fb", "_bp", "*", "tests_resolved.csv")):
        bp = os.path.basename(os.path.dirname(f))
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if r["method_found"] != "yes":
                continue
            fr = feats.get(r["test_name"])
            if not fr:
                continue
            # the flaky side is unordered collections only; the negative class is
            # every non-flaky test we can reach, judged by the same rules
            if fr["is_flaky"] == "yes" and fr["label"] != "unordered collections":
                continue
            key = r["test_name"]
            if key in want:
                continue
            want[key] = (bp, r["qualified_class"], r["test_method"].split("[")[0])

    by_bp = collections.defaultdict(dict)
    for key, (bp, qc, meth) in want.items():
        by_bp[bp][(qc, meth)] = key

    items = []
    for bp, targets in by_bp.items():
        path = os.path.join(ROOT, "runs_fb", "_bp", bp, "spoon_methods.json")
        if not os.path.isfile(path):
            continue
        for m in stream_model(path):
            k = (m.get("qualified_class"), m.get("method"))
            if k in targets and (m.get("body") or "").strip().startswith("{"):
                items.append({"key": targets[k], "body": m["body"]})
                del targets[k]

    print(f"tests wanted {len(want)}, bodies pulled {len(items)}")
    inp = os.path.join(SP, "slice_in.json")
    out = os.path.join(SP, "slice_out.json")
    json.dump(items, open(inp, "w", encoding="utf-8"),
              separators=(",", ":"))   # the Java reader scans for "key":" exactly

    cp = open(os.path.join(ROOT, "runs", "tools", "spoon_cp.txt"),
              encoding="utf-8").read().strip()
    import os as _os
    jvm = [f"-D{k}={v}" for k, v in
           (kv.split("=") for kv in _os.environ.get("SLICE_FLAGS", "").split() if kv)]
    rc = subprocess.run(["java", "-Xmx2g"] + jvm + ["-cp", cp,
                         os.path.join(SCRIPTS, "SliceAnalysis.java"),
                         "snippets", inp, out],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace")
    print(rc.stdout.strip()[-300:] or rc.stderr.strip()[-500:])
    if not os.path.isfile(out):
        return 1

    res = {r["key"]: r for r in json.load(open(out, encoding="utf-8"))}
    report(res, feats)
    return 0


def report(res, feats):
    groups = {"flaky (unordered)": [], "non-flaky": []}
    for k, r in res.items():
        fr = feats.get(k)
        if not fr:
            continue
        groups["flaky (unordered)" if fr["is_flaky"] == "yes" else "non-flaky"].append(r)

    print()
    print("=== PILOT 1: parse of the stored body text (no checkout) ===")
    parsed = {g: [r for r in v if r.get("parsed")] for g, v in groups.items()}
    for g, v in groups.items():
        print(f"  {g:20s} {len(v):5d} tests, parsed {len(parsed[g]):5d} "
              f"({100.0 * len(parsed[g]) / max(len(v), 1):.1f}%)")

    print()
    print(f"  {'stage':26s} {'flaky':>16s} {'non-flaky':>16s} {'lift':>7s}")
    stages = [("hazard anywhere (baseline)", lambda r: r.get("hazard_anywhere")),
              ("hazard on path", lambda r: r.get("hazard_on_path")),
              ("+ exposure", lambda r: r.get("hazard_on_path") and r.get("exposure")),
              ("+ uncontrolled = FLAG", lambda r: r.get("flag"))]
    fl, nf = parsed["flaky (unordered)"], parsed["non-flaky"]
    if not fl or not nf:
        print("  not enough parsed rows to report")
        return
    base = 100.0 * len(fl) / (len(fl) + len(nf))
    for label, pred in stages:
        a = sum(1 for r in fl if pred(r))
        b = sum(1 for r in nf if pred(r))
        ap = 100.0 * a / len(fl)
        bp = 100.0 * b / len(nf)
        lift = ((100.0 * a / (a + b)) / base) if a + b else 0.0
        print(f"  {label:26s} {a:4d} ({ap:5.1f}%) {b:7d} ({bp:5.1f}%) {lift:6.2f}x")


if __name__ == "__main__":
    sys.exit(main())
