"""Spoon-only evidence pass over FlakeBench build points — no Maven, no JaCoCo.

    python run_spoon_fb.py --spec runs_fb/_specs/<bp>.json --tools runs/tools
    python run_spoon_fb.py --spec-dir runs_fb/_specs --tools runs/tools --jobs 2

WHY THIS EXISTS SEPARATELY FROM run_group.py
--------------------------------------------
`run_group.py` checks out, *builds*, runs one test per pair under the JaCoCo
agent, and reports. Almost all of that cost is the build and the test runs, and
none of it is needed for the scopes tier 1 is measured on. Spoon runs in
noclasspath mode: it needs sources and nothing else. So the test body, the class
fields, the fixtures and the superclass chain are all obtainable from a shallow
checkout with no Maven invocation at all.

That matters because the measurement it feeds — how often the liberal lexicon
flags a NON-flaky test — is what decides whether the expensive coverage pass is
worth running. Doing the cheap half first is the point.

WHY IT DOES NOT FEED THE WHOLE REPOSITORY TO SPOON
--------------------------------------------------
`apache/hadoop` and `wildfly` are hundreds of modules. Modelling all of them to
read one test class would be slow enough to matter across 175 build points and
would risk the heap. Instead the tree is indexed by `src/test/java` root, the
test classes named in the spec are located by simple name, and Spoon is given
only the modules that actually hold them — each module's `src/test/java` plus its
`src/main/java`, so a fixture's superclass and the module's own production code
are in the same model.

WHAT IT WRITES

    <out>/_bp/<bp>/spoon_methods.json   the model (shared by every test here)
    <out>/_bp/<bp>/tests_resolved.csv   one row per candidate test: found here or
                                        not, and how many classes matched the
                                        simple name
    <out>/_bp/<bp>/status.json          checkout / index / spoon step outcomes
"""
import argparse
import collections
import csv
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_pair as rp                                            # noqa: E402

SKIP_DIRS = {".git", "target", "build", "node_modules", ".gradle", ".idea"}


def index_test_roots(src):
    """simple class name -> [java files], plus the module root of each test root.

    One walk, pruned at the directories that never hold sources, because these
    trees are large and this runs 175 times.
    """
    by_name = collections.defaultdict(list)
    module_of = {}
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        norm = dirpath.replace("\\", "/")
        if not (norm.endswith("/src/test/java") or norm.endswith("/src/main/java")):
            continue
        module = os.path.dirname(os.path.dirname(os.path.dirname(dirpath)))
        module_of[dirpath] = module
        for sub, _, files in os.walk(dirpath):
            for f in files:
                if f.endswith(".java"):
                    by_name[f[:-5]].append(os.path.join(sub, f))
    return by_name, module_of


def roots_for(src, classes, by_name):
    """The module source roots that hold the named test classes.

    Returns (roots, per-class match counts). A class matched in two modules keeps
    both — the ambiguity is real (`test_name` carries no package) and is recorded
    rather than resolved by picking one.
    """
    roots, matches = [], {}
    for cls in classes:
        files = by_name.get(cls, [])
        matches[cls] = len(files)
        for f in files:
            norm = f.replace("\\", "/")
            for marker in ("/src/test/java/", "/src/main/java/"):
                if marker in norm:
                    module = norm.split(marker)[0]
                    for sub in ("test", "main"):
                        r = os.path.join(module.replace("/", os.sep),
                                         "src", sub, "java")
                        if os.path.isdir(r) and r not in roots:
                            roots.append(r)
                    break
    return roots, matches


def do_build_point(spec_path, tools, args):
    spec = json.load(open(spec_path, encoding="utf-8"))
    key = spec["build_point"]
    out_root = os.path.abspath(spec.get("out") or args.out)
    bp_dir = os.path.join(out_root, "_bp", key)
    os.makedirs(bp_dir, exist_ok=True)
    src = os.path.join(bp_dir, "source")
    t0 = time.time()

    st = {"build_point": key, "project": spec["project"],
          "project_slug": spec["project_slug"], "ref": spec["ref"],
          "n_shas_in_project": spec.get("n_shas_in_project", 1), "steps": {}}
    spoon_json = os.path.join(bp_dir, "spoon_methods.json")

    if args.force or not os.path.isfile(spoon_json):
        # require_pom=False: Spoon needs sources, not a build system, and
        # FlakeBench includes Gradle projects
        used, err = rp.checkout(spec["project_url"], [spec["ref"]], src,
                                os.path.join(bp_dir, "checkout.log"),
                                args.timeout_checkout, require_pom=False)
        st["steps"]["checkout"] = {"ok": used is not None, "ref": used, "error": err}
        if used is None:
            st["status"] = "checkout_failed"
            return finish(st, bp_dir, src, t0, args, spec, [])

        by_name, _ = index_test_roots(src)
        classes = sorted({c["test_class"] for c in spec["candidate_tests"]
                          if c["test_class"]})
        roots, matches = roots_for(src, classes, by_name)
        st["steps"]["index"] = {
            "ok": bool(roots),
            "classes_wanted": len(classes),
            "classes_located": sum(1 for c in classes if matches.get(c)),
            "classes_ambiguous": sum(1 for c in classes if matches.get(c, 0) > 1),
            "source_roots": len(roots),
        }
        if not roots:
            st["status"] = "no_test_class_found"
            return finish(st, bp_dir, src, t0, args, spec, [])

        cp = open(tools["SPOON_CP_FILE"], encoding="utf-8").read().strip()
        rcs, outs = rp.run(["java", "-Xmx" + args.xmx_spoon, "-cp", cp,
                            os.path.join(HERE, "SpoonExtract.java"), spoon_json] + roots,
                           cwd=src, log=os.path.join(bp_dir, "spoon.log"),
                           timeout=args.timeout_spoon)
        st["steps"]["spoon"] = {"ok": rcs == 0, "rc": rcs,
                                "summary": (outs or "").strip().splitlines()[-1:]}

    model = []
    if os.path.isfile(spoon_json):
        try:
            model = json.load(open(spoon_json, encoding="utf-8"))
        except Exception as e:
            st["steps"].setdefault("spoon", {})["parse_error"] = str(e)
    st["steps"]["model"] = {"records": len(model)}

    resolved = resolve_tests(spec, model)
    st["status"] = "ok" if model else "no_model"
    return finish(st, bp_dir, src, t0, args, spec, resolved)


def resolve_tests(spec, model):
    """Which candidate tests this commit actually declares."""
    by_simple = collections.defaultdict(list)
    for m in model:
        by_simple[m.get("simple_class")].append(m)

    rows = []
    for c in spec["candidate_tests"]:
        want = rp.BRACKET.sub("", c["test_method"])
        in_class = by_simple.get(c["test_class"], [])
        hits = [m for m in in_class if m.get("method") == want]
        rows.append({
            "id": c["id"],
            "test_name": c["test_name"],
            "test_class": c["test_class"],
            "test_method": c["test_method"],
            "label": c["label"],
            "category": c["category"],
            "malformed": c["malformed"],
            "class_found": "yes" if in_class else "no",
            "classes_matching_simple_name":
                len({m.get("qualified_class") for m in in_class}),
            "method_found": "yes" if hits else "no",
            "qualified_class": hits[0]["qualified_class"] if hits else "",
        })
    return rows


def finish(st, bp_dir, src, t0, args, spec, resolved):
    if resolved:
        with open(os.path.join(bp_dir, "tests_resolved.csv"), "w",
                  encoding="utf-8", newline="\n") as fh:
            w = csv.DictWriter(fh, fieldnames=list(resolved[0]))
            w.writeheader()
            w.writerows(resolved)
    st["resolved"] = {
        "candidates": len(spec["candidate_tests"]),
        "method_found": sum(1 for r in resolved if r["method_found"] == "yes"),
        "flaky_found": sum(1 for r in resolved
                           if r["method_found"] == "yes" and r["label"] != "non-flaky"),
    }
    st["seconds"] = round(time.time() - t0, 1)
    if not args.keep and os.path.isdir(src):
        # the checkout is the only large thing here and a fetch of the recorded
        # SHA brings it back; 175 of them retained would be hundreds of GB
        st["source_removed"] = rp.rmtree_hard(src)
    json.dump(st, open(os.path.join(bp_dir, "status.json"), "w",
                       encoding="utf-8"), indent=1)
    print(f"  {st['build_point']}: {st.get('status')} "
          f"model={st['steps'].get('model', {}).get('records', 0)} "
          f"found={st['resolved']['method_found']}/{st['resolved']['candidates']} "
          f"({st['resolved']['flaky_found']} flaky) {st['seconds']}s")
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--spec-dir")
    ap.add_argument("--tools", default=os.path.join("runs", "tools"))
    ap.add_argument("--out", default="runs_fb")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--keep", action="store_true",
                    help="keep the checkout (debugging; ~GB per build point)")
    ap.add_argument("--force", action="store_true",
                    help="re-run a build point that already has a model")
    ap.add_argument("--xmx-spoon", default=rp.XMX["spoon"])
    ap.add_argument("--timeout-checkout", type=int, default=1800)
    ap.add_argument("--timeout-spoon", type=int, default=3600)
    args = ap.parse_args()

    tools = rp.load_tools(args.tools)
    specs = []
    if args.spec:
        specs = [args.spec]
    elif args.spec_dir:
        specs = sorted(os.path.join(args.spec_dir, f)
                       for f in os.listdir(args.spec_dir)
                       if f.endswith(".json"))
    else:
        ap.error("one of --spec or --spec-dir is required")
    if args.limit:
        specs = specs[:args.limit]

    print(f"build points: {len(specs)}   jobs: {args.jobs}")
    results = []
    if args.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            for st in ex.map(lambda s: do_build_point(s, tools, args), specs):
                results.append(st)
    else:
        for s in specs:
            results.append(do_build_point(s, tools, args))

    ok = sum(1 for r in results if r.get("status") == "ok")
    found = sum(r["resolved"]["method_found"] for r in results)
    flaky = sum(r["resolved"]["flaky_found"] for r in results)
    print(f"\nbuild points ok {ok}/{len(results)}   "
          f"test methods located {found} ({flaky} flaky)")
    print("note: a test in a multi-SHA project is a candidate at every SHA, so "
          "the located count is over build points, not distinct tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
