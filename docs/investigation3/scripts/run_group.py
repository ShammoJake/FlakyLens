#!/usr/bin/env python3
"""Collect evidence for ONE build point — one (project, commit) — and every test
that lands on it.

    python run_group.py --spec group.json --tools tools [--keep] [--isolate auto|always|never]

WHY A BUILD POINT AND NOT A PAIR
--------------------------------
`run_pair.py` treats a pair-side as the unit of work, so it checks out, builds and
runs Spoon once per side. That is enormously redundant: pairs sharing a PR share
both commits, and on the 343-pair JDK-11 slice the 686 sides collapse to **199
distinct build points, a 3.4x reduction**. The clustering is extreme in places —
google/TestParameterInjector is 51 pairs over 2 build points, and
alibaba/innodb-java-reader 45 pairs over 2.

Spoon is the worse offender of the two. Its output depends only on the source
tree, so those 51 TestParameterInjector sides were about to produce 51 identical
JSON files. Here it runs once per build point and every test on that commit joins
against the same model.

WHAT IT DOES
------------
    checkout once  ->  build the union of the needed modules once  ->  Spoon once
      ->  for each test: mvn test -Dtest=... under the agent, report, collect, join

Shared artefacts live in `<out>/_bp/<project>@<sha>/`; per-test artefacts and the
join land in the pair's own directory, so the product stays exactly where
`run_pair.py` put it and nothing downstream has to change.

ISOLATION BETWEEN TESTS
-----------------------
Sharing a working tree across tests is safe for implementation-dependent
flakiness, and NOT obviously safe for order-dependent or non-idempotent-outcome
tests — a test that pollutes the tree is precisely the phenomenon under study, so
letting it leak into the next test could manufacture or mask the effect.
`--isolate auto` (the default) therefore restores the tree between tests whenever
any test on this build point is OD or NIO, and skips the cost otherwise. What it
does is recorded per test, so the choice is auditable rather than implicit.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_pair as rp                                            # noqa: E402


def bp_key(project_url, ref):
    repo = project_url.rstrip("/").rsplit("/", 1)[-1]
    return f"{rp.sanitize(repo, 24)}@{rp.sanitize(ref, 12)}"


def restore_tree(src, log):
    """Undo whatever the last test wrote, without throwing away compiled classes.

    `git clean -xdf` alone would delete every target/ directory and force a full
    rebuild before the next test, which defeats the entire point of grouping."""
    rp.run(["git", "checkout", "--", "."], cwd=src, timeout=300)
    rp.run(["git", "clean", "-xdff", "-e", "target", "-e", "*/target", "-e", "**/target"],
           cwd=src, log=log, timeout=300)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--tools", default=os.path.join(HERE, "tools"))
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--isolate", choices=["auto", "always", "never"], default="auto")
    ap.add_argument("--no-fast-test", action="store_true",
                    help="always use the `test` lifecycle phase instead of trying "
                         "the surefire:test goal first")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--maven-repo", default="")
    ap.add_argument("--xmx-maven", default=rp.XMX["maven"])
    ap.add_argument("--xmx-spoon", default=rp.XMX["spoon"])
    ap.add_argument("--timeout-checkout", type=int, default=900)
    ap.add_argument("--timeout-build", type=int, default=2700)
    ap.add_argument("--timeout-test", type=int, default=900)
    ap.add_argument("--timeout-report", type=int, default=600)
    ap.add_argument("--timeout-spoon", type=int, default=1200)
    args = ap.parse_args()

    rp.XMX["maven"], rp.XMX["spoon"] = args.xmx_maven, args.xmx_spoon
    if args.maven_repo:
        rp.MAVEN_REPO.append("-Dmaven.repo.local=" + os.path.abspath(args.maven_repo))

    spec = json.load(open(args.spec, encoding="utf-8"))
    out_root = os.path.abspath(spec["out"])
    url, ref, ref_kind = spec["project_url"], spec["ref"], spec.get("ref_kind", "")
    tests = spec["tests"]
    key = bp_key(url, ref)
    bp_dir = os.path.join(out_root, "_bp", key)
    os.makedirs(bp_dir, exist_ok=True)
    tools = rp.load_tools(args.tools)

    st = {"build_point": key, "project_url": url, "ref": ref, "ref_kind": ref_kind,
          "tests": len(tests), "started": time.strftime("%Y-%m-%dT%H:%M:%S"), "steps": {}}
    done_marker = os.path.join(bp_dir, "status.json")
    if os.path.isfile(done_marker) and not args.force:
        prev = json.load(open(done_marker, encoding="utf-8"))
        if prev.get("status") == "ok" and prev.get("tests") == len(tests):
            print(f"{key}: already done")
            return 0

    src = os.path.join(bp_dir, "source")
    t0 = time.time()

    # ---- checkout once
    used, err = rp.checkout(url, [ref], src, os.path.join(bp_dir, "checkout.log"),
                            args.timeout_checkout)
    st["steps"]["checkout"] = {"ok": used is not None, "ref": used, "error": err}
    if used is None:
        st["status"] = "checkout_failed"
        return finish(st, bp_dir, src, tests, out_root, args, t0)

    # ---- build the union of every module these tests need, in one invocation
    modules = sorted({t.get("module") or "." for t in tests})
    pl = ",".join(modules)
    cmd = (["mvn", "-B", "-pl", pl, "-am", "-DskipTests", "install"]
           + rp.GATE_SKIPS + rp.MAVEN_REPO)
    rc, out = rp.run(cmd, cwd=src, log=os.path.join(bp_dir, "build.log"),
                     timeout=args.timeout_build, env=rp.maven_env())
    st["steps"]["build"] = {"ok": rc == 0, "rc": rc, "modules": modules,
                            "error": rp.first_error(out)}

    # ---- Spoon once, over the same roots the coverage report will span
    spoon_json = os.path.join(bp_dir, "spoon_methods.json")
    roots = []
    _, built_sources = rp.module_roots(src)
    roots.extend(built_sources)
    for m in modules:
        for sub in ("test", "main"):
            p = os.path.join(src, m, "src", sub, "java")
            if os.path.isdir(p) and p not in roots:
                roots.append(p)
    if roots and (args.force or not os.path.isfile(spoon_json)):
        cp = open(tools["SPOON_CP_FILE"], encoding="utf-8").read().strip()
        rcs, _ = rp.run(["java", "-Xmx" + rp.XMX["spoon"], "-cp", cp,
                         os.path.join(HERE, "SpoonExtract.java"), spoon_json] + roots,
                        cwd=src, log=os.path.join(bp_dir, "spoon.log"),
                        timeout=args.timeout_spoon)
    n_methods = 0
    if os.path.isfile(spoon_json):
        try:
            n_methods = len(json.load(open(spoon_json, encoding="utf-8")))
        except Exception:
            n_methods = -1
    st["steps"]["spoon"] = {"ok": n_methods > 0, "methods": n_methods,
                            "roots": [os.path.relpath(r, src) for r in roots]}

    # the Spoon model is shared, so index the test methods once
    spoon_all = []
    if os.path.isfile(spoon_json):
        try:
            spoon_all = json.load(open(spoon_json, encoding="utf-8"))
        except Exception:
            spoon_all = []

    isolate = args.isolate == "always" or (
        args.isolate == "auto"
        and any((t.get("category") or "").upper().startswith(("OD", "NIO"))
                for t in tests))
    st["isolate_between_tests"] = isolate

    # ---- one test at a time against the shared build
    results = []
    for i, t in enumerate(tests):
        side_dir = os.path.join(out_root, t["pair_dir"], t["side"])
        os.makedirs(side_dir, exist_ok=True)
        r = {"pair_id": t["pair_id"], "side": t["side"], "ref_kind": ref_kind,
             "build_point": key, "spoon_methods": os.path.relpath(spoon_json, out_root),
             "steps": dict(st["steps"])}

        # The flaky test method itself, out of the shared model.
        #
        # IDoFT names a parameterised instance `formatTestNameString_success[ARRAY]`,
        # but the declared Java method is `formatTestNameString_success`. Matching
        # the selector literally therefore found nothing for every parameterised
        # test, and wrote an empty test_method.json — 103 of the first 115 sides,
        # all of TestParameterInjector among them. Strip the instance suffix.
        short = t["test_class"].rsplit(".", 1)[-1]
        want = rp.BRACKET.sub("", t["test_method"])
        hits = [m for m in spoon_all
                if m["method"] == want
                and (m["qualified_class"] == t["test_class"] or m["simple_class"] == short)]
        json.dump(hits, open(os.path.join(side_dir, "test_method.json"), "w",
                             encoding="utf-8"), indent=1)
        r["steps"]["test_method_found"] = len(hits) > 0

        if st["steps"]["build"]["ok"]:
            if isolate and i > 0:
                restore_tree(src, os.path.join(bp_dir, "clean.log"))
            exec_file = os.path.abspath(os.path.join(side_dir, "jacoco.exec"))
            if os.path.isfile(exec_file):
                os.remove(exec_file)
            rc, note, fb = rp.mvn_test_with_jacoco(
                src, t.get("module") or ".", t["test_class"], t["test_method"],
                exec_file, tools["JACOCO_VERSION"], tools["JACOCO_AGENT"],
                os.path.join(side_dir, "test.log"), args.timeout_test,
                fast=not args.no_fast_test)
            have = os.path.isfile(exec_file) and os.path.getsize(exec_file) > 0
            r["steps"]["test"] = {"ok": have, "rc": rc, "note": note,
                                  "argline_fallback": fb, "test_passed": rc == 0}
            if have:
                xml = os.path.abspath(os.path.join(side_dir, "coverage.xml"))
                rcr, errr, cls, srcs = rp.jacoco_report(
                    src, exec_file, xml, tools["JACOCO_CLI"],
                    os.path.join(side_dir, "report.log"), args.timeout_report)
                r["steps"]["report"] = {"ok": rcr == 0, "error": errr,
                                        "classfile_dirs": len(cls),
                                        "sourcefile_dirs": len(srcs)}
                if rcr == 0:
                    cov = os.path.join(side_dir, "executed_methods.csv")
                    rc1, o1 = rp.run([sys.executable,
                                      os.path.join(HERE, "collect_coverage.py"), xml, cov],
                                     timeout=600)
                    r["steps"]["collect_coverage"] = {"ok": rc1 == 0,
                                                      "summary": o1.strip().splitlines()[-1:]}
                    if os.path.isfile(cov) and os.path.isfile(spoon_json):
                        rc2, o2 = rp.run([sys.executable,
                                          os.path.join(HERE, "join_spoon_coverage.py"),
                                          cov, spoon_json,
                                          os.path.join(side_dir, "executed_with_bodies.json")],
                                         timeout=600)
                        r["steps"]["join"] = {"ok": rc2 == 0,
                                              "summary": o2.strip().splitlines()[-1:]}
                    r["status"] = "ok"
                else:
                    r["status"] = "report_failed"
            else:
                r["status"] = "no_coverage"
        else:
            r["status"] = "build_failed"

        json.dump(r, open(os.path.join(side_dir, "status.json"), "w",
                          encoding="utf-8"), indent=1)
        results.append({"pair_id": t["pair_id"], "side": t["side"], "status": r["status"]})
        print(f"  {key} [{i+1}/{len(tests)}] {t['pair_id']} {t['side']}: {r['status']}")

    st["status"] = "ok" if st["steps"]["build"]["ok"] else "build_failed"
    st["results"] = results
    return finish(st, bp_dir, src, tests, out_root, args, t0)


def finish(st, bp_dir, src, tests, out_root, args, t0):
    # a build point that never built still owes every test on it a status file,
    # otherwise the pair looks un-run rather than failed
    if st.get("status") in ("checkout_failed",):
        for t in tests:
            side_dir = os.path.join(out_root, t["pair_dir"], t["side"])
            os.makedirs(side_dir, exist_ok=True)
            json.dump({"pair_id": t["pair_id"], "side": t["side"],
                       "build_point": st["build_point"], "status": st["status"],
                       "steps": st["steps"]},
                      open(os.path.join(side_dir, "status.json"), "w",
                           encoding="utf-8"), indent=1)
    if not args.keep and os.path.isdir(src):
        st["source_removed"] = rp.rmtree_hard(src)
    st["seconds"] = round(time.time() - t0, 1)
    st["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    json.dump(st, open(os.path.join(bp_dir, "status.json"), "w",
                       encoding="utf-8"), indent=1)
    print(f"{st['build_point']}: {st['status']} "
          f"({st['tests']} tests) in {st['seconds']}s")
    return 0 if st["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
