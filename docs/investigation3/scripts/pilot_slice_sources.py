"""Pilot 2: the same analysis over a real checkout, with full class context.

Pilot 1 parsed the stored `body` text and had to stop at the edge of the method:
fields, fixtures, helper methods and every production class were invisible. That
capped recall at 5% because only 28% of flaky unordered-collections tests carry a
typed hazard in the body itself.

This checks out the real source and runs SliceAnalysis over it, so the model
holds the whole test class and the production code beside it. The comparison that
matters is not the absolute numbers - the project mix differs - but whether the
same tests get a different verdict when the context is there.
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
import run_pair as rp                                              # noqa: E402
import run_spoon_fb as fb                                          # noqa: E402

# projects holding the most located unordered-collections flaky tests
PILOT_BPS = ["fastjson@e05e9c5e4be5", "ecchronos@caad1754c527",
             "junit-quickcheck@9361b6dae25b", "kylin@31ab93618311",
             "nutz@97745dd754eb"]


def main():
    feats = {r["test_name"]: r for r in csv.DictReader(
        open(os.path.join(ROOT, "docs", "investigation3", "fb_features.csv"),
             encoding="utf-8"))}
    cp = open(os.path.join(ROOT, "runs", "tools", "spoon_cp.txt"),
              encoding="utf-8").read().strip()

    specs = {os.path.basename(f)[:-5]: f
             for f in glob.glob(os.path.join(ROOT, "runs_fb", "_specs", "*.json"))}
    available = [b for b in PILOT_BPS if b in specs]
    print("pilot build points:", available)

    allres = {}
    for bp in available:
        spec = json.load(open(specs[bp], encoding="utf-8"))
        work = os.path.join(SP, "p2", bp.replace("@", "_"))
        src = os.path.join(work, "source")
        os.makedirs(work, exist_ok=True)

        if not os.path.isdir(src):
            used, err = rp.checkout(spec["project_url"], [spec["ref"]], src,
                                    os.path.join(work, "checkout.log"), 1800,
                                    require_pom=False)
            if used is None:
                print(f"  {bp}: checkout failed: {err}")
                continue

        by_name, _ = fb.index_test_roots(src)
        classes = sorted({c["test_class"] for c in spec["candidate_tests"]
                          if c["test_class"]})
        bare = sorted({c["test_method"].split("[")[0]
                       for c in spec["candidate_tests"] if not c["test_class"]})
        roots, _ = fb.roots_for(src, classes, by_name, bare)
        out = os.path.join(work, "slice.json")
        r = subprocess.run(["java", "-Xmx3g", "-cp", cp,
                            os.path.join(SCRIPTS, "SliceAnalysis.java"),
                            "sources", out] + roots,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=3600)
        print(f"  {bp}: roots={len(roots)} {r.stdout.strip()[-120:]}")
        if os.path.isfile(out):
            for rec in json.load(open(out, encoding="utf-8")):
                allres[rec["key"]] = rec

    # map qualified_class#method back to FlakeBench test names
    wanted = {}
    for f in glob.glob(os.path.join(ROOT, "runs_fb", "_bp", "*", "tests_resolved.csv")):
        if os.path.basename(os.path.dirname(f)) not in available:
            continue
        for row in csv.DictReader(open(f, encoding="utf-8")):
            if row["method_found"] == "yes" and row["qualified_class"]:
                wanted[row["qualified_class"] + "#"
                       + row["test_method"].split("[")[0]] = row["test_name"]

    matched = {}
    for k, rec in allres.items():
        if k in wanted:
            matched[wanted[k]] = rec
    print(f"\nanalysed methods {len(allres)}, matched to FlakeBench tests {len(matched)}")

    fl = [r for n, r in matched.items()
          if feats.get(n, {}).get("label") == "unordered collections"]
    nf = [r for n, r in matched.items()
          if feats.get(n, {}).get("is_flaky") == "no"]
    print(f"  flaky (unordered) {len(fl)}   non-flaky {len(nf)}")
    if not fl or not nf:
        print("  not enough matched rows to report")
        return 0

    print()
    print("=== PILOT 2: full source context ===")
    print(f"  {'stage':26s} {'flaky':>16s} {'non-flaky':>16s} {'lift':>7s}")
    base = 100.0 * len(fl) / (len(fl) + len(nf))
    for label, pred in [
            ("hazard anywhere (baseline)", lambda r: r.get("hazard_anywhere")),
            ("hazard on path", lambda r: r.get("hazard_on_path")),
            ("+ exposure", lambda r: r.get("hazard_on_path") and r.get("exposure")),
            ("+ uncontrolled = FLAG", lambda r: r.get("flag"))]:
        a = sum(1 for r in fl if pred(r))
        b = sum(1 for r in nf if pred(r))
        lift = ((100.0 * a / (a + b)) / base) if a + b else 0.0
        print(f"  {label:26s} {a:4d} ({100.0*a/len(fl):5.1f}%) "
              f"{b:7d} ({100.0*b/len(nf):5.1f}%) {lift:6.2f}x")

    json.dump({k: v for k, v in matched.items()},
              open(os.path.join(SP, "pilot2_matched.json"), "w", encoding="utf-8"),
              indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
