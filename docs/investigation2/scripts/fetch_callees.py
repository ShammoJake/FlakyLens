"""Extract the production methods a test calls, at depth 1.

For each located test, work out which methods of the project's own main source
tree the body invokes, then save those method bodies as a `callees` slice.

Resolution is type-directed, not name-only. The body's local declarations and
the class fields give a variable-to-type map, so `cache.put(...)` after
`PeerCache cache = new PeerCache(...)` resolves to PeerCache.put rather than to
every `put` in the repository. A call is kept only when its receiver type is a
class declared under src/main/java in the same project, so JUnit, Mockito and
the JDK drop out without needing a deny list.

Needs a real working tree, which a blobless clone provides via sparse checkout.
Run after fetch_sources.py and resolve_bare_names.py.
"""
import os, re, sys, json, subprocess, collections
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from slice_and_count import strip_noise, parse_methods, slices_for  # noqa: E402

BASE = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(BASE, "sources")
OUT = os.path.join(SRC, "_callees")
MIRR = os.environ.get("FLAKY_MIRRORS",
                      os.path.join(os.environ.get("TEMP", "/tmp"), "flaky_mirrors"))

REPO_DIR = {"apache_hadoop": "apache__hadoop", "apache_pulsar": "apache__pulsar",
            "cdapio_cdap": "cdapio__cdap", "neo4j_neo4j": "neo4j__neo4j",
            "wildfly_wildfly": "wildfly__wildfly"}
# wildfly rows carry no sha; they were resolved against this commit
FALLBACK_SHA = {"wildfly_wildfly": "b19048b7"}

SPARSE = ["/*/src/main/java/**", "/*/*/src/main/java/**",
          "/*/*/*/src/main/java/**", "/*/*/*/*/src/main/java/**",
          "/src/main/java/**"]

TYPE_DECL = re.compile(r"\b([A-Z]\w*)(?:<[^<>()]*>)?(?:\[\])?\s+(\w+)\s*[=;)]")
INVOKE = re.compile(r"\b(\w+)\s*\.\s*(\w+)\s*\(")
NEWOBJ = re.compile(r"\bnew\s+([A-Z]\w*)\s*\(")
CLASS_DECL = re.compile(r"\b(?:class|interface|enum)\s+(\w+)")


def git(args, cwd, timeout=900):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True, errors="replace", timeout=timeout)


def checkout_main(repo_dir, sha):
    """Sparse-checkout the main source tree at one commit. Batched, so fast."""
    d = os.path.join(MIRR, repo_dir)
    git(["config", "core.sparseCheckout", "true"], d)
    # Windows MAX_PATH: deep Java package paths in Hadoop and cdap exceed 260
    # characters without this.
    git(["config", "core.longpaths", "true"], d)
    git(["sparse-checkout", "init", "--no-cone"], d)
    with open(os.path.join(d, ".git", "info", "sparse-checkout"), "w") as fh:
        fh.write("\n".join(SPARSE) + "\n")
    tag = "c_" + sha if not sha.startswith("c_") else sha
    r = git(["checkout", "-f", tag], d)
    if r.returncode != 0:
        r = git(["checkout", "-f", sha], d)
    return d if r.returncode == 0 else None


def wanted_calls(body, fields):
    """(Type, method) pairs the body invokes, plus constructed types."""
    var2type = {}
    for scope in (fields, body):
        for t, v in TYPE_DECL.findall(scope):
            var2type.setdefault(v, t)
    pairs, types = set(), set()
    for recv, meth in INVOKE.findall(body):
        if recv in var2type:
            pairs.add((var2type[recv], meth))
        elif recv[:1].isupper():
            pairs.add((recv, meth))          # static call on a class
    for t in NEWOBJ.findall(body):
        types.add(t)
        pairs.add((t, "<init>"))
    return pairs, types


def index_from_objects(repo_dir, sha, wanted_types):
    """Read the needed files straight from git objects, no working tree.

    Fallback for repositories that cannot be checked out on Windows. cdap has a
    path containing a colon, which NTFS rejects, so git refuses the whole
    checkout even when sparse rules exclude that file.
    """
    d = os.path.join(MIRR, repo_dir)
    tag = "c_" + sha if not sha.startswith("c_") else sha
    listing = git(["ls-tree", "-r", "--name-only", tag], d).stdout.splitlines()
    idx = collections.defaultdict(dict)
    for path in listing:
        if not path.endswith(".java") or "/src/main/java/" not in path:
            continue
        cls = path.rsplit("/", 1)[-1][:-5]
        if cls not in wanted_types or cls in idx:
            continue
        blob = git(["cat-file", "blob", "%s:%s" % (tag, path)], d).stdout
        if not blob:
            continue
        for kind, name, text, _, _ in parse_methods(strip_noise(blob))[0]:
            if name not in idx[cls]:
                idx[cls][name] = text
    return idx


def index_tree(tree, wanted_types):
    """SimpleClassName -> {method name: source} for the classes we need."""
    idx = collections.defaultdict(dict)
    for dirpath, _, filenames in os.walk(tree):
        if ".git" in dirpath or os.sep + "test" + os.sep in dirpath:
            continue
        for fn in filenames:
            if not fn.endswith(".java"):
                continue
            cls = fn[:-5]
            if cls not in wanted_types:
                continue
            p = os.path.join(dirpath, fn)
            try:
                src = strip_noise(open(p, encoding="utf-8", errors="replace").read())
            except OSError:
                continue
            for kind, name, text, _, _ in parse_methods(src)[0]:
                if name not in idx[cls]:
                    idx[cls][name] = text
    return idx


def main():
    os.makedirs(OUT, exist_ok=True)
    index = pd.read_csv(os.path.join(SRC, "index.csv"))
    index = index[index.file.notna()].copy()
    index["sha2"] = [s if isinstance(s, str) else FALLBACK_SHA.get(p, "")
                     for p, s in zip(index.project, index.sha)]

    rows = []
    for (proj, sha), grp in index.groupby(["project", "sha2"]):
        if not sha:
            print("!! no commit for %s, skipping %d tests" % (proj, len(grp)))
            continue
        # what do these tests need?
        need_pairs, need_types = set(), set()
        per_test = {}
        for _, r in grp.iterrows():
            p = os.path.join(SRC, r.project, r.file)
            if not os.path.exists(p):
                continue
            src = strip_noise(open(p, encoding="utf-8", errors="replace").read())
            sl = slices_for(src, r.test.split(".")[-1])
            body = sl["body"] + "\n" + sl["helpers"]
            pairs, types = wanted_calls(body, sl["fields"])
            per_test[r.test] = pairs
            need_pairs |= pairs
            need_types |= types | {t for t, _ in pairs}

        print("== %s @ %s: %d tests, %d candidate types"
              % (proj, sha, len(grp), len(need_types)), flush=True)
        tree = checkout_main(REPO_DIR[proj], sha)
        if tree:
            idx = index_tree(tree, need_types)
        else:
            print("   checkout refused; reading from git objects instead",
                  flush=True)
            idx = index_from_objects(REPO_DIR[proj], sha, need_types)
        print("   resolved %d of %d types in the main tree"
              % (len(idx), len(need_types)), flush=True)

        for _, r in grp.iterrows():
            pairs = per_test.get(r.test, set())
            got, texts = [], []
            for cls, meth in sorted(pairs):
                if cls in idx and meth in idx[cls]:
                    got.append("%s.%s" % (cls, meth))
                    texts.append(idx[cls][meth])
            fn = "%s__%s.java" % (r.test.split(".")[0], r.test.split(".")[-1])
            with open(os.path.join(OUT, "%s__%s" % (r.project, fn)), "w",
                      encoding="utf-8", errors="replace") as fh:
                fh.write("\n".join(texts))
            rows.append(dict(project=r.project, test=r.test, sha=sha,
                             callees=len(got), resolved=";".join(got[:20]),
                             file="%s__%s" % (r.project, fn)))

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT, "callees_index.csv"), index=False)
    print("\n%d tests, %d with at least one resolved callee (%.0f%%)"
          % (len(out), (out.callees > 0).sum(),
             100 * (out.callees > 0).mean() if len(out) else 0))
    print(out.groupby("project").agg(tests=("test", "size"),
                                     with_callees=("callees", lambda s: (s > 0).sum()),
                                     median=("callees", "median")).to_string())


if __name__ == "__main__":
    main()
