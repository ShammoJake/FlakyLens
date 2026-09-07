#!/usr/bin/env python3
"""Resolve every PR link in pairs.csv to the commit that actually landed.

    python resolve_prs.py [--pairs ../pairs.csv] [--out data/pr_meta.csv]
                          [--jobs 4] [--limit N] [--no-files] [--force]

Requires an authenticated `gh` (5,000 requests/hour; the anonymous limit of 60
makes this impossible without it).

WHY THIS EXISTS
---------------
`pairs.csv` names the after side of an IDoFT pair as a PR *link*. Turning that
into a commit without the API means guessing at refs, and the guess is wrong:

  * `refs/pull/<n>/merge` does not exist for a merged PR — GitHub drops the
    test-merge ref once the PR closes. All four smoke-test pairs fell through to
    the fallback.
  * `refs/pull/<n>/head` is the author's branch tip. It is not what landed when
    the maintainer squashed or rebased, and it is missing anything that reached
    the base branch between branch point and merge.

The API gives `merge_commit_sha` — the commit on the base branch — and its first
parent, which is the tree immediately before the repair. That parent is the
correct "before" for a paired design: IDoFT's `SHA Detected` can predate the fix
by years, so a pair built on it differs by the repair *plus* everything else that
landed meanwhile.

Checked against jsondoc PR 261: merge commit `3b3907f4`, first parent `16d42fd3`.
ReproFlake independently packages that same pair — its zip is named
`jsondoc=jsondoc-core=16d42fd`. Two sources agreeing on a construction neither of
our ref guesses produced.

OUTPUT
------
`pr_meta.csv`, one row per distinct PR URL. `build_pairs.py` joins it onto
pairs.csv when it exists, so this step is optional and the corpus can still be
rebuilt without `gh`.

Resumable: PRs already in the output file are skipped unless --force.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
PR_URL = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")
# A handful of IDoFT "PR Link" values point at a commit, not a pull request —
# fastjson, bookkeeper and byte-buddy each do. Those are better evidence than a
# PR, not worse: the fix commit is named outright.
COMMIT_URL = re.compile(r"github\.com/([^/]+)/([^/]+)/commit/([0-9a-f]{7,40})")

COLS = ["pr_url", "owner", "repo", "number", "state", "merged", "merged_at",
        "base_sha", "head_sha", "merge_commit_sha", "merge_parent_count",
        "merge_parent_sha", "merge_kind", "minimal_pair", "pr_commits",
        "changed_files", "additions", "deletions",
        "files_java_main", "files_java_test", "files_other", "touch",
        "files_listed", "error"]


def gh(path, jq=None, paginate=False):
    cmd = ["gh", "api", path]
    if paginate:
        cmd.append("--paginate")
    if jq:
        cmd += ["--jq", jq]
    # encoding must be forced: text=True decodes with the locale codec, which on
    # Windows is cp1252 and dies on any PR body containing non-Latin-1 text — it
    # surfaced as a bogus "the JSON object must be str" on 7 of the first 12 PRs.
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[:200])
    return p.stdout


def classify_files(files):
    """Split changed paths into production Java, test Java, and everything else.

    This is the measurement behind experiment E5: for a repair that touches only
    production code, no representation of the test body can distinguish the flaky
    version from the fixed one, so a body-only model is at chance by construction.
    A 90-PR hand sample put that at roughly one in six; this makes it exact."""
    main = test = other = 0
    for f in files:
        p = f.lower().replace("\\", "/")
        if not p.endswith(".java"):
            other += 1
        elif "/src/test/" in p or "/test/java/" in p:
            test += 1
        else:
            main += 1
    if main and test:
        return main, test, other, "both"
    if main:
        return main, test, other, "prod_only"
    if test:
        return main, test, other, "test_only"
    return main, test, other, "none"


def resolve(url, want_files=True):
    rec = {c: "" for c in COLS}
    rec["pr_url"] = url

    cm = COMMIT_URL.search(url)
    if cm and not PR_URL.search(url):
        owner, repo, sha = cm.group(1), cm.group(2), cm.group(3)
        rec.update(owner=owner, repo=repo, state="commit", merged="true",
                   merge_commit_sha=sha, merge_kind="direct_commit")
        try:
            c = json.loads(gh(f"repos/{owner}/{repo}/commits/{sha}"))
            rec["merge_commit_sha"] = c["sha"]
            parents = [p["sha"] for p in c.get("parents", [])]
            rec["merge_parent_count"] = len(parents)
            rec["merge_parent_sha"] = parents[0] if parents else ""
            # A direct fix commit is the tightest pair there is: its parent is the
            # tree immediately before the repair, by construction.
            rec["minimal_pair"] = "yes" if len(parents) == 1 else "no"
            rec["pr_commits"] = 1
            rec["merged_at"] = (c.get("commit", {}).get("committer", {}) or {}).get("date", "")
            files = [f["filename"] for f in c.get("files", [])]
            if files:
                mn, tn, on, touch = classify_files(files)
                rec.update(files_java_main=mn, files_java_test=tn, files_other=on,
                           touch=touch, files_listed="yes", changed_files=len(files))
        except Exception as e:
            rec["error"] = f"commit-url: {e}"
        return rec

    m = PR_URL.search(url)
    if not m:
        rec["error"] = "not a github PR or commit url"
        return rec
    owner, repo, num = m.group(1), m.group(2), m.group(3)
    rec.update(owner=owner, repo=repo, number=num)

    try:
        pr = json.loads(gh(f"repos/{owner}/{repo}/pulls/{num}"))
    except Exception as e:
        rec["error"] = f"pulls: {e}"
        return rec

    rec.update(state=pr.get("state", ""), merged=str(bool(pr.get("merged"))).lower(),
               merged_at=pr.get("merged_at") or "",
               base_sha=(pr.get("base") or {}).get("sha", ""),
               head_sha=(pr.get("head") or {}).get("sha", ""),
               merge_commit_sha=pr.get("merge_commit_sha") or "",
               changed_files=pr.get("changed_files", ""),
               pr_commits=pr.get("commits", ""),
               additions=pr.get("additions", ""), deletions=pr.get("deletions", ""))

    # Parents of the merge commit. Two parents means a real merge, so the first
    # parent is the base branch immediately before the repair. One parent means
    # squash or rebase: the commit still holds the repair, but its parent is not
    # guaranteed to be the base, so `merge_kind` records the distinction rather
    # than letting a later analysis assume it.
    if rec["merge_commit_sha"] and pr.get("merged"):
        try:
            c = json.loads(gh(f"repos/{owner}/{repo}/commits/{rec['merge_commit_sha']}"))
            parents = [p["sha"] for p in c.get("parents", [])]
            rec["merge_parent_count"] = len(parents)
            rec["merge_parent_sha"] = parents[0] if parents else ""
            rec["merge_kind"] = "merge" if len(parents) > 1 else "squash_or_rebase"
            # Is the first parent really "the tree just before this repair"?
            #   two parents  -> a true merge commit; the first parent is the base. Yes.
            #   one parent   -> squash or rebase, and they differ. A squash puts one
            #                   commit on the base, so the parent is the base. A rebase
            #                   replays every commit, so for a multi-commit PR the last
            #                   one's parent is the second-to-last commit, not the base.
            #                   Only safe when the PR had a single commit.
            rec["minimal_pair"] = "yes" if (
                len(parents) > 1 or str(pr.get("commits", "")) == "1") else "no"
        except Exception as e:
            rec["error"] = f"commit: {e}"
    elif not pr.get("merged"):
        rec["merge_kind"] = "unmerged"
        rec["minimal_pair"] = "no"

    if want_files:
        # The files endpoint pages at 30 and caps at 3000. A handful of IDoFT PRs
        # are bulk NonDex sweeps touching hundreds of files; paginating those buys
        # nothing the counts do not already give.
        try:
            n = int(rec["changed_files"] or 0)
        except ValueError:
            n = 0
        if 0 < n <= 100:
            try:
                out = gh(f"repos/{owner}/{repo}/pulls/{num}/files",
                         jq=".[].filename", paginate=True)
                files = [ln for ln in out.splitlines() if ln.strip()]
                mn, tn, on, touch = classify_files(files)
                rec.update(files_java_main=mn, files_java_test=tn, files_other=on,
                           touch=touch, files_listed="yes")
            except Exception as e:
                rec["files_listed"] = "no"
                rec["error"] = (rec["error"] + "; " if rec["error"] else "") + f"files: {e}"
        else:
            rec["files_listed"] = "skipped" if n else "no"
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=os.path.join(HERE, "..", "pairs.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "data", "pr_meta.csv"))
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-files", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    try:
        rl = json.loads(gh("rate_limit"))["resources"]["core"]
    except Exception as e:
        sys.exit(f"gh is not usable: {e}\nrun: gh auth login")
    print(f"gh rate limit: {rl['remaining']}/{rl['limit']} remaining")

    rows = list(csv.DictReader(open(a.pairs, encoding="utf-8")))
    urls = []
    seen = set()
    for r in rows:
        if r.get("after_type") == "pr" and r["after_ref"] not in seen:
            seen.add(r["after_ref"])
            urls.append(r["after_ref"])

    done = {}
    if os.path.isfile(a.out) and not a.force:
        for r in csv.DictReader(open(a.out, encoding="utf-8")):
            done[r["pr_url"]] = r
    todo = [u for u in urls if u not in done]
    if a.limit:
        todo = todo[:a.limit]

    calls = len(todo) * (2 if a.no_files else 3)
    print(f"{len(urls)} distinct PRs; {len(done)} cached; {len(todo)} to fetch "
          f"(~{calls} API calls)")
    if calls > rl["remaining"]:
        print(f"warning: only {rl['remaining']} requests left this hour; "
              f"the run will stop when it hits the limit and can be resumed")

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    results = dict(done)
    t0, n = time.time(), 0
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(resolve, u, not a.no_files): u for u in todo}
        for f in as_completed(futs):
            u = futs[f]
            try:
                results[u] = f.result()
            except Exception as e:
                results[u] = {c: "" for c in COLS} | {"pr_url": u, "error": str(e)[:200]}
            n += 1
            if n % 25 == 0 or n == len(todo):
                el = time.time() - t0
                print(f"  [{n}/{len(todo)}] {el:.0f}s elapsed, "
                      f"eta {(len(todo) - n) * el / max(n, 1) / 60:.0f}m")
                with open(a.out, "w", newline="", encoding="utf-8") as fh:
                    w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
                    w.writeheader()
                    w.writerows(results[k] for k in sorted(results))

    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(results[k] for k in sorted(results))

    from collections import Counter
    vals = list(results.values())
    print()
    print("wrote", a.out, "-", len(vals), "PRs")
    print("  merged:     ", dict(Counter(v.get("merged") for v in vals)))
    print("  merge_kind: ", dict(Counter(v.get("merge_kind") for v in vals)))
    print("  touch:      ", dict(Counter(v.get("touch") for v in vals)))
    errs = [v for v in vals if v.get("error")]
    print("  errors:     ", len(errs))
    for v in errs[:5]:
        print("     ", v["pr_url"], "-", v["error"][:110])
    return 0


if __name__ == "__main__":
    sys.exit(main())
