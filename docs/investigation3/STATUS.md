# Investigation 3 — status, and where to pick it up

Written for someone joining cold. It assumes no knowledge of the earlier work and
explains the question, what has been built, what has been measured, and what the
open problem is. Every number here comes from a file in the repository; where a
number is provisional or thin, it says so.

---

## 1. The question

A flaky test is one whose **verdict depends on a choice it does not control** —
the iteration order of a hash container, the interleaving of two threads, the
reading of a clock, the order tests happen to run in.

The claim under investigation is that flaky-test detectors do not learn that.
They learn the **hazard** — the presence of a risky API — rather than the
**defect**, which is a *path* from an uncontrolled choice to an assertion with
nothing closing it. If that is true, a detector will fire on any test that merely
touches a `HashMap`, whether or not the verdict could ever depend on it.

Three things must hold for a test to be flaky, and the distinction runs through
everything below:

| | |
| --- | --- |
| **hazard** | an uncontrolled choice exists (`new HashMap<>()`, `System.currentTimeMillis()`) |
| **exposure + path** | the choice is revealed by some operation, and that value reaches an assertion |
| **control** | nothing on the way closes the choice (a `sort`, a fixed clock, a tolerance) |

A hazard on its own is not a defect. That sentence is the whole investigation.

---

## 2. The two corpora, and why both are needed

Neither dataset can answer the question alone.

**FlakeBench** (`FlakeBench/FlakeBench_dataset.csv`) — 8,574 rows over 98
projects: **280 flaky and 8,294 non-flaky**, labelled into five categories. It is
the only source of a **negative class**, without which no false-positive rate and
no precision can be computed. 96 of its 98 projects contain both flaky and
non-flaky tests, so the comparison is controlled rather than confounded by
project. It has **no fixes**.

**The before/after pair corpus** (IDoFT and others, see `datasets.md`) — 2,214
eligible pairs of (commit before a flakiness fix, commit after). It is the only
source of evidence about what a *repair* changes. Every subject in it is flaky,
so it has no negative class at all.

The two halves of the claim map onto them exactly:

- *"detectors learn the hazard"* needs the negative class → FlakeBench
- *"…rather than the defect"* needs before/after → the pair corpus

One caution about the pair corpus that shaped the plan: its 2,214 pairs reduce to
**672 distinct commit pairs**, and by category those are 523 unordered
collections, 109 order dependency, 26 async, 3 time and **0 concurrency**. It is
a single-category corpus with a tail, not a five-category corpus.

---

## 3. What has been measured

### 3.1 Tier 1 — a hazard lexicon, the thing being criticised

A liberal lexicon of 38 hazard families (`docs/investigation2/lexicon.json`)
applied to three scopes: the test body, the test class fields, and the fixtures
(`@Before` / `@After` / `@Rule` and initialiser blocks).

Reported on the **availability-matched subset** — 164 flaky against 6,926
non-flaky, all of which have all three scopes present. Matching matters: class
scopes resolve for 83.5% of non-flaky and only 58.6% of flaky, so pooling
unmatched would hand the non-flaky class more chances to be flagged.

| scope | flaky | non-flaky | gap | lift over base rate |
| --- | ---: | ---: | ---: | ---: |
| test body | 75.0% | 49.0% | 26.0 | 1.51× |
| fixtures | 56.1% | 35.3% | 20.8 | 1.57× |
| **fields** | **39.0%** | **36.5%** | **2.5** | **1.07×** |
| all three | 93.3% | 69.5% | 23.7 | 1.33× |

Two results:

1. **A declared field carries essentially no signal.** 36.5% of non-flaky tests
   have a hazard token in a field, against 39.0% of flaky ones.
2. **Widening the scope makes the classifier worse.** Body alone is 1.51×; adding
   fixtures and fields drops it to 1.33×, because hazard evidence accumulates on
   both classes at once.

The conclusion does not depend on the gate threshold described in §5.2 — across
every setting the fields lift runs 0.77×–1.07×, never meaningfully above 1.

On the pair corpus the same lexicon flagged **before and after the fix
identically on 57 of 57 pairs**. A hazard token survives the repair that removes
the flakiness, which is the same finding from the other direction.

### 3.2 Tier 2 — a first prototype of the path-and-control analysis

`SliceAnalysis.java` asks the four-part question instead: start at the assertion,
walk backwards, and flag only *hazard **and** exposure **and** path **and** not
controlled*. Piloted on unordered collections, the category with the clearest
vocabulary and 40 of its 41 flaky tests located.

| stage | flaky (39) | non-flaky (6,980) | lift |
| --- | ---: | ---: | ---: |
| hazard anywhere (typed) | 28.2% | 7.2% | 3.83× |
| hazard on path to an assertion | 15.4% | 3.6% | 4.17× |
| + through an exposing operation | 7.7% | 1.2% | 6.35× |
| **+ uncontrolled = FLAG** | **5.1%** | **0.4%** | **11.61×** |

Every element earns its place: lift climbs monotonically, and the *typed* hazard
baseline alone (3.83×) is already far better than tier 1's 1.51×, which says much
of tier 1's failure was an over-broad token lexicon rather than the hazard idea
being worthless.

**But recall is 5.1%,** and that is the open problem. See §6.

---

## 4. What exists in the repository

### 4.1 Documents

| file | content |
| --- | --- |
| `datasets.md` | how the pair corpus was assembled from IDoFT, ReproFlake, FlakeSync, ODRepair |
| `METHODOLOGY.md` | the full process record. §1–12 the pair corpus, **§13 the FlakeBench corpus** |
| `RUNNER.md` | the evidence runner, its departures from prior work, and **§7 the defects the extractor exposed** |
| `STATUS.md` | this file |

### 4.2 Data

| path | content |
| --- | --- |
| `fb_features.csv` | **8,574 rows, one per FlakeBench test** — the tier-1 result. Identity, label, provenance (`located`, `body_match`, `body_similarity`, `class_scopes_available`) and per-scope flags with the families that fired |
| `pairs.csv`, `pairs_resolved.csv` | the 2,654-row pair corpus and its PR-resolved form |
| `runs_fb/_specs/` | 172 build-point specs plus `index.csv` |
| `runs_fb/_bp/<bp>/` | per build point: `spoon_methods.json` (the source model), `tests_resolved.csv`, `status.json` |
| `runs_fb/logs/` | sweep logs |
| `runs/tools/` | Spoon and JaCoCo jars, and `spoon_cp.txt` |

The pair evidence (`runs2/`, 57 pairs including every `jacoco.exec`) is **not in
the working tree**. It is archived on the branch `investigation3/pairs-evidence`
and can be restored with `git checkout investigation3/pairs-evidence -- runs2`.

### 4.3 Scripts

Collection, FlakeBench:

| script | what it does |
| --- | --- |
| `build_flakebench_bp.py` | dataset → 172 build-point specs; also holds the test-name parser |
| `run_spoon_fb.py` | one build point: checkout → index the tree → Spoon over the relevant modules → resolve candidates → delete the checkout. **No Maven, no JaCoCo** |
| `extract_features_fb.py` | the tier-1 extractor, one row per test, both classes |

Analysis, tier 2:

| script | what it does |
| --- | --- |
| `SliceAnalysis.java` | the four-part analysis. `snippets` mode parses stored bodies; `sources` mode parses a real checkout |
| `pilot_slice_bodies.py` | pilot 1 — runs it over stored `body` text, no checkout |
| `pilot_slice_sources.py` | pilot 2 — checks out 5 projects and runs it over full sources |

Collection, pairs (used for the before/after corpus):

`build_pairs.py`, `resolve_prs.py`, `run_pair.py`, `run_group.py`,
`run_groups.py`, `collect_coverage.py`, `join_spoon_coverage.py`,
`extract_features.py`, `SpoonExtract.java`, plus the `probe_*.sh` and
`fetch_sources.sh` helpers.

### 4.4 Reproducing the current numbers

```bash
# tier 1, from the models already on disk (a few minutes, no network)
python docs/investigation3/scripts/extract_features_fb.py --runs runs_fb \
       --out docs/investigation3/fb_features.csv

# tier 2 pilot 1, no checkout
python docs/investigation3/scripts/pilot_slice_bodies.py

# re-collect a build point from scratch (needs network)
python docs/investigation3/scripts/run_spoon_fb.py \
       --spec runs_fb/_specs/<name>.json --tools runs/tools
```

---

## 5. Things that will bite you

### 5.1 Windows, four times over

Every one of these produced a failure that looked like a data problem:

- `core.longpaths` unset → silently incomplete checkouts
- `core.autocrlf` on → LF rewritten to CRLF, which failed 24 consecutive builds
  on a line-ending checkstyle rule and would have corrupted every `raw_body`
- `file.encoding` defaulting to cp1252 → `maven-compiler-plugin` dies with
  `Error while storing the mojo status: Input length = 1`
- **MAX_PATH again on deletion**: git *creates* 333-character paths because
  `core.longpaths` is set, but Python refuses them without the `\\?\` prefix, so
  checkouts survived every cleanup attempt and then failed the next run

All four are handled in `run_pair.py`. The lesson is that a failure that looks
like a broken repository is usually the platform.

### 5.2 FlakeBench's own data has defects

Found by using it, all handled, all documented in `METHODOLOGY.md` §13.4:

- **three `shas` entries are not SHAs** — a source file path, a `commit `-prefixed
  hex, and apache_jackrabbit's SVN revisions, which cannot be fetched from a git
  remote at all and cost the project and its 48 tests
- **`id` is not a primary key** — 66 ids name two different tests
- **81 `test_name` values are not `Class.method`**, and *every one of the 81 is
  flaky*: 61 bare method names, 18 prefixed with a commit sha, 2 with a package
  fragment. Rejecting them cost 29% of the positive class before it was fixed
- **the recorded SHA is often not the commit `full_code` came from.** This is why
  `body_match` and `usable_for_class_scopes` exist. The body scope is immune
  because it reads `full_code` directly; the class scopes are gated at a 0.85
  similarity threshold, with the raw ratio stored per test so it can be re-tuned
  without re-running anything

### 5.3 Two shell traps

The Bash tool eats a backslash inside heredocs, so regexes written that way
silently lose their escapes (`\b` became a literal backspace once). Use the file
tools for anything containing backslashes. And `cmd | tail` reports *tail's* exit
status, which once made a failed `git push` look successful.

---

## 6. Where it stands, and what to do next

### 6.1 The state in one paragraph

Tier 1 is finished and the result is solid: hazard tokens do not separate flaky
from non-flaky, and the separation *degrades* as the scope widens. Tier 2 has a
working prototype whose precision is excellent — 11.6× lift against tier 1's
1.5× — and whose recall is 5%. The open problem is recall, and its cause is
known precisely.

### 6.2 Why recall is 5%, measured not guessed

Two compounding losses on the 39 flaky unordered-collections tests:

- **Only 28% have a typed hazard in the test body at all.** The rest live in a
  field, a fixture, or production code the test calls.
- **Of those that do, two-thirds are lost before the flag:** 11 have a hazard →
  6 reach an assertion → 3 through an exposing operation → 2 uncontrolled.

### 6.3 The next step, and an honest note about the pilot that was meant to test it

`SliceAnalysis`'s backward walk currently resolves **only local variables inside
the one method**. A field read hits a dead end; a call into production code is
not followed.

Pilot 2 was supposed to test whether full source context helps. It checked out
five projects, built a model holding every field, fixture and production class —
**and then the analysis ignored all of it**, because the walk is intraprocedural.
Its headline (26.7× lift) is one detection out of 15 flaky tests: noise. So that
pilot did *not* answer the question it was built for. What it did establish is
that the machinery runs on real sources, and that the bottleneck is analysis
depth rather than the parse route.

The next step is therefore to make the walk interprocedural, in this order:

1. **Field and fixture reads** — resolve a field to its initialiser and to any
   assignment in a `@Before` method. Cheap; pilot 2's model already holds them.
2. **Callee bodies** — follow a call into the method it invokes, bounded depth.
   This is what resolves `assertEquals(expected, service.getNames())`, where the
   hash container lives inside `service`.

Only after that is it worth re-running the pilot-1 versus pilot-2 comparison,
because only then is there anything for the extra context to feed.

### 6.4 The validation that is waiting, and costs nothing

**A fix is by definition an act of closing a hazard.** So on the before/after
pairs, a correct tier 2 must flag the *before* side and go quiet on the *after*
side. Tier 1 scored 57/57 identical, which is exactly its failure mode.

The pair corpus holds **523 distinct unordered-collections repair diffs**, and
the two repairs already inspected separate the mechanisms cleanly:

| repair | hazard source before | after | what has to catch it |
| --- | --- | --- | --- |
| `HashMap` → `LinkedHashMap` | hash container | ordered container | typing alone |
| `Arrays.sort(...)` added after `getDeclaredMethods()` | `getDeclaredMethods` | **unchanged** | only control analysis |

The second is the existence proof that a lexicon of any narrowness cannot do this
job: the hazard source is byte-identical on both sides of the fix.

This validation needs no new collection — `runs2` is one `git checkout` away.

### 6.5 Deliberately not done

- **The JaCoCo/coverage pass over FlakeBench.** The production-closure scope
  saturated at 99.1% on the pair corpus, so it is predicted to push non-flaky
  toward 100% and lift toward 1.0. It cannot help tier-1 *classification*. It
  remains necessary for *localisation*: static call-graph reachability recovered
  3.8% and 0.0% of the covered set on the two pairs measured and missed the
  developer's repair site in both, because JUnit runners, reflection and
  dependency injection reach code the test's call chain does not.
- **A learned classifier.** The thesis is that learned detectors pick up hazards
  rather than defects; using one as the contribution would undercut the argument.

### 6.6 What the corpus can and cannot support

| | flaky | non-flaky |
| --- | ---: | ---: |
| body scope — complete, needs no checkout | **280** | **8,294** |
| Spoon AST of the test method | 231 | 7,008 |
| + body confirmed to match, + fields + fixtures | 164 | 6,926 |

Flaky class-scope coverage by category: unordered collections 37/41, order
dependency 66/93, async wait 36/76, **concurrency 16/37, time 9/33**.

The aggregate comparison is well powered. Unordered collections and order
dependency support category-specific claims. **Concurrency and time do not**, and
no additional compute changes that — it is a property of FlakeBench's 280 flaky
tests. The class imbalance is roughly 42:1, so report rates within each class; a
pooled precision figure mostly measures the base rate.

---

## 7. Git

| branch | content |
| --- | --- |
| `investigation3/flakebench` | current work — scripts, documents, `fb_features.csv` |
| `investigation3/pairs-evidence` | the archived pair evidence, `runs2/` with all 114 `jacoco.exec` |
| `main` | upstream FlakeBench, untouched |

`runs_fb/` and `runs/` are gitignored: 3.4 GB of models, regenerable from the
specs at roughly 40 seconds per build point.
