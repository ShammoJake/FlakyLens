"""Locate tests whose benchmark row carries no usable class name.

Some FlakeBench rows name the test as "<commit sha>.<method>" or as a bare
method name, so the class cannot be derived. This resolves those by searching a
checked-out working tree for a @Test-annotated declaration of that method, and
records whether the match was unique.

Requires a working tree, not a blobless partial clone: see README.
"""
import os, re, sys, json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.abspath(os.path.join(HERE, ".."))
ROOT = os.path.abspath(os.path.join(BASE, "..", ".."))
SRC  = os.path.join(BASE, "sources")
MIRR = os.environ.get("FLAKY_MIRRORS",
                      os.path.join(os.environ.get("TEMP", "/tmp"), "flaky_mirrors"))

SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


def index_tree(tree):
    """method name -> [(path, source)] for every @Test method in the tree."""
    idx = {}
    for dirpath, dirnames, filenames in os.walk(tree):
        if ".git" in dirpath:
            continue
        for fn in filenames:
            if not fn.endswith(".java"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                src = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if "@Test" not in src:
                continue
            for m in re.finditer(
                    r"@Test[^\n]*\n(?:\s*@[\w.]+[^\n]*\n)*\s*public\s+[\w<>\[\],\s.]*?\s(\w+)\s*\(",
                    src):
                idx.setdefault(m.group(1), []).append((p, src))
    return idx


def main(project, repo_dir):
    tree = os.path.join(MIRR, repo_dir)
    if not os.path.isdir(tree):
        sys.exit("no working tree at %s" % tree)
    print("indexing", tree, flush=True)
    idx = index_tree(tree)
    print("indexed %d distinct @Test method names" % len(idx), flush=True)

    ipath = os.path.join(SRC, "index.csv")
    index = pd.read_csv(ipath)
    todo = index[(index.project == project) & (index.path.isna())]
    pdir = os.path.join(SRC, project)
    os.makedirs(pdir, exist_ok=True)

    resolved = ambiguous = missing = 0
    for i, r in todo.iterrows():
        meth = r.test.split(".")[-1]
        hits = idx.get(meth, [])
        # drop duplicate files
        seen, uniq = set(), []
        for p, s in hits:
            if p not in seen:
                seen.add(p); uniq.append((p, s))
        if not uniq:
            missing += 1; continue
        if len(uniq) > 1:
            ambiguous += 1
            index.loc[i, "note"] = "ambiguous:%d" % len(uniq)
            continue
        p, s = uniq[0]
        cls = os.path.basename(p)[:-5]
        fn = "%s__%s.java" % (cls, meth)
        with open(os.path.join(pdir, fn), "w", encoding="utf-8",
                  errors="replace") as fh:
            fh.write(s)
        rel = os.path.relpath(p, tree).replace("\\", "/")
        index.loc[i, ["path", "file", "note"]] = [rel, fn, "by-method-search"]
        resolved += 1

    index.to_csv(ipath, index=False)
    print("%s: resolved %d, ambiguous %d, not found %d"
          % (project, resolved, ambiguous, missing))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
