#!/usr/bin/env python3
"""Drive run_pair.py over a selection of pairs.csv.

    python run_all_pairs.py --out runs --tools tools [filters] [--jobs N]

Always start with --dry-run. A full sweep is 2,654 pairs x 2 sides x (checkout +
build + single test), which is days of wall clock and tens of GB of ~/.m2 churn;
the filters exist so you can take one category, one project, or one hundred pairs
at a time and look at the result before committing to more.

Filters (all optional, all AND-ed):
    --category    FlakeBench label, repeatable: "unordered collections", ...
    --source      idoft | reproflake | flakesync | odrepair
    --repair-by   developer | tool
    --project     substring match on project_slug, repeatable
    --with-env    only pairs that carry a ReproFlake build environment
    --java        only pairs whose declared JDK matches (8 | 11 | 17)
    --reachable   only pairs whose before_sha was verified fetchable
    --touch       PR file footprint: prod_only | test_only | both (needs resolve_prs.py)
    --minimal     only pairs whose merge parent is a trustworthy "before" commit
    --merged      only pairs whose PR is confirmed merged
    --ids         file with one pair_id per line
    --limit N     take the first N after filtering
    --shuffle     shuffle before --limit, so a sample is not one project

Resumable: a pair with meta.json is skipped unless --force. Safe to interrupt and
rerun. Writes <out>/_manifest.csv after every completion, so progress survives a
kill.
"""
import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_PAIR = os.path.join(HERE, "run_pair.py")

MANIFEST_COLS = ["pair_id", "project_slug", "test_class", "test_method",
                 "flakebench_label", "source", "overall",
                 "before_status", "after_status",
                 "before_methods", "after_methods", "delta_methods",
                 "before_anonymous", "after_anonymous",
                 "seconds", "pair_dir"]


def select(rows, a):
    out = []
    ids = None
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
        # The next three need pr_meta.csv; without it the columns are empty and
        # these filters would silently select nothing, so say so instead.
        if a.touch and r.get("pr_touch", "") not in a.touch:
            continue
        if a.minimal and r.get("minimal_pair", "") != "yes":
            continue
        if a.merged and r.get("pr_merged", "") != "true":
            continue
        # a pair with no git ref on the after side cannot be run at all
        if r["after_type"] == "tool_patch":
            continue
        out.append(r)
    if a.shuffle:
        random.seed(a.seed)
        random.shuffle(out)
    if a.limit:
        out = out[:a.limit]
    return out


def pair_dir_for(out_dir, row):
    # must stay identical to run_pair.pair_dirname
    sys.path.insert(0, HERE)
    from run_pair import pair_dirname
    return os.path.join(out_dir, pair_dirname(row))


def one(row, a):
    started = time.time()
    cmd = [sys.executable, RUN_PAIR, "--pair-id", row["pair_id"],
           "--out", a.out, "--tools", a.tools, "--pairs", a.pairs,
           "--timeout-build", str(a.timeout_build),
           "--timeout-test", str(a.timeout_test),
           "--before", a.before]
    if a.maven_repo:
        cmd += ["--maven-repo", a.maven_repo]
    if a.force:
        cmd.append("--force")
    if a.keep:
        cmd.append("--keep")
    # Keep the worker's output. Sending it to DEVNULL hides a crash in run_pair.py
    # as a bare "no_meta" in the manifest, with nothing to diagnose from.
    logdir = os.path.join(a.out, "_driver_logs")
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, row["pair_id"] + ".log"), "w", encoding="utf-8") as lf:
        subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=a.timeout_pair)
    return row, round(time.time() - started, 1)


def read_result(row, out_dir, seconds):
    pd = pair_dir_for(out_dir, row)
    rec = {c: "" for c in MANIFEST_COLS}
    rec.update({"pair_id": row["pair_id"], "project_slug": row["project_slug"],
                "test_class": row["test_class"], "test_method": row["test_method"],
                "flakebench_label": row["flakebench_label"], "source": row["source"],
                "seconds": seconds, "pair_dir": pd, "overall": "no_meta"})
    try:
        meta = json.load(open(os.path.join(pd, "meta.json"), encoding="utf-8"))
        rec["overall"] = meta.get("overall", "")
        for s in ("before", "after"):
            rec[f"{s}_status"] = meta.get("sides", {}).get(s, {}).get("status", "")
        summ = json.load(open(os.path.join(pd, "summary.json"), encoding="utf-8"))
        for s in ("before", "after"):
            rec[f"{s}_methods"] = (summ.get(s) or {}).get("executed_methods", "")
            rec[f"{s}_anonymous"] = (summ.get(s) or {}).get("anonymous", "")
        rec["delta_methods"] = (summ.get("delta") or {}).get("executed_methods", "")
    except Exception:
        pass
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=os.path.join(HERE, "..", "pairs.csv"))
    ap.add_argument("--out", default="runs")
    ap.add_argument("--tools", default=os.path.join(HERE, "tools"))
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--category", action="append")
    ap.add_argument("--source", action="append")
    ap.add_argument("--repair-by", action="append")
    ap.add_argument("--project", action="append")
    ap.add_argument("--java", action="append")
    ap.add_argument("--with-env", action="store_true")
    ap.add_argument("--reachable", action="store_true")
    ap.add_argument("--touch", action="append")
    ap.add_argument("--minimal", action="store_true")
    ap.add_argument("--merged", action="store_true")
    ap.add_argument("--before", choices=["auto", "idoft", "merge-parent"], default="auto")
    ap.add_argument("--ids")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--shuffle", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--maven-repo", default="")
    ap.add_argument("--timeout-build", type=int, default=1800)
    ap.add_argument("--timeout-test", type=int, default=900)
    ap.add_argument("--timeout-pair", type=int, default=7200)
    a = ap.parse_args()
    a.out = os.path.abspath(a.out)

    rows = list(csv.DictReader(open(a.pairs, encoding="utf-8")))
    if (a.touch or a.minimal or a.merged) and not any(r.get("merge_commit_sha") for r in rows):
        sys.exit("--touch/--minimal/--merged need the pr_* columns; run resolve_prs.py "
                 "then rebuild pairs.csv with build_pairs.py")
    sel = select(rows, a)

    todo = [r for r in sel
            if a.force or not os.path.isfile(os.path.join(pair_dir_for(a.out, r), "meta.json"))]
    print(f"selected {len(sel)} of {len(rows)} pairs; {len(todo)} to run "
          f"({len(sel) - len(todo)} already done)")
    if a.dry_run:
        from collections import Counter
        print("  by label:  ", dict(Counter(r["flakebench_label"] or "(none)" for r in sel)))
        print("  by source: ", dict(Counter(r["source"] for r in sel)))
        print("  by touch:  ", dict(Counter(r.get("pr_touch") or "(unknown)" for r in sel)))
        print("  minimal:   ", dict(Counter(r.get("minimal_pair") or "(unknown)" for r in sel)))
        print("  projects:  ", len({r["project_slug"] for r in sel}))
        for r in todo[:25]:
            print("   ", r["pair_id"], r["project_slug"], r["module_path"],
                  r["test_class"].rsplit(".", 1)[-1] + "#" + r["test_method"])
        if len(todo) > 25:
            print(f"    ... and {len(todo) - 25} more")
        return 0

    os.makedirs(a.out, exist_ok=True)
    manifest, done, t0 = [], 0, time.time()
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(one, r, a): r for r in todo}
        for f in as_completed(futs):
            row = futs[f]
            try:
                _, secs = f.result()
            except Exception as ex_:
                secs = -1
                print(f"  {row['pair_id']}: driver error {ex_}")
            rec = read_result(row, a.out, secs)
            manifest.append(rec)
            done += 1
            rate = (time.time() - t0) / done
            print(f"[{done}/{len(todo)}] {rec['pair_id']:6s} {rec['overall']:8s} "
                  f"before={rec['before_status'] or '-':14s} after={rec['after_status'] or '-':14s} "
                  f"{secs}s  eta={(len(todo) - done) * rate / 60:.0f}m")
            with open(os.path.join(a.out, "_manifest.csv"), "w", newline="",
                      encoding="utf-8") as mf:
                w = csv.DictWriter(mf, fieldnames=MANIFEST_COLS)
                w.writeheader()
                w.writerows(manifest)

    from collections import Counter
    print()
    print("overall:", dict(Counter(m["overall"] for m in manifest)))
    print("before: ", dict(Counter(m["before_status"] for m in manifest)))
    print("after:  ", dict(Counter(m["after_status"] for m in manifest)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
