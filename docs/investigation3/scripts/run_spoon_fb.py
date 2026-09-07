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
import difflib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_pair as rp                                            # noqa: E402

SKIP_DIRS = {".git", "target", "build", "node_modules", ".gradle", ".idea"}


PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)


def index_test_roots(src):
    """simple class name -> [java files], over the whole tree.

    An earlier version only indexed directories ending in src/test/java or
    src/main/java. That is the Maven convention, not a rule, and requiring it
    lost 26 of the first 77 build points outright: cassandra keeps tests under
    test/unit, CoreNLP under test/src, and androidx - 16 SHAs of the corpus by
    itself - does not match either. Those came back as no_test_class_found with
    an empty model, which looks like a missing test rather than a layout we
    refused to read.
    """
    by_name = collections.defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith(".java"):
                by_name[f[:-5]].append(os.path.join(dirpath, f))
    return by_name, {}


def source_root_of(java_file):
    """The package root above a .java file, derived from its own declaration.

    a/b/src/test/java/com/x/FooTest.java declaring `package com.x;` gives
    a/b/src/test/java. This works for any layout, including the ones that do not
    follow the Maven convention at all, because the file states its own package
    rather than the path implying it.
    """
    try:
        with open(java_file, encoding="utf-8", errors="replace") as fh:
            head = fh.read(8192)
    except Exception:
        return None
    m = PACKAGE.search(head)
    d = os.path.dirname(java_file)
    if not m:
        return d                              # default package: the file sits at the root
    parts = m.group(1).split(".")
    for want in reversed(parts):
        if os.path.basename(d) != want:
            return None                       # path and package disagree; skip it
        d = os.path.dirname(d)
    return d


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
            root = source_root_of(f)
            if root and root not in roots:
                roots.append(root)
            # the production sources that go with a test root, where the Maven
            # convention does hold; harmless when it does not
            norm = (root or "").replace("\\", "/")
            if norm.endswith("/src/test/java"):
                sibling = os.path.join(os.path.dirname(os.path.dirname(
                    root)), "main", "java")
                if os.path.isdir(sibling) and sibling not in roots:
                    roots.append(sibling)
    return roots, matches


_FULL_CODE = {}


def load_full_code(path):
    """(project, test_name) -> [full_code, ...], read once and shared.

    NOT keyed by `id`: 66 ids in FlakeBench_dataset.csv name two different tests
    (id 281 is both soot's TestDominance.TestSimpleDiamond and hadoop's
    TestOffsetRange.testConstructor1), so an id-keyed dict silently hands 66 rows
    somebody else's body and reports a bogus body_match for them.

    The value is a list because 110 (project, test_name) keys appear more than
    once — the same test at different commits, 107 of them with different bodies.
    Labels never conflict across those copies, so any copy matching is enough to
    say this commit holds a version FlakeBench labelled.
    """
    if not _FULL_CODE:
        try:
            for r in csv.DictReader(open(os.path.abspath(path), encoding="utf-8")):
                _FULL_CODE.setdefault((r["project"], r["test_name"]), []).append(
                    r["full_code"])
        except Exception as e:
            print(f"  warning: could not read the dataset for body matching: {e}")
            _FULL_CODE[("__missing__", "")] = [""]
    return _FULL_CODE


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

    # Stream the model instead of json.load-ing it, and keep only the classes
    # this build point actually asks about. Loading it whole cost 9x the file
    # size in Python objects - druid's 34 MB model peaked at 302 MB, so hadoop's
    # 157 MB would peak near 1.4 GB - and two of those alongside two 2 GB Spoon
    # JVMs is what got the first full sweep killed for memory at 59 of 172.
    # A build point names ~100 test classes out of tens of thousands of records,
    # so the filtered index is negligible.
    wanted = {c["test_class"] for c in spec["candidate_tests"] if c["test_class"]}
    # names that arrived without a class have to be found by method name instead
    bare = {rp.BRACKET.sub("", c["test_method"])
            for c in spec["candidate_tests"] if not c["test_class"]}
    by_simple = collections.defaultdict(list)
    by_method = collections.defaultdict(list)
    n_records = 0
    if os.path.isfile(spoon_json):
        try:
            for m in stream_model(spoon_json):
                n_records += 1
                if m.get("simple_class") in wanted:
                    by_simple[m["simple_class"]].append(m)
                if bare and m.get("method") in bare and m.get("kind") == "method":
                    by_method[m["method"]].append(m)
        except Exception as e:
            st["steps"].setdefault("spoon", {})["parse_error"] = str(e)
    st["steps"]["model"] = {"records": n_records}

    resolved = resolve_tests(spec, by_simple, by_method,
                             load_full_code(args.dataset), args.body_threshold)
    st["status"] = "ok" if n_records else "no_model"
    return finish(st, bp_dir, src, t0, args, spec, resolved)


WS = re.compile(r"\s+")


def body_similarity(a, b, cap=4000):
    """Ratio in [0,1] over whitespace-stripped bodies, length-capped for cost."""
    return difflib.SequenceMatcher(None, a[:cap], b[:cap]).ratio()


def body_match(extracted, full_code, threshold=0.85):
    """Does the source at this commit hold the body FlakeBench labelled?

    FlakeBench ships `full_code`, the test method as it stood when the label was
    assigned. That is an oracle, and it is needed rather than optional: the
    recorded SHA is not always the commit the body came from. Over the 10-build-
    point pilot, 641 tests resolved by name but only 501 carried a matching body,
    and 110 of the 140 mismatches were in single-SHA projects — so no other commit
    of that project exists to try.

    The consequence is specific. The body scope is safe either way, because it
    reads `full_code` directly. The fields, fixtures and production scopes are
    not: they would attribute a different version of the class to a body
    FlakeBench labelled at another commit. So this becomes the gate on those
    scopes rather than a diagnostic.

    Compared ignoring whitespace, and `contains` counts as a match because
    FlakeBench sometimes carries the method without its annotations.
    """
    a, b = WS.sub("", extracted or ""), WS.sub("", full_code or "")
    if not a or not b:
        return "unknown", 0.0
    if a == b:
        return "exact", 1.0
    if a in b or b in a:
        return "contains", 1.0
    r = body_similarity(a, b)
    return ("similar" if r >= threshold else "differs"), r


def stream_model(path):
    """Yield the model one record at a time.

    SpoonExtract writes exactly one JSON object per line and escapes every
    newline inside a body, so the file is line-delimited and needs no incremental
    parser - which keeps peak memory flat regardless of how large the model is.
    """
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line in ("[", "]"):
                continue
            if line.endswith(","):
                line = line[:-1]
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def resolve_tests(spec, by_simple, by_method=None, full_code_by_id=None,
                  threshold=0.85):
    """Which candidate tests this commit actually declares.

    Takes a prebuilt simple-class index rather than the whole model, so the
    caller can stream and filter.
    """
    full_code_by_id = full_code_by_id or {}
    by_method = by_method or {}
    project = spec["project"]

    RANK = {"exact": 4, "contains": 3, "similar": 2, "differs": 1, "unknown": 0}
    rows = []
    for c in spec["candidate_tests"]:
        want = rp.BRACKET.sub("", c["test_method"])

        # A name FlakeBench gave without a class (61 bare method names and 18
        # prefixed with a commit sha, all of them flaky) is looked up by method
        # name across the model instead. That is ambiguous on purpose: the
        # disambiguation is the body comparison below, which picks whichever
        # candidate class actually holds the body FlakeBench labelled.
        if c["test_class"]:
            in_class = by_simple.get(c["test_class"], [])
            hits = [m for m in in_class if m.get("method") == want]
        else:
            in_class = by_method.get(want, [])
            hits = in_class

        variants = full_code_by_id.get((project, c["test_name"]), [])
        scored = []
        for m in hits:
            for fc in (variants or [""]):
                lvl, sim = body_match(m.get("raw_body"), fc, threshold)
                scored.append((RANK[lvl], sim, lvl, m))
        if scored:
            _, sim, best, winner = max(scored, key=lambda x: (x[0], x[1]))
        else:
            sim, best, winner = 0.0, "unknown", None

        rows.append({
            "id": c["id"],
            "test_name": c["test_name"],
            "test_class": c["test_class"] or (winner or {}).get("simple_class", ""),
            "test_method": c["test_method"],
            "name_shape": c.get("name_shape", ""),
            "label": c["label"],
            "category": c["category"],
            "malformed": c["malformed"],
            "class_found": "yes" if in_class else "no",
            "classes_matching_simple_name":
                len({m.get("qualified_class") for m in in_class}),
            "method_found": "yes" if hits else "no",
            "qualified_class": (winner or hits[0] if hits else {}).get(
                "qualified_class", "") if hits else "",
            # the gate on the fields/fixtures/production scopes
            "body_match": best,
            "body_similarity": round(sim, 3),
            "usable_for_class_scopes":
                "yes" if best in ("exact", "contains", "similar") else "no",
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
        "body_matched": sum(1 for r in resolved
                            if r.get("usable_for_class_scopes") == "yes"),
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
          f"body_ok={st['resolved'].get('body_matched', 0)} "
          f"({st['resolved']['flaky_found']} flaky) {st['seconds']}s")
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--spec-dir")
    ap.add_argument("--tools", default=os.path.join("runs", "tools"))
    ap.add_argument("--dataset", default=os.path.join(
        os.path.dirname(HERE), "..", "..", "FlakeBench", "FlakeBench_dataset.csv"))
    ap.add_argument("--out", default="runs_fb")
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--keep", action="store_true",
                    help="keep the checkout (debugging; ~GB per build point)")
    ap.add_argument("--force", action="store_true",
                    help="re-run a build point that already has a model")
    ap.add_argument("--body-threshold", type=float, default=0.85,
                    help="similarity at or above which a differing body still "
                         "counts as the same test at another revision; the raw "
                         "ratio is stored per test so this can be re-tuned "
                         "without re-running anything")
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
