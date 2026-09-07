"""Turn FlakeBench into build-point specs.

    python build_flakebench_bp.py [--out runs_fb] [--dataset ...] [--repos ...]

FlakeBench ships 8,574 tests over 98 projects, but the dataset CSV carries no
commit: `FlakeBench_dataset.csv` has (id, project, test_name, full_code, label,
category) and nothing else. The commits live in `project_repos.csv`, one row per
project with a `;`-separated `shas` column — 175 SHAs in total.

That leaves two things to resolve, and this script resolves neither by guessing:

  WHICH COMMIT a test belongs to
      70 of the 98 projects have exactly one SHA, so the question does not arise.
      The other 28 hold 2,696 of the 8,574 tests between them. Rather than pick a
      SHA, every SHA of a project gets the project's full test list as
      *candidates*, and the Spoon pass records which of them the commit actually
      contains. Resolution is then an observation, not an assumption.

  WHICH CLASS `test_name` names
      It is `SimpleClass.method` — no package, ever (8,505 of 8,574 rows have
      exactly one dot). Two modules of a large project can hold the same simple
      class name, so matching is by simple name and the ambiguity is counted and
      reported rather than silently resolved to the first hit.

61 rows carry no dot at all and 8 more are SHA-prefixed junk; they are written to
the spec with `malformed = yes` so the loss is visible downstream instead of
being a silent shortfall in the totals.

Output, one file per build point:

    <out>/_specs/<project>@<sha12>.json
    <out>/_specs/index.csv
"""
import argparse
import collections
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

WELL_FORMED = re.compile(r"^[A-Za-z_$][\w$]*\.[A-Za-z_$][\w$]*(\[.*\])?$")
SHA40 = re.compile(r"\b[0-9a-f]{40}\b")
SHA_PREFIX = re.compile(r"^[0-9a-f]{40}\.")


def parse_test_name(name):
    """(test_class, test_method, shape) out of FlakeBench's `test_name`.

    The common shape is `SimpleClass.method`, but 81 rows are not — and every one
    of those 81 is flaky, so rejecting them cost 29% of the positive class.
    Three other shapes exist and all are recoverable:

        <40-hex sha>.method       18 rows. The prefix is a commit, not a class,
                                  so the class is unknown and the method is the
                                  suffix.
        pkgfragment.Class.method  2 rows, e.g.
                                  schema.IndexPopulationIT.shutdownDatabase...
                                  The last two segments are what is wanted.
        method                    61 rows: a bare method name, no class at all.

    A bare method name leaves the class to be found in the model. That is
    ambiguous by nature, and the disambiguator is FlakeBench's own full_code —
    the right class is the one whose method body matches it.
    """
    n = (name or "").strip()
    shape = "class.method"
    if SHA_PREFIX.match(n):
        n = n[41:]
        shape = "sha-prefixed"
    parts = n.split(".")
    if len(parts) >= 3:
        return parts[-2], parts[-1], "qualified"
    if len(parts) == 2:
        return parts[0], parts[1], shape
    return "", n, "bare-method"


def normalize_shas(raw):
    """(usable SHAs, rejected entries) out of the `shas` column.

    Three rows of FlakeBench's project_repos.csv do not hold a bare SHA:

        ReactiveX_RxJava    a source file path in the SHA column
        apache_pulsar       one entry prefixed with the word "commit "
        apache_jackrabbit   SVN revision numbers (1522657, 1157104) — that
                            project was on SVN, and these cannot be fetched from
                            a git remote at all

    The first two are recoverable by pulling the 40-hex token out. The third is
    not, so it is returned as a rejection and reported, because losing a project
    silently is how a corpus total stops meaning anything.
    """
    usable, rejected = [], []
    for entry in raw.split(";"):
        e = entry.strip()
        if not e:
            continue
        m = SHA40.search(e)
        if m:
            usable.append(m.group(0))
        else:
            rejected.append(e)
    return usable, rejected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset",
                    default=os.path.join(ROOT, "FlakeBench", "FlakeBench_dataset.csv"))
    ap.add_argument("--repos",
                    default=os.path.join(ROOT, "FlakeBench", "project_repos.csv"))
    ap.add_argument("--out", default="runs_fb")
    ap.add_argument("--projects", default="",
                    help="comma-separated project names, for a pilot slice")
    args = ap.parse_args()

    tests = list(csv.DictReader(open(args.dataset, encoding="utf-8")))
    repos = {r["project"]: r for r in csv.DictReader(open(args.repos, encoding="utf-8"))}

    wanted = {p.strip() for p in args.projects.split(",") if p.strip()}
    by_project = collections.defaultdict(list)
    for t in tests:
        if wanted and t["project"] not in wanted:
            continue
        by_project[t["project"]].append(t)

    spec_dir = os.path.join(args.out, "_specs")
    os.makedirs(spec_dir, exist_ok=True)

    index, n_specs, n_malformed = [], 0, 0
    bad_shas, lost_tests = [], 0
    for project, rows in sorted(by_project.items()):
        repo = repos.get(project)
        if not repo:
            print(f"  no repo row for {project}: {len(rows)} tests dropped")
            continue
        shas, rejected = normalize_shas(repo["shas"])
        if rejected:
            bad_shas.append({"project": project, "tests": len(rows),
                             "rejected": rejected, "usable": len(shas)})
        if not shas:
            lost_tests += len(rows)
            continue

        candidates = []
        for t in rows:
            name = t["test_name"].strip()
            cls, meth, shape = parse_test_name(name)
            if shape != "class.method":
                n_malformed += 1
            candidates.append({
                "id": t["id"],
                "test_name": name,
                "test_class": cls,          # simple name; FlakeBench carries no package
                "test_method": meth,
                "name_shape": shape,
                "label": t["label"],
                "category": t["category"],
                # kept for continuity: "malformed" now means "not the plain shape",
                # not "unusable" - these resolve, just by a different route
                "malformed": "" if shape == "class.method" else shape,
            })

        for sha in shas:
            key = f"{repo['repo'].rsplit('/', 1)[-1]}@{sha[:12]}"
            spec = {
                "build_point": key,
                "project": project,
                "project_slug": repo["repo"],
                "project_url": repo["repo_url"],
                "ref": sha,
                "n_shas_in_project": len(shas),
                "out": os.path.abspath(args.out),
                # every SHA of a project gets the whole list; the Spoon pass says
                # which of them this commit actually contains
                "candidate_tests": candidates,
            }
            with open(os.path.join(spec_dir, key + ".json"), "w",
                      encoding="utf-8", newline="\n") as fh:
                json.dump(spec, fh, indent=1)
            n_specs += 1
            index.append({
                "build_point": key, "project": project,
                "project_slug": repo["repo"], "ref": sha,
                "n_shas_in_project": len(shas),
                "candidate_tests": len(candidates),
                "flaky": sum(1 for c in candidates if c["label"] != "non-flaky"),
                "non_flaky": sum(1 for c in candidates if c["label"] == "non-flaky"),
            })

    with open(os.path.join(spec_dir, "index.csv"), "w",
              encoding="utf-8", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=list(index[0]))
        w.writeheader()
        w.writerows(index)

    single = sum(1 for r in index if r["n_shas_in_project"] == 1)
    covered = sum(r["candidate_tests"] for r in index if r["n_shas_in_project"] == 1)
    print(f"build points     {n_specs}   ({single} in single-SHA projects)")
    print(f"projects         {len({r['project'] for r in index})} of {len(by_project)}")
    print(f"tests            {sum(len(v) for v in by_project.values())}"
          f"   malformed names: {n_malformed}   dropped with their project: {lost_tests}")
    if bad_shas:
        print()
        print("  project_repos.csv rows whose sha column needed repair:")
        for b in bad_shas:
            state = f"{b['usable']} usable" if b["usable"] else "NO usable SHA - project dropped"
            print(f"    {b['project']:22s} {state:32s} rejected {b['rejected'][:2]}")
    print()
    print(f"specs written to {spec_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
