"""Derive the hazard and control vocabularies from what flakiness fixes CHANGED.

    python mine_fix_diffs.py fetch    [--limit N] [--jobs N]
    python mine_fix_diffs.py derive   [--min-projects 5] [--min-commits 6]

WHY THIS EXISTS
---------------
The tier-1 lexicon (docs/investigation2/lexicon.json) is mined from flaky test
*bodies* and evaluated on the corpus it was mined from. Two problems, and the
second is the serious one:

  1. Circularity. FlakeBench in, FlakeBench out. "Held out" controls for
     memorisation, not for distribution.
  2. It is mined from the wrong thing. The claim under investigation is that
     what a flaky test *contains* is not what makes it flaky. A vocabulary
     derived from flaky test bodies is derived from exactly the correlation we
     argue is spurious, so it cannot be used as evidence about that correlation
     without begging the question.

This mines the repairs instead. A construct earns its place if developers
actually changed it to fix flakiness. That is causal rather than correlational,
and it comes from the IDoFT pair corpus, which is not the evaluation set.

A fix diff hands over both halves of the vocabulary at once:

    -      resultBuilder.add(clazz.getDeclaredMethods());          <- HAZARD
    +      Method[] declaredMethods = clazz.getDeclaredMethods();
    +      Arrays.sort(declaredMethods, Comparator.comparing(...)); <- CONTROL

Removed and context lines at the repair site name the uncontrolled choice; added
lines name the operation that closes it. The control half matters independently:
SliceAnalysis.java currently carries a hand-written CONTROL set, and this
replaces that guess with evidence.

METHOD
------
Fetch each fix commit through `gh api repos/{slug}/commits/{sha}` — the API
returns per-file patches, so no checkout is needed anywhere in this pipeline.
For a background, sample ordinary commits from the same projects, so that project
idiom (a house style that always uses Guava, say) cancels out instead of being
mistaken for a flakiness signal.

Scoring is the log-odds ratio with an informative Dirichlet prior (Monroe,
Colaresi and Quinn 2008), which is the standard way to compare token usage
between two corpora and, unlike raw frequency ratios, does not hand the top of
the table to constructs that appear twice. Reported as a z-score.

Support floors match the existing lexicon's mining criteria so the two are
comparable: a construct must appear in at least 5 distinct projects and 6
distinct commits.
"""
import argparse
import collections
import csv
import json
import math
import os
import random
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PAIRS = os.path.join(ROOT, "docs", "investigation3", "pairs_resolved.csv")
CACHE = os.path.join(ROOT, "mining", "commits")
OUT_DIR = os.path.join(ROOT, "docs", "investigation3")

# A commit that rewrites half the repository says nothing about one flaky test,
# and its vocabulary would swamp the counts. The cap is generous: the median
# flakiness fix touches 1-2 Java files.
MAX_JAVA_FILES = 25

TEST_PATH = re.compile(r"(^|/)(test|tests|src/test)/|Test[s]?\.java$|IT\.java$"
                       r"|TestCase\.java$", re.I)


# --------------------------------------------------------------- construct set

# Constructs, not words. A bare identifier like "sort" is ambiguous; ".sort(" as
# a call is not. Each pattern yields a namespaced token so the two vocabularies
# stay readable and so a call never collides with a type of the same name.
CONSTRUCT_PATTERNS = [
    ("call", re.compile(r"\.(\w+)\s*\(")),
    ("new", re.compile(r"\bnew\s+([A-Z]\w*)")),
    ("static", re.compile(r"\b([A-Z]\w*)\s*\.\s*(\w+)\s*\(")),
    ("type", re.compile(r"\b([A-Z][A-Za-z0-9]{2,})\b")),
    ("annot", re.compile(r"@(\w+)")),
    ("kw", re.compile(r"\b(synchronized|volatile|transient|static|final)\b")),
]

# Comments and string literals are stripped before extraction, exactly as the
# tier-1 lexicon does, so a token inside a log message is not evidence.
STR = re.compile(r'"(?:\\.|[^"\\])*"')
CHR = re.compile(r"'(?:\\.|[^'\\])'")
LINE_COMMENT = re.compile(r"//[^\n]*")


def strip_source(s):
    return STR.sub('""', CHR.sub("' '", LINE_COMMENT.sub(" ", s or "")))


def constructs(line):
    """Namespaced constructs in one source line."""
    out = set()
    s = strip_source(line)
    for kind, pat in CONSTRUCT_PATTERNS:
        for m in pat.finditer(s):
            if kind == "static":
                out.add(f"static:{m.group(1)}.{m.group(2)}")
            else:
                out.add(f"{kind}:{m.group(1)}")
    return out


# --------------------------------------------------------------------- fetching

TRANSIENT = ("timeout", "timed out", "connection", "could not resolve",
             "bad gateway", "502", "503", "504", "rate limit", "abuse",
             "secondary rate", "eof", "reset by peer")


def gh_json(path, attempts=3):
    """One gh api call. Returns (parsed, error). Retries only what looks transient.

    Forcing UTF-8 is not optional here: subprocess text mode uses the locale
    codec on Windows, and a commit message with a non-cp1252 character otherwise
    fails with "the JSON object must be str", which cost us seven PR lookups
    earlier in this project.
    """
    delay = 3
    err = ""
    for attempt in range(1, attempts + 1):
        try:
            p = subprocess.run(["gh", "api", path], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=120)
        except Exception as e:
            err = str(e)
            time.sleep(delay)
            delay *= 3
            continue
        if p.returncode == 0:
            try:
                return json.loads(p.stdout), ""
            except Exception as e:
                return None, f"unparseable json: {e}"
        err = (p.stderr or p.stdout or "").strip()[:300]
        low = err.lower()
        if not any(t in low for t in TRANSIENT):
            return None, err            # 404 on a deleted repo: do not retry
        if attempt < attempts:
            time.sleep(delay)
            delay *= 3
    return None, err


def cache_path(slug, sha):
    return os.path.join(CACHE, slug.replace("/", "__") + "__" + sha[:12] + ".json")


def fetch_commit(slug, sha):
    """Cached commit fetch. The cache makes re-derivation free and keeps the
    5,000/hour budget for commits we have not seen."""
    cp = cache_path(slug, sha)
    if os.path.isfile(cp):
        try:
            return json.load(open(cp, encoding="utf-8")), ""
        except Exception:
            pass                        # a truncated cache entry: refetch
    data, err = gh_json(f"repos/{slug}/commits/{sha}")
    if data is None:
        return None, err
    slim = slim_commit(data)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    json.dump(slim, open(cp, "w", encoding="utf-8", newline="\n"))
    return slim, ""


def slim_commit(data):
    """Keep only the Java patches. A full commit payload is mostly metadata we
    never read, and 2,000 of them on disk would be gigabytes."""
    files = []
    for f in data.get("files") or []:
        name = f.get("filename") or ""
        if not name.endswith(".java") or not f.get("patch"):
            continue
        files.append({"filename": name, "patch": f["patch"],
                      "additions": f.get("additions", 0),
                      "deletions": f.get("deletions", 0)})
    return {"sha": data.get("sha", ""), "files": files,
            "n_java": len(files),
            "message": (data.get("commit", {}).get("message") or "")[:200]}


def eligible_pairs():
    rows = list(csv.DictReader(open(PAIRS, encoding="utf-8")))
    return [r for r in rows
            if r["after_type"] != "tool_patch"
            and r["before_sha_reachable"] != "no"
            and r.get("pr_merged") != "false"
            and "(" not in r["test_method"]]


def fix_commits():
    """(slug, sha) -> the labels the pair corpus carries for it."""
    out = collections.defaultdict(lambda: {"categories": set(), "labels": set()})
    for r in eligible_pairs():
        sha = r.get("merge_commit_sha") or ""
        if not sha:
            continue
        k = (r["project_slug"], sha)
        out[k]["categories"].add(r["source_category"])
        out[k]["labels"].add(r["flakebench_label"] or "(none)")
    return out


def cmd_fetch(args):
    os.makedirs(CACHE, exist_ok=True)
    fixes = fix_commits()
    keys = sorted(fixes)
    if args.limit:
        keys = keys[:args.limit]

    print(f"fix commits to fetch: {len(keys)}")
    failures = {}
    ok = 0
    for i, (slug, sha) in enumerate(keys, 1):
        data, err = fetch_commit(slug, sha)
        if data is None:
            failures[f"{slug}@{sha[:12]}"] = err
        else:
            ok += 1
        if i % 50 == 0:
            print(f"  {i}/{len(keys)} fetched, ok={ok}, failed={len(failures)}")
    print(f"fix commits: ok={ok} failed={len(failures)}")

    # ---- background: ordinary commits from the same projects
    projects = sorted({slug for slug, _ in keys})
    fix_shas = {sha for _, sha in keys}
    print(f"\nbackground sampling over {len(projects)} projects, "
          f"{args.background} commits each")
    bg = []
    bg_fail = {}
    for i, slug in enumerate(projects, 1):
        listing, err = gh_json(f"repos/{slug}/commits?per_page=100")
        if listing is None:
            bg_fail[slug] = err
            continue
        cands = [c["sha"] for c in listing
                 if c.get("sha") and c["sha"] not in fix_shas]
        random.Random(slug).shuffle(cands)      # deterministic per project
        taken = 0
        for sha in cands:
            if taken >= args.background:
                break
            data, e2 = fetch_commit(slug, sha)
            if data is None:
                continue
            if data["n_java"] == 0:
                continue                        # no Java: tells us nothing
            bg.append((slug, sha))
            taken += 1
        if i % 25 == 0:
            print(f"  {i}/{len(projects)} projects, {len(bg)} background commits")

    manifest = {
        "fix_commits": [{"slug": s, "sha": h,
                         "categories": sorted(fixes[(s, h)]["categories"]),
                         "labels": sorted(fixes[(s, h)]["labels"])}
                        for (s, h) in keys if os.path.isfile(cache_path(s, h))],
        "background_commits": [{"slug": s, "sha": h} for s, h in bg],
        "fix_failures": failures,
        "background_listing_failures": bg_fail,
    }
    mp = os.path.join(ROOT, "mining", "manifest.json")
    json.dump(manifest, open(mp, "w", encoding="utf-8", newline="\n"), indent=1)
    print(f"\nfix ok {len(manifest['fix_commits'])}, "
          f"background {len(bg)}, manifest -> {mp}")
    return 0


# -------------------------------------------------------------------- deriving

def hunk_lines(patch):
    """(added, removed, context) construct-bearing lines of a unified diff."""
    added, removed, context = [], [], []
    for line in (patch or "").splitlines():
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith(" "):
            context.append(line[1:])
    return added, removed, context


def commit_constructs(commit):
    """Constructs of one commit, split by role and by test/production path.

    Returned as sets: a construct counts once per commit, which is what the
    support floors are expressed in and what stops a single 400-line file from
    dominating.
    """
    out = {"added": set(), "removed_context": set(),
           "added_test": set(), "added_prod": set()}
    if commit["n_java"] > MAX_JAVA_FILES:
        return out
    for f in commit["files"]:
        is_test = bool(TEST_PATH.search(f["filename"]))
        added, removed, context = hunk_lines(f["patch"])
        a = set()
        for ln in added:
            a |= constructs(ln)
        out["added"] |= a
        (out["added_test"] if is_test else out["added_prod"]).__ior__(a)
        for ln in removed + context:
            out["removed_context"] |= constructs(ln)
    return out


def log_odds(counts_a, n_a, counts_b, n_b, prior):
    """Log-odds ratio with an informative Dirichlet prior, as a z-score.

    Monroe, Colaresi and Quinn (2008). The prior is the pooled corpus, which is
    what keeps a construct seen three times in one corpus and never in the other
    from topping the table on the strength of a division by almost zero.
    """
    a0 = sum(prior.values())
    z = {}
    for w in set(counts_a) | set(counts_b):
        ya, yb, aw = counts_a.get(w, 0), counts_b.get(w, 0), prior.get(w, 0)
        if aw == 0:
            continue
        la = math.log((ya + aw) / max(n_a + a0 - ya - aw, 1e-9))
        lb = math.log((yb + aw) / max(n_b + a0 - yb - aw, 1e-9))
        var = 1.0 / (ya + aw) + 1.0 / (yb + aw)
        z[w] = (la - lb) / math.sqrt(var)
    return z


def cmd_derive(args):
    manifest = json.load(open(os.path.join(ROOT, "mining", "manifest.json"),
                              encoding="utf-8"))
    fb_projects = {r["project"].split("_")[-1].lower() for r in csv.DictReader(
        open(os.path.join(ROOT, "FlakeBench", "project_repos.csv"),
             encoding="utf-8"))}

    def load(entries):
        out = []
        for e in entries:
            cp = cache_path(e["slug"], e["sha"])
            if not os.path.isfile(cp):
                continue
            try:
                c = json.load(open(cp, encoding="utf-8"))
            except Exception:
                continue
            c["slug"] = e["slug"]
            c["labels"] = e.get("labels", [])
            c["categories"] = e.get("categories", [])
            out.append(c)
        return out

    fixes = load(manifest["fix_commits"])
    background = load(manifest["background_commits"])

    # A fix commit touches a flaky test by construction; an ordinary commit often
    # touches no test at all (88.5% against 66.9% here). Left uncorrected, that
    # mismatch alone puts every piece of test scaffolding - @Test, Assert,
    # assertEquals - at the top of the HAZARD table, which says only that fixes
    # edit tests. Matching the background on "touches a test file" removes the
    # confound at the cost of a smaller background.
    def touches_test(c):
        return any(TEST_PATH.search(f["filename"]) for f in c["files"])

    if args.match_test_touching:
        before = len(background)
        background = [c for c in background if touches_test(c)]
        print(f"background matched on touching a test file: "
              f"{before} -> {len(background)}")
    print(f"fix commits {len(fixes)}, background commits {len(background)}")

    # per-construct: how many commits, and how many distinct projects
    def tally(commits, role):
        n_commits = collections.Counter()
        n_projects = collections.defaultdict(set)
        for c in commits:
            for w in commit_constructs(c)[role]:
                n_commits[w] += 1
                n_projects[w].add(c["slug"])
        return n_commits, n_projects

    roles = {"control": "added", "hazard": "removed_context"}
    vocab = {}
    for name, role in roles.items():
        fc, fp = tally(fixes, role)
        bc, bp = tally(background, role)
        prior = collections.Counter()
        prior.update(fc)
        prior.update(bc)
        z = log_odds(fc, sum(fc.values()), bc, sum(bc.values()), prior)

        rows = []
        for w, score in z.items():
            if len(fp.get(w, ())) < args.min_projects:
                continue
            if fc.get(w, 0) < args.min_commits:
                continue
            projs = fp[w]
            overlap = {p for p in projs if p.split("/")[-1].lower() in fb_projects}
            rows.append({
                "construct": w,
                "z": round(score, 2),
                "fix_commits": fc.get(w, 0),
                "fix_projects": len(projs),
                "bg_commits": bc.get(w, 0),
                "bg_projects": len(bp.get(w, ())),
                "fix_rate": round(fc.get(w, 0) / max(len(fixes), 1), 4),
                "bg_rate": round(bc.get(w, 0) / max(len(background), 1), 4),
                "projects_overlapping_flakebench": len(overlap),
                "projects_independent": len(projs) - len(overlap),
            })
        rows.sort(key=lambda r: -r["z"])
        vocab[name] = rows
        print(f"  {name:8s} constructs passing support floors: {len(rows)}")

    sfx = args.out_suffix
    out_json = os.path.join(OUT_DIR, f"fix_vocabulary{sfx}.json")
    json.dump({"min_projects": args.min_projects,
               "min_commits": args.min_commits,
               "background_matched_on_test_touching": args.match_test_touching,
               "n_fix_commits": len(fixes),
               "n_background_commits": len(background),
               "vocabulary": vocab},
              open(out_json, "w", encoding="utf-8", newline="\n"), indent=1)

    out_csv = os.path.join(OUT_DIR, f"fix_vocabulary{sfx}.csv")
    with open(out_csv, "w", encoding="utf-8", newline="\n") as fh:
        w = csv.DictWriter(fh, fieldnames=["role"] + list(vocab["control"][0].keys())
                           if vocab["control"] else ["role", "construct"])
        w.writeheader()
        for role, rows in vocab.items():
            for r in rows:
                w.writerow(dict(r, role=role))

    print(f"\nwritten: {out_json}")
    print(f"         {out_csv}")
    report(vocab, fixes)
    return 0


def report(vocab, fixes):
    for name in ("hazard", "control"):
        rows = vocab[name]
        print()
        print(f"=== {name.upper()} — top 20 by log-odds z ===")
        print(f"  {'construct':34s} {'z':>7s} {'fix':>5s} {'proj':>5s} "
              f"{'bg':>5s} {'indep':>6s}")
        for r in rows[:20]:
            print(f"  {r['construct']:34s} {r['z']:7.1f} {r['fix_commits']:5d} "
                  f"{r['fix_projects']:5d} {r['bg_commits']:5d} "
                  f"{r['projects_independent']:6d}")
        if rows:
            print(f"  ... and the weakest passing entry: {rows[-1]['construct']} "
                  f"(z={rows[-1]['z']})")


# ------------------------------------------------------- comparison to tier 1

# A construct is a namespaced token; the lexicon matches source text. Render each
# construct back into the fragment of source it stands for so the two can meet.
def as_source(construct):
    kind, _, rest = construct.partition(":")
    if kind == "call":
        return f".{rest}("
    if kind == "new":
        return f"new {rest}("
    if kind == "static":
        return f"{rest}("
    if kind == "annot":
        return f"@{rest}"
    return rest                     # type, kw


def cmd_compare(args):
    vocab = json.load(open(os.path.join(OUT_DIR, "fix_vocabulary.json"),
                           encoding="utf-8"))["vocabulary"]
    lex = json.load(open(os.path.join(ROOT, "docs", "investigation2",
                                      "lexicon.json"), encoding="utf-8"))
    fams = {}
    for cat, cd in lex["categories"].items():
        for fn, rx in cd["families"].items():
            fams[f"{cat}.{fn}"] = re.compile(rx)

    # measured tier-1 discrimination, from fb_features.csv (STATUS.md 3.1)
    covered = collections.defaultdict(list)
    uncovered = collections.defaultdict(list)
    for role in ("hazard", "control"):
        for r in vocab[role]:
            src = as_source(r["construct"])
            hit = [f for f, rx in fams.items() if rx.search(src)]
            if hit:
                for f in hit:
                    covered[f].append((role, r["construct"], r["z"]))
            else:
                uncovered[role].append(r)

    print("=== LEXICON FAMILIES CORROBORATED BY FIX EVIDENCE ===")
    print(f"  {'family':26s} {'constructs':>10s} {'best z':>8s}  example")
    rows = []
    for f in sorted(fams):
        c = covered.get(f, [])
        best = max((z for _, _, z in c), default=None)
        rows.append((f, len(c), best,
                     max(c, key=lambda x: x[2])[1] if c else ""))
    for f, n, best, ex in sorted(rows, key=lambda x: -(x[2] or -99)):
        b = f"{best:8.1f}" if best is not None else "       -"
        print(f"  {f:26s} {n:10d} {b}  {ex}")

    print()
    print(f"  corroborated families: {sum(1 for _, n, _, _ in rows if n)}"
          f" of {len(fams)}")
    print(f"  families with NO fix evidence: "
          f"{[f for f, n, _, _ in rows if not n]}")

    for role in ("hazard", "control"):
        print()
        print(f"=== {role.upper()} CONSTRUCTS THE LEXICON DOES NOT COVER "
              f"(top 15 by z) ===")
        for r in uncovered[role][:15]:
            print(f"  {r['construct']:34s} z={r['z']:7.1f} "
                  f"fix={r['fix_commits']:4d} bg={r['bg_commits']:4d} "
                  f"proj={r['fix_projects']:3d} indep={r['projects_independent']:3d}")

    out = os.path.join(OUT_DIR, "fix_vs_lexicon.json")
    json.dump({"covered": {k: v for k, v in covered.items()},
               "uncovered": {k: v[:60] for k, v in uncovered.items()}},
              open(out, "w", encoding="utf-8", newline="\n"), indent=1)
    print(f"\nwritten: {out}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch")
    f.add_argument("--limit", type=int, default=0)
    f.add_argument("--background", type=int, default=5,
                   help="ordinary commits sampled per project")
    f.set_defaults(func=cmd_fetch)

    d = sub.add_parser("derive")
    d.add_argument("--min-projects", type=int, default=5)
    d.add_argument("--min-commits", type=int, default=6)
    d.add_argument("--match-test-touching", action="store_true",
                   help="restrict the background to commits that also touch a "
                        "test file, removing the test-scaffolding confound")
    d.add_argument("--out-suffix", default="",
                   help="suffix for the output filenames, to keep variants apart")
    d.set_defaults(func=cmd_derive)

    c = sub.add_parser("compare")
    c.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
