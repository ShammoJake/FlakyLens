#!/usr/bin/env python3
"""Drive the evidence collection over pairs.csv, grouped by build point.

    python run_groups.py --pairs ../pairs_resolved.csv --out runs --tools runs/tools \\
                         [filters] [--jobs N] [--dry-run]

Same filters as run_all_pairs.py — category, source, repair-by, project, java,
with-env, reachable, touch, minimal, merged, ids, limit, shuffle — plus:

    --max-per-project N   cap the pairs taken from any one project

WHY GROUPED
-----------
The unit of work is a **build point**: one (project, commit). Every pair-side that
lands on the same commit shares its checkout, its build and its Spoon model, and
only the single-test run and the join are done per test.

Measured on the 343-pair JDK-11 slice: 686 sides collapse to 199 build points, a
**3.4x reduction**, and the clustering is worst exactly where the cost was worst —
google/TestParameterInjector is 51 pairs over 2 build points, alibaba/innodb-java-reader
45 over 2, alibaba/fastjson2 50 over 21.

--max-per-project is not only about time. Three projects were 43% of that slice, so
any pooled statistic over it is mostly a statement about those three; capping the
per-project count improves the inference as well as the runtime.

Two sides of one pair are usually different build points, so `meta.json` and
`summary.json` cannot be written by the worker. A finalize pass assembles them
from the two `status.json` files once the groups are done — and it runs even if
the sweep is interrupted, so partial results are still readable.
"""
import argparse
import collections
import csv
import json
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run_pair import pair_dirname, resolve_after_refs, resolve_before_refs  # noqa: E402
from run_group import bp_key                                                # noqa: E402

MANIFEST_COLS = ["pair_id", "project_slug", "test_class", "test_method",
                 "flakebench_label", "source", "pr_touch", "overall",
                 "before_status", "after_status", "before_bp", "after_bp",
                 "before_methods", "after_methods", "delta_methods",
                 "before_anonymous", "after_anonymous", "pair_dir"]


def select(rows, a):
    out, ids = [], None
    if a.ids:
        ids = {ln.strip() for ln in open(a.ids, encoding="utf-8") if ln.strip()}
    for r in rows:
        if ids is not None and r["pair_id"] not in ids:
            continue
        if a.category and r["flakebench_label"] not in a.category:
            continue
        if a.source and r["source"] not in a.source:
            continue
        if a.repair_by and r["repair_author"] not in a.repair_by:
            continue
        if a.project and not any(p.lower() in r["project_slug"] for p in a.project):
            continue
        if a.with_env and r["build_env"] != "reproflake":
            continue
        if a.java and r["java_version"] not in a.java:
            continue
        if a.reachable and r["before_sha_reachable"] != "yes":
            continue
        if a.touch and r.get("pr_touch", "") not in a.touch:
            continue
        if a.minimal and r.get("minimal_pair", "") != "yes":
            continue
        if a.merged and r.get("pr_merged", "") != "true":
            continue
        if r["after_type"] == "tool_patch":
            continue
        if "(" in r["test_method"]:            # -Dtest= cannot express parameters
            continue
        out.append(r)
    if a.shuffle:
        random.seed(a.seed)
        random.shuffle(out)
    if a.max_per_project:
        per = collections.Counter()
        capped = []
        for r in out:
            if per[r["project_slug"]] < a.max_per_project:
                per[r["project_slug"]] += 1
                capped.append(r)
        out = capped
    if a.limit:
        out = out[:a.limit]
    return out


def build_groups(sel, out_dir, before_mode):
    """Expand each pair into two sides and bucket them by (project, commit)."""
    groups, skipped = collections.OrderedDict(), []
    for r in sel:
        pd = pair_dirname(r)
        after_refs, after_kind, after_err = resolve_after_refs(r)
        before_refs, before_kind = resolve_before_refs(r, before_mode)
        for side, refs, kind in (("before", before_refs, before_kind),
                                 ("after", after_refs, after_kind)):
            if not refs:
                skipped.append((r["pair_id"], side, after_err or "no ref"))
                continue
            k = (r["project_url"], refs[0])
            g = groups.setdefault(k, {"project_url": r["project_url"], "ref": refs[0],
                                      "ref_kind": kind, "tests": []})
            g["tests"].append({"pair_id": r["pair_id"], "pair_dir": pd, "side": side,
                               "module": r["module_path"] or ".",
                               "test_class": r["test_class"],
                               "test_method": r["test_method"],
                               "category": r["source_category"]})
    return groups, skipped


def run_one(g, a):
    key = bp_key(g["project_url"], g["ref"])
    spec_dir = os.path.join(a.out, "_specs")
    os.makedirs(spec_dir, exist_ok=True)
    spec_path = os.path.join(spec_dir, key + ".json")
    json.dump(dict(g, out=a.out), open(spec_path, "w", encoding="utf-8"), indent=1)

    logdir = os.path.join(a.out, "_driver_logs")
    os.makedirs(logdir, exist_ok=True)
    cmd = [sys.executable, "-u", os.path.join(HERE, "run_group.py"),
           "--spec", spec_path, "--tools", a.tools, "--isolate", a.isolate,
           "--timeout-build", str(a.timeout_build), "--timeout-test", str(a.timeout_test)]
    if a.force:
        cmd.append("--force")
    if a.keep:
        cmd.append("--keep")
    if a.maven_repo:
        cmd += ["--maven-repo", a.maven_repo]
    t0 = time.time()
    with open(os.path.join(logdir, key + ".log"), "w", encoding="utf-8") as lf:
        subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=a.timeout_group)
    return key, len(g["tests"]), round(time.time() - t0, 1)


def counts(side_dir):
    p = os.path.join(side_dir, "executed_with_bodies.json")
    if not os.path.isfile(p):
        return {}
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}
    return {"executed_methods": len(d),
            "anonymous": sum(1 for m in d if m["is_anonymous"]),
            "matched": sum(1 for m in d if m["match_level"] not in ("unmatched", "synthetic")),
            "with_body": sum(1 for m in d if m["body"])}


def finalize(sel, a):
    """Assemble per-pair meta.json / summary.json / _manifest.csv from the sides."""
    manifest = []
    for r in sel:
        pd = pair_dirname(r)
        pair_dir = os.path.join(a.out, pd)
        sides, statuses = {}, {}
        for side in ("before", "after"):
            f = os.path.join(pair_dir, side, "status.json")
            if os.path.isfile(f):
                try:
                    sides[side] = json.load(open(f, encoding="utf-8"))
                except Exception:
                    sides[side] = {"status": "unreadable"}
            statuses[side] = sides.get(side, {}).get("status", "")
        if not sides:
            continue
        summary = {s: counts(os.path.join(pair_dir, s)) for s in ("before", "after")}
        b, af = summary.get("before") or {}, summary.get("after") or {}
        if b and af:
            summary["delta"] = {k: af.get(k, 0) - b.get(k, 0) for k in b}
        os.makedirs(pair_dir, exist_ok=True)
        json.dump(summary, open(os.path.join(pair_dir, "summary.json"), "w",
                                encoding="utf-8"), indent=1)
        overall = "ok" if all(statuses[s] == "ok" for s in ("before", "after")) else "partial"
        json.dump({"pair": r, "sides": sides, "overall": overall,
                   "finalized": time.strftime("%Y-%m-%dT%H:%M:%S")},
                  open(os.path.join(pair_dir, "meta.json"), "w", encoding="utf-8"), indent=1)
        manifest.append({
            "pair_id": r["pair_id"], "project_slug": r["project_slug"],
            "test_class": r["test_class"], "test_method": r["test_method"],
            "flakebench_label": r["flakebench_label"], "source": r["source"],
            "pr_touch": r.get("pr_touch", ""), "overall": overall,
            "before_status": statuses["before"], "after_status": statuses["after"],
            "before_bp": sides.get("before", {}).get("build_point", ""),
            "after_bp": sides.get("after", {}).get("build_point", ""),
            "before_methods": b.get("executed_methods", ""),
            "after_methods": af.get("executed_methods", ""),
            "delta_methods": (summary.get("delta") or {}).get("executed_methods", ""),
            "before_anonymous": b.get("anonymous", ""),
            "after_anonymous": af.get("anonymous", ""),
            "pair_dir": pair_dir})
    with open(os.path.join(a.out, "_manifest.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLS)
        w.writeheader()
        w.writerows(manifest)
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=os.path.join(HERE, "..", "pairs_resolved.csv"))
    ap.add_argument("--out", default="runs")
    ap.add_argument("--tools", default=os.path.join(HERE, "tools"))
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--category", action="append")
    ap.add_argument("--source", action="append")
    ap.add_argument("--repair-by", action="append")
    ap.add_argument("--project", action="append")
    ap.add_argument("--java", action="append")
    ap.add_argument("--touch", action="append")
    ap.add_argument("--with-env", action="store_true")
    ap.add_argument("--reachable", action="store_true")
    ap.add_argument("--minimal", action="store_true")
    ap.add_argument("--merged", action="store_true")
    ap.add_argument("--ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--max-per-project", type=int)
    ap.add_argument("--shuffle", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--before", choices=["auto", "idoft", "merge-parent"], default="auto")
    ap.add_argument("--isolate", choices=["auto", "always", "never"], default="auto")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--finalize-only", action="store_true")
    ap.add_argument("--maven-repo", default="")
    ap.add_argument("--timeout-build", type=int, default=2700)
    ap.add_argument("--timeout-test", type=int, default=900)
    ap.add_argument("--timeout-group", type=int, default=14400)
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)

    rows = list(csv.DictReader(open(a.pairs, encoding="utf-8")))
    sel = select(rows, a)
    groups, skipped = build_groups(sel, a.out, a.before)

    todo = []
    for k, g in groups.items():
        marker = os.path.join(a.out, "_bp", bp_key(g["project_url"], g["ref"]), "status.json")
        if a.force or not os.path.isfile(marker):
            todo.append(g)

    print(f"selected {len(sel)} pairs -> {len(sel)*2} sides -> {len(groups)} build points"
          f"  ({len(sel)*2/max(len(groups),1):.1f}x fewer builds)")
    print(f"  {len(todo)} build points to run, {len(groups)-len(todo)} already done"
          f"{', ' + str(len(skipped)) + ' sides unresolvable' if skipped else ''}")

    if a.dry_run:
        print("  by label: ", dict(collections.Counter(r["flakebench_label"] or "(none)"
                                                       for r in sel)))
        print("  by touch: ", dict(collections.Counter(r.get("pr_touch") or "(unknown)"
                                                       for r in sel)))
        top = collections.Counter(r["project_slug"] for r in sel).most_common(8)
        bps = collections.Counter(g["project_url"].rsplit("/", 1)[-1].lower()
                                  for g in groups.values())
        print("  top projects (pairs -> build points):")
        for p, n in top:
            print(f"    {n:4d} -> {bps.get(p.rsplit('/',1)[-1], 0):3d}   {p}")
        return 0

    if a.finalize_only:
        m = finalize(sel, a)
        print(f"finalized {len(m)} pairs")
        return 0

    os.makedirs(a.out, exist_ok=True)
    done, t0 = 0, time.time()
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(run_one, g, a): g for g in todo}
        for f in as_completed(futs):
            g = futs[f]
            try:
                key, ntests, secs = f.result()
            except Exception as e:
                key, ntests, secs = bp_key(g["project_url"], g["ref"]), len(g["tests"]), -1
                print(f"  {key}: driver error {e}")
            done += 1
            rate = (time.time() - t0) / done
            print(f"[{done}/{len(todo)}] {key:40s} {ntests:3d} tests  {secs}s  "
                  f"eta={(len(todo)-done)*rate/60:.0f}m")
            finalize(sel, a)

    m = finalize(sel, a)
    print()
    print("pairs:", dict(collections.Counter(x["overall"] for x in m)))
    print("before:", dict(collections.Counter(x["before_status"] for x in m)))
    print("after: ", dict(collections.Counter(x["after_status"] for x in m)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
