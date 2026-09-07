# Investigation 3 — Methodology and Process Record

How this investigation got from a question to `pairs.csv`. Written so the numbers can
be re-derived and the judgement calls can be argued with.

Companion documents in this directory:

| File | What it holds |
| --- | --- |
| `PLAN.md` | the experimental design (E0–E5), features, phasing, threats |
| `datasets.md` | the source inventory, with counts and feasibility |
| `pairs.csv` | the corpus itself, 2,654 rows |
| `slack.md` | the alignment message drafted for the supervisor |
| `RUNNER.md` | the evidence runner: JaCoCo + Spoon per pair, and what it produces |
| `scripts/` | everything needed to rebuild `pairs.csv` and to run the pairs |
| `../what_makes_a_test_flaky.md` | the conceptual argument the investigation tests |

---

## 1. Where the investigation came from

The supervisor raised an objection to investigations 1 and 2: *a flaky test and its
FlakeSync-repaired counterpart carry the same signals, so what is a token model
actually detecting?*

Working that through (`../what_makes_a_test_flaky.md`) produced a claim: a repair
removes the *dependency* of the verdict on an uncontrolled choice, and essentially never
removes the *hazard* — the threads, the `HashMap`, the clock call all remain. If that is
right, then a bag-of-tokens model sees an identical input before and after a repair, and
is at chance on the flaky/non-flaky decision by construction.

That claim is falsifiable, and the instrument is a corpus of **before/after fix pairs**.
Everything below is the work of building that corpus.

**Status.** No experiment from `PLAN.md` has been run. The supervisor alignment check
(`slack.md`) is still outstanding, and the plan is explicitly paused until it happens.
This document covers corpus construction only.

---

## 2. Source discovery

Sources were found by working outward from IDoFT: the papers that use it, the tools that
repair its subjects, and the datasets that re-package it. Each candidate was then asked
one question — **does it supply an *after* side?** — and kept or dropped on the answer.

| Source | How found | Supplies a fix? | Kept |
| --- | --- | :-: | --- |
| **IDoFT** `pr-data.csv` | given by the supervisor as the starting point | yes — merged PR | **yes** |
| **ReproFlake** | search for reproducible flaky-test datasets; arXiv:2605.21677 | yes — fixed commit SHA | **yes** |
| **FlakeSync** | already known from investigations 1–2; subject list found inside `shanto-Rahman/NOD-Test-Repair` rather than in the 1.5 GB Zenodo tarball | yes — tool patch | **yes** |
| **ODRepair** | referenced by FlakyDoctor as its OD input | yes — 59 `.patch` files | **yes** |
| FlakyFix | search for flaky-fix taxonomies | no — labels over IDoFT pairs | no (label layer) |
| Flakify | cited by the C-IDoFT critique | no — re-packages IDoFT pairs | no |
| FlakyDoctor | search for LLM flaky repair | no — reuses IDoFT + ODRepair | no |
| iFixFlakies | the original OD repair tool | partly — 21 merged (already in IDoFT), rest not enumerable from the repo, which ships the tool and no dataset | no |
| NOD-Test-Repair | already known; the JaCoCo pipeline we reviewed | no | no (tooling) |
| FlakeRake | mirrored inside NOD-Test-Repair | no — reproduces failures, does not repair | no |
| C-IDoFT / FlakeCI | arXiv:2607.09345 | no — labels from 500 reruns | no (but see §8) |
| ShowFlakes, iPFlakies, IDoFT `gr-data`/`py-data` | Python and Gradle | yes | no — out of scope, §3 |

---

## 3. Scope: Maven-built Java only

Set by the user after the first survey. The reason is not arbitrary: the tier-2 analysis
needs per-test coverage, and the only pipeline that exists for that is Maven-specific —
a JaCoCo agent injected into `pom.xml`, `mvn test -Dtest=<one test>`, then
`jacococli report --xml`. Every reusable tool in this space assumes it.

Cost of the restriction, recorded so it stays reversible: IDoFT `gr-data.csv` (161
pairs, Gradle), IDoFT `py-data.csv` (74 pairs, Python), ShowFlakes (75 commits), and
iPFlakies. The Python IDoFT rows are proportionally much richer in NIO (45 of 74) than
the Maven file, which is worth remembering if the restriction is ever lifted.

---

## 4. What counts as a pair

A row enters `pairs.csv` only if all four hold:

1. The test is identified as flaky, with a category.
2. There is a **before** commit that can be named.
3. There is an **after** side — a merged PR, a fixed commit SHA, or a patch file.
4. The provenance of the repair is known, so developer-authored and tool-generated
   repairs can be separated rather than blended.

For IDoFT this means `Status ∈ {Accepted, DeveloperFixed, InspiredAFix}` **and** a PR
link. `Opened` (1,508 rows) is excluded — a PR that was never merged is not a repair.
So are `Deleted`, `DeveloperWontFix`, `Rejected` and the rest.

---

## 5. Deduplication

The four sources overlap heavily, because three of them draw their subjects from IDoFT.
Overlap was **computed, not assumed**, by matching on
`(project slug, fully-qualified test name)`, lowercased, with `#` normalised to `.`.

| Source | Claimed | Overlap | Net new |
| --- | ---: | --- | ---: |
| IDoFT | 2,487 | — (base) | 2,487 |
| ReproFlake | 1,115 | 1,049 of 1,052 iDoFT-sourced rows, and 12 of 63 Jira-sourced rows, are already in the IDoFT pair set | **54** |
| FlakeSync | 72 | 71 of 72 appear in IDoFT — but **none has a merged developer fix** | **72** |
| ODRepair | 59 | all 59 appear in IDoFT; **18 already have a merged developer fix** | **41** |
| | | **Total** | **2,654** |

Two of these need explaining, because a naive overlap count gets them backwards.

**FlakeSync's 71/72 overlap is not duplication.** The tests are the same tests IDoFT
lists, but IDoFT records no accepted repair for a single one of them. The overlap is on
*detection*; the *fix* exists only in FlakeSync. Subtracting it would delete the entire
async arm.

**ReproFlake usually disagrees with IDoFT about the commit.** Only 179 of the 1,049
overlapping rows share IDoFT's `SHA Detected`; for the rest ReproFlake picked a different
flaky commit — presumably one that builds. They are still the same pair, so they are
deduplicated on test identity, not on SHA. Where the two disagree, ReproFlake's commit
is the one to use, because it comes with a working environment.

The 1,058 overlapping ReproFlake rows are dropped as pairs but kept as **metadata**:
their `build_env`, `java_version`, `reproflake_zip` and `reproflake_url` are joined onto
the corresponding IDoFT rows. That is how 1,111 rows in `pairs.csv` end up carrying a
ready-made build environment.

---

## 6. Mapping to FlakeBench labels

`pairs.csv` carries both taxonomies. The source label is preserved verbatim in
`source_category`; the mapped label is in `flakebench_label`, with FlakeBench's own
numeric code in `flakebench_category` (0 async wait, 1 concurrency, 2 time,
3 unordered collections, 4 test order dependency, 5 non-flaky).

The mapping is not one-to-one, so every row also carries `label_confidence`,
`label_candidates` and a `mapping_note`.

| Source category | FlakeBench label | Code | Confidence | Reasoning |
| --- | --- | :-: | --- | --- |
| `ID` | unordered collections | 3 | high | NonDex-induced iteration order over hash containers and reflection — exactly what the FlakeBench label denotes |
| `OD`, `OD-Vic`, `OD-Brit` | test order dependency | 4 | high | direct correspondence |
| `NIO` | test order dependency | 4 | **medium** | non-idempotent-outcome is order dependency in which the polluter *is* the victim. FlakeBench has no label for it. Mapped, but it should be reported separately |
| `NOD` from FlakeSync | async wait | 0 | high | that subject set is async by construction |
| `NOD` from IDoFT | *(left blank)* | — | **ambiguous** | IDoFT's NOD does not separate async from concurrency. `label_candidates = async wait\|concurrency`; needs manual triage |
| `TD` from ReproFlake | async wait | 0 | **medium** | timing-dependent in FlakeRake's sleep-injection sense, which is nearer async than FlakeBench's `time` (clock and timezone). `label_candidates = async wait\|time` |
| `TZD` | time | 2 | high | timezone dependence is what the label means |
| `UD`, `Unclassified` | *(left blank)* | — | unknown | no basis to assign one |

Multi-label IDoFT rows (21 of them, e.g. `NIO;OD-Vic`) are mapped on their **first**
label. The full original string survives in `source_category`, so the choice is
reversible.

Resulting distribution: 1,953 unordered collections, 547 test order dependency,
108 async wait, 4 time, 42 unlabelled. Confidence: 2,419 high, 193 medium,
30 ambiguous, 12 unknown.

**Design decision worth flagging:** the 30 ambiguous rows were left with an *empty*
label rather than being guessed into one bucket. Guessing would have inflated whichever
category received them, in the two categories where the corpus is thinnest and where an
inflated count would matter most.

---

## 7. Feasibility — what was measured

The user's requirement was that a source is only listed if we can actually run JaCoCo
and Spoon on it. That turned into four measurements, all made on this machine on
2026-09-06.

### 7.1 Environment

| Component | Found | Consequence |
| --- | --- | --- |
| JDK | Temurin 11.0.32, the only one installed | insufficient — see 7.4 |
| Maven | 3.9.16 | fine |
| Git | 2.55.0.windows.5, `core.longpaths` **unset** | see 7.3 |
| `gh` CLI | absent | GitHub API capped at 60 req/hr, so API-based probing was avoided in favour of git and public raw URLs |

### 7.2 Are the "before" commits still there?

All 432 IDoFT build points — a build point being a distinct
`(project URL, SHA Detected)` — were probed with a real depth-1, blob-filtered fetch of
the exact SHA. A repository being alive does not imply an old SHA is still reachable, so
`git ls-remote` was not sufficient; the fetch is the test.

**417 of 432 succeeded (96.5%).** All 273 repositories are alive.

Of the 15 failures, **12 are a single artefact**: `wildfly/wildfly` rows whose SHAs run
`…bb76f052` through `…bb76f063` in sequence. Those are fabricated or corrupted entries in
IDoFT, not lost commits. The genuine losses are three: `apache/rocketmq`,
`EsotericSoftware/kryo`, `FasterXML/jackson-databind`.

Script: `scripts/probe_shas.sh`.

### 7.3 The Windows long-path trap

Three of the first ten build attempts produced a checkout with no `pom.xml`. The cause
was not the dataset:

```
error: unable to create file plugins/affinity-group-processors/explicit-dedication/
       src/main/resources/META-INF/cloudstack/explicit-dedication/
       spring-explicit-dedication-context.xml: Filename too long
```

`core.longpaths` was unset. Re-running the identical checkout with
`core.longpaths=true` succeeded and produced both the root and module POMs.

This matters more than a one-line fix usually does, because **it fails as a missing file
rather than as an error**. A pipeline that does not check would treat those projects as
"no POM found" or, worse, would analyse a partial source tree and report results.

```
git config --global core.longpaths true
```

### 7.4 The JDK is the real constraint

ReproFlake declares the required JDK per subject, which turns a guess into a
measurement:

| JDK | Subjects | Categories affected |
| --- | ---: | --- |
| Java 8 | 465 | **all** NIO (125), **all** TD (36), 118 OD, 176 ID |
| Java 11 | 566 | 559 ID, 7 OD |
| Java 17 | 84 | ID only |

**549 of 1,115 — 49% — cannot be built on the only JDK installed here.** Every
timing-dependent and every non-idempotent-outcome subject needs Java 8. Installing JDK 8
and 17, with per-subject `JAVA_HOME` selection, is a prerequisite. ReproFlake solves it
with `Dockerfile8.id`, `Dockerfile11.id`, `Dockerfile17.id`.

Raw IDoFT declares no JDK at all, which is a second reason to prefer ReproFlake's
environment wherever the two overlap.

### 7.5 Do the builds work?

Ten random reachable build points were checked out and compiled with
`mvn -pl <module> -am -DskipTests compile` on JDK 11, with quality gates
(`enforcer`, `rat`, `checkstyle`, `license`, `javadoc`, `gpg`) skipped — those are
gates, not build steps, and leaving them on adds failures that say nothing about whether
the code compiles.

**9 of 10 succeeded** once `core.longpaths` was set: jsondoc, zerocode, runelite,
feign-vertx, XChange, nacos, dropwizard, cxf, cloudstack.

The single failure is informative and is **not** dependency rot:

```
[ERROR] Failed to execute goal org.codehaus.mojo:exec-maven-plugin:1.3.1:exec
        (convert-ms-winutils) on project hadoop-common: Command execution failed.
```

`apache/hadoop` needs a native Windows toolchain to build on Windows at all. That is a
*platform* failure — the same commit builds on Linux. Part of the corpus will need WSL,
a Linux machine, or ReproFlake's Docker images.

Caveats on the 9/10 figure, stated because it is easy to over-read: n is 10, and
`compile` is weaker than what the pipeline needs. A project that compiles may still fail
to *run* the flaky test, and JaCoCo needs the test to run. Treat it as encouraging, not
as a rate. The authoritative number comes from sweeping all 417 points with
`test-compile` or a real single-test run.

Script: `scripts/probe_builds.sh`.

### 7.6 JaCoCo and Spoon, concretely

**JaCoCo on ReproFlake: already solved.** Its artifact ships `jacocoagent.jar`,
`jacococli.jar`, `coverage_generator.sh`, `modify_pom_for_coverage.sh` and
`python-scripts/parse_coverage.py`. Porting `runAll.sh` from NOD-Test-Repair — which has
two known defects, anonymous classes silently dropped and a tree-sitter API removed in
0.22 — turned out to be unnecessary.

**JaCoCo elsewhere: conditional** on §7.4 and §7.5.

**Spoon: everywhere.** Spoon parses source and runs in noclasspath mode, so it needs a
checkout, not a build. It is available on all 417 reachable IDoFT build points
regardless of whether they compile.

That asymmetry should shape the feature design: **features needing only types and
dataflow are computable on the whole corpus; features needing coverage are computable
only where a build survives.** The coverage-dependent part should be additive rather
than load-bearing.

### 7.7 Getting ReproFlake

Its landing page points at an anonymous double-blind URL, but the data itself is not
anonymous: `test_config.csv` gives a direct **public Zenodo URL** per subject — 300 zips
across 3 Zenodo records. Sampled sizes: median 112 MB, mean 145 MB, max 393 MB, so
**roughly 42 GB** for the complete set. Zenodo rate-limits at about 133 requests per
window, so fetch selectively by category.

The anonymous API (`https://anonymous.4open.science/api/repo/ReproFlake-C9E6/`) serves
the small metadata files, which is how every ReproFlake number here was obtained without
downloading a single zip.

---

## 8. Cross-check against FlakeBench

121 of the 2,654 pairs are tests that already appear in `FlakeBench_dataset.csv`
(recorded per row in `in_flakebench` and `flakebench_existing_label`):

| FlakeBench's label | Count |
| --- | ---: |
| non-flaky | **88** |
| unordered collections | 32 |
| async wait | 1 |

**88 tests that IDoFT records as flaky with a merged developer repair are labelled
`non-flaky` in FlakeBench**, and 76 of those 88 are `OD-Vic`. Order-dependent victims
pass in isolation and fail only in an adverse order, so the most likely explanation is
that FlakeBench's non-flaky labels come from isolated reruns, which structurally cannot
observe order dependency.

This is not a curiosity. It is the same shortcut arXiv:2607.09345 identifies in
IDoFT-derived benchmarks — fix-commit or isolation-based non-flaky labels producing
near-duplicate pairs — reproduced inside our own benchmark. It has to be resolved before
FlakeBench is used as ground truth alongside this corpus.

---

## 9. Rebuilding `pairs.csv`

```bash
cd docs/investigation3/scripts

bash fetch_sources.sh data          # ~5 MB of metadata, no large artifacts
bash probe_shas.sh   data           # 432 shallow fetches, ~5 min at -P 12
bash probe_builds.sh data 10 4      # optional: sample build feasibility

python resolve_prs.py --out data/pr_meta.csv --jobs 6   # needs authenticated gh

FLAKYLENS_DATA=data python build_pairs.py
```

`resolve_prs.py` is optional in the sense that `build_pairs.py` runs without it — the
`merge_*` and `pr_*` columns are simply left empty. It is not optional in practice; §9.1
says why.

`build_pairs.py` writes `../pairs.csv` and prints the distribution summary used in
§5 and §6. It needs `FlakeBench/FlakeBench_dataset.csv` at the repository root for the
cross-check in §8; set `FLAKYLENS_REPO` if the repository is elsewhere.

Inputs, and what each contributes:

| File | From | Contributes |
| --- | --- | --- |
| `pr-data.csv` | IDoFT | 2,487 pairs, before SHA, PR link, category, status |
| `rf_idoft.csv`, `rf_jira.csv` | ReproFlake `research-data/` | flaky **and** fixed SHA, module, polluter |
| `rf_test_config.csv` | ReproFlake | required JDK, Zenodo URL, zip name |
| `async_wait_coming_from_flakysync.csv` | NOD-Test-Repair `data/` | 72 async subjects |
| `odrepair_patches.txt` | ODRepair `experiments/data/patches/` | 59 patch names = FQ test names |
| `sha_reach.tsv` | `probe_shas.sh` | `before_sha_reachable` per row |

### 9.1 Why the PR resolution step matters

A PR link is not a commit, and the two obvious ways to turn one into a commit are both
wrong.

`refs/pull/<n>/merge` is GitHub's synthetic test-merge, and **GitHub deletes it when the
PR closes**. Every merged PR therefore falls through to `refs/pull/<n>/head`, which is
the author's branch tip: not what landed if the maintainer squashed or rebased, and
missing anything that reached the base branch between the branch point and the merge.
All four smoke-test pairs took that fallback before this was noticed.

`gh` gives `merge_commit_sha` — the commit on the base branch — and its first parent,
which is the tree immediately before the repair. That parent is the better *before* side
for a paired design, because IDoFT's `SHA Detected` records where the flakiness was
observed and can predate the repair by years; a pair built on it differs by the repair
plus everything else that landed in between.

Trustworthiness of the parent is derived, not assumed. Two parents means a true merge and
the first parent is the base. One parent means squash *or* rebase, and those are not the
same: a squash puts one commit on the base, but a rebase replays every commit, so for a
multi-commit PR the last one's parent is another commit from that PR. `minimal_pair` is
`yes` only for a true merge or a single-commit squash.

The construction cross-validates. jsondoc PR 261 merges as `3b3907f4` with first parent
`16d42fd3`; ReproFlake independently packages that exact pair, its zip named
`jsondoc=jsondoc-core=16d42fd`. Neither ref guess produces it.

The same pass also records each PR's file footprint, which turns the E5 estimate into a
measurement: the "roughly one repair in six touches production code only" figure came
from a 90-PR hand sample, and `pr_touch` now carries `prod_only` / `test_only` / `both`
for every PR in the corpus. P1334 is a worked example — its only changed file is
`jsondoc-core/src/main/java/.../ApiAuthDoc.java`, so the test body is byte-identical on
both sides, which is exactly why that pair's before/after coverage delta is zero.

Cost: about 2,100 API calls for 709 PRs, roughly 11 minutes at `--jobs 6`. Anonymous
access is capped at 60 requests an hour, so this step is not feasible without `gh`.

---

**Verified reproducible.** Running the commands above into a clean directory
regenerated `pairs.csv` byte-for-byte identically to the shipped file
(1,485,217 bytes, same SHA-256). The only step not re-run in that check was
`probe_shas.sh`, whose output was carried over — it is 432 network fetches and its
result is recorded in §7.2.

---

## 10. Corrections made during this work

Recorded because two of them changed published counts, and because the failure modes are
the kind that recur.

| What went wrong | How it showed up | Resolution |
| --- | --- | --- |
| **ReproFlake net-new miscounted as 51** | arithmetic slip: subtracted 1,064 instead of 1,061 | correct figure is **54**; corpus total 2,655 → then 2,654 after the next row |
| **FlakeSync counted as 73 subjects** | line 72 of their CSV is a stray `#.` with one field | correct figure is **72** |
| **"All 273 repositories are dead"** | the repo list was written from Python on Windows, so every URL ended in `\r`; `git ls-remote` failed on all of them in 14 seconds | wrote list files with `newline='\n'`; all 273 are alive. A probe that fails 100% and finishes suspiciously fast is a bug in the probe |
| **Three build points reported `NO_POM`** | Windows `core.longpaths` unset — checkout silently incomplete | §7.3; all three build once the flag is set |
| **A fetch-by-SHA "failure" for cloudstack** | I retyped an 8-character abbreviated SHA from a display column; git needs the full 40 | operator error, not a data problem — but it is why `probe_shas.sh` always reads the SHA from the file |
| **`test_method.json` empty on 103 of 115 collected sides** | the runner matched IDoFT's parameterised selector `foo[ARRAY]` literally against Spoon method names, and no Java method is called that | strip the instance suffix before searching the model; `RUNNER.md` §7.1 |
| **The lexicon was scored on the wrong text** | the coverage/Spoon join carried only Spoon's fully-qualified pretty-print, which invents tokens (`conc.parallel` fired on 100% of sides against 0% on real source) and drops the ones on the declaration line (`conc.sync_kw` 2% against 91%) | the join now carries `raw_body` and `annotations`; measurement in `RUNNER.md` §7.1 |
| **Test class fields and initialiser blocks were never extracted** | `SpoonExtract` emitted methods and constructors only, so a `static final Map<..> CACHE = new HashMap<>()` and a `static { }` block were both invisible — the two commonest declarations of order-dependence | `SpoonExtract` emits field records, per-record annotations, and the superclass link; static blocks merge into one `<clinit>` record |

---

## 11. Collecting the evidence

`pairs.csv` names the pairs; it does not contain any evidence about them. The runner
that turns a pair into data — check out both sides, run the single flaky test under a
JaCoCo agent, model the sources with Spoon, join the two — is documented separately in
`RUNNER.md`, along with its four deliberate departures from `tdrepro/runAll.sh` in
NOD-Test-Repair and the bugs the first end-to-end runs exposed.

It has been smoke-tested on four pairs, not swept. Nothing in the corpus has been
processed in bulk.

---

## 12. Open questions

1. **The 88 FlakeBench `non-flaky` contradictions** (§8). Resolve before using FlakeBench
   as ground truth beside this corpus.
2. **The 30 ambiguous IDoFT `NOD` rows** need manual triage into async versus
   concurrency. It is a small enough number to do by hand, and both categories are too
   thin to absorb a guess.
3. **The pairing critique** (arXiv:2607.09345) argues that fix-commit pairing is itself a
   shortcut, because flaky and fixed versions are near-identical. Our reading was that
   pairing removes confounds; theirs is that it introduces one. Both are true. E0 needs a
   companion condition in which the model sees only one side of each pair. Unresolved,
   and it blocks E0.
4. **The corpus is 73.6% one category.** Nearly three quarters is NonDex-induced
   iteration order. Any whole-corpus number is really a statement about `HashMap`
   iteration, and should be reported per category.
5. **Time is four tests.** Nothing about clock-dependent flakiness can be claimed from
   this corpus. The 36 ReproFlake TD pairs are the only real timing supply.
6. **Async and concurrency is 138 pairs, 72 of them tool-generated**, and the 30
   developer-authored NOD pairs span only 6 projects. The honest framing is that the
   category has no developer-merged evidence base, not that it has a small one.
7. **A full 417-point build sweep** has not been run. Until it is, the true corpus size
   is unknown; 2,654 is an upper bound on what is analysable with coverage.
