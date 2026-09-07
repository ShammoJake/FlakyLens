"""Fetch the test class for every flaky test in the selected projects.

Blobless partial clone per repository, one shallow fetch per pinned commit, then
locate each test class by filename and confirm the method is present in it.
Writes one Java file per (project, test) plus an index CSV.

Usage:  python fetch_sources.py [project ...]
"""
import os, re, sys, subprocess, json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))     # repo root
OUT  = os.path.join(HERE, "..", "sources")
MIRR = os.environ.get("FLAKY_MIRRORS",
                      os.path.join(os.environ.get("TEMP", "/tmp"), "flaky_mirrors"))

PROJECTS = ["wildfly_wildfly", "apache_hadoop", "apache_pulsar",
            "cdapio_cdap", "neo4j_neo4j", "androidx_androidx"]


def git(args, cwd, timeout=900):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True, errors="replace", timeout=timeout)


def mirror(repo):
    """Blobless partial clone directory for owner/name, created on demand."""
    d = os.path.join(MIRR, repo.replace("/", "__"))
    if not os.path.isdir(os.path.join(d, ".git")):
        os.makedirs(d, exist_ok=True)
        git(["init", "-q"], d)
        git(["remote", "add", "origin", "https://github.com/%s" % repo], d)
    return d


def fetch(d, sha):
    """Shallow blobless fetch of one commit. Returns a ref name or None."""
    tag = "c_" + sha[:8]
    if git(["rev-parse", "--verify", "-q", tag], d).returncode == 0:
        return tag
    r = git(["fetch", "--depth", "1", "--filter=blob:none", "-q", "origin", sha], d)
    if r.returncode != 0:
        return None
    git(["tag", "-f", tag, "FETCH_HEAD"], d)
    return tag


def main(selected):
    bench = pd.read_csv(os.path.join(ROOT, "FlakeBench", "FlakeBench_dataset.csv"))
    preds = pd.read_csv(os.path.join(ROOT, "docs", "investigation",
                                     "all_flaky_with_preds.csv"))
    shas = pd.read_csv(os.path.join(ROOT, "FlakeBench",
                                    "filtered_tests_with_owner_sha.csv"),
                       header=None, names=["repo", "shas"])
    shas["key"] = shas.repo.str.replace("/", "_", regex=False)
    repo_of = dict(zip(shas.key, shas.repo))
    sha_of = {k: sorted({s.strip().split()[-1] for s in v.split(";") if s.strip()})
              for k, v in zip(shas.key, shas.shas)}

    rows = []
    for proj in selected:
        repo = repo_of.get(proj)
        if not repo:
            print("!! no repo for", proj); continue
        tests = preds[preds.project == proj]
        print("== %s (%s): %d flaky tests, %d commits"
              % (proj, repo, len(tests), len(sha_of[proj])), flush=True)

        d = mirror(repo)
        refs = []
        for sha in sha_of[proj]:
            t = fetch(d, sha)
            if t:
                refs.append((t, sha))
            else:
                print("   fetch failed:", sha[:8], flush=True)
        if not refs:
            print("   no usable commits", flush=True); continue

        trees = {}
        for t, sha in refs:
            trees[t] = git(["ls-tree", "-r", "--name-only", t], d).stdout.splitlines()

        pdir = os.path.join(OUT, proj)
        os.makedirs(pdir, exist_ok=True)
        found = 0
        for _, r in tests.iterrows():
            tn = r.test_name
            cls = tn.split(".")[0] if "." in tn else None
            meth = tn.split(".")[-1]
            hit = None
            if cls:
                for t, sha in refs:
                    for p in trees[t]:
                        if p.endswith("/" + cls + ".java"):
                            src = git(["cat-file", "blob", "%s:%s" % (t, p)], d).stdout
                            if re.search(r"\b" + re.escape(meth) + r"\s*\(", src):
                                hit = (sha, p, src); break
                    if hit: break
            if hit:
                sha, p, src = hit
                fn = "%s__%s.java" % (cls, meth)
                with open(os.path.join(pdir, fn), "w", encoding="utf-8",
                          errors="replace") as fh:
                    fh.write(src)
                rows.append(dict(project=proj, test=tn, truth=r.truth, pred=r.pred,
                                 wrong=bool(r.wrong), sha=sha[:8], path=p, file=fn))
                found += 1
            else:
                rows.append(dict(project=proj, test=tn, truth=r.truth, pred=r.pred,
                                 wrong=bool(r.wrong), sha=None, path=None, file=None))
        print("   located %d/%d" % (found, len(tests)), flush=True)

    idx = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, "index.csv")
    if os.path.exists(out):
        old = pd.read_csv(out)
        idx = pd.concat([old[~old.project.isin(selected)], idx], ignore_index=True)
    idx.to_csv(out, index=False)
    ok = idx[idx.path.notna()]
    print("\nTOTAL located %d / %d  (%d projects)"
          % (len(ok), len(idx), idx.project.nunique()))
    print(idx.groupby("project").apply(
        lambda g: "%d/%d" % (g.path.notna().sum(), len(g))).to_string())


if __name__ == "__main__":
    main(sys.argv[1:] or PROJECTS)
