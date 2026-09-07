# Before/After Fix Pairs — Maven, Deduplicated, Feasibility-Checked

Compiled 2026-09-06.

Three filters were applied to the earlier survey:

1. **Pairs only.** A source is listed only if it supplies an *after* side — a merged
   PR, a fixed commit, or a patch. Sources that supply detections, labels or tooling
   but no fix are moved to §4 with the reason.
2. **No duplicates.** Overlaps were computed, not assumed. Every count in §1 is *net
   new* after subtracting tests already carried by a source above it.
3. **Analysable.** Each source was checked for whether we can actually run JaCoCo and
   Spoon on it. Sources that fail this are removed or marked.

Counts marked **[verified]** were computed from the files or measured on this machine.

---

## 1. The deduplicated corpus

| # | Dataset | Net-new pairs | Build points | Repair by | Fix info | Categories | Spoon | JaCoCo |
| --- | --- | ---: | ---: | --- | --- | --- | :-: | :-: |
| 1 | **IDoFT** `pr-data.csv` | **2,487** | 432 (417 reachable) | developer | PR link + `SHA Detected` | ID 1,943 · OD\* 345 · NIO 145 · NOD 29 · TZD 4 · mixed 21 | yes | build it ourselves |
| 2 | **ReproFlake** | **54** | 291 | developer (Jira) | flaky SHA **+** fixed SHA, 4 code versions | TD 36 · ID 14 · OD 4 · unclassified 9 | yes | **pre-built** |
| 3 | **FlakeSync** | **72** | 72 | tool | generated barrier patch | async wait / concurrency | yes | build it ourselves |
| 4 | **ODRepair** | **41** | 41 | tool | `.patch` per test | OD | yes | build it ourselves |
| | **Total** | **2,654** | | 2,541 developer / 113 tool | | | | |

Nothing below the line duplicates anything above it. The dedup arithmetic is in §2.

**ReproFlake's second and larger contribution is not new pairs.** 1,058 of its 1,115
subjects are pairs we already have from IDoFT — but it ships them with a Docker image,
a pinned `.m2`, and a declared JDK. It therefore converts **43% of the IDoFT corpus
from "build it and hope" into "already builds"**, which matters more than the 54 rows
it adds. See §3.

### 1.1 Category totals

Both taxonomies are shown, because they are not the same taxonomy. IDoFT's labels are on
the left; the collapse into the five categories we have been working with is below.
Multi-label IDoFT rows (21 of them) are counted by their first label. **[verified]**

| Category | IDoFT | ReproFlake | FlakeSync | ODRepair | **Total** | dev / tool |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| **ID** — implementation-dependent (iteration order) | 1,951 | 2 | — | — | **1,953** | 1,953 / 0 |
| **OD** — test order dependency | 345 | 4 | — | 41 | **390** | 349 / 41 |
| **NIO** — non-idempotent-outcome | 154 | 3 | — | — | **157** | 157 / 0 |
| **NOD** — non-deterministic (async / concurrency) | 30 | — | 72 | — | **102** | 30 / 72 |
| **TD** — timing-dependent | — | 36 | — | — | **36** | 36 / 0 |
| **TZD** — time / timezone | 4 | — | — | — | **4** | 4 / 0 |
| **UD** — unknown / unclassified | 3 | 9 | — | — | **12** | 12 / 0 |
| **Total** | **2,487** | **54** | **72** | **41** | **2,654** | **2,541 / 113** |

Collapsed into our five categories:

| Our category | Maps from | Pairs | Share |
| --- | --- | ---: | ---: |
| unordered collections | ID | 1,953 | 73.6% |
| test order dependency | OD + NIO | 547 | 20.6% |
| async wait + concurrency | NOD + TD | 138 | 5.2% |
| time | TZD | 4 | 0.2% |
| unclassified | UD | 12 | 0.5% |

Three things this makes plain.

**The corpus is one category wearing a costume.** Nearly three quarters is
implementation-dependent iteration order, and almost all of that was induced by NonDex
rather than observed failing. Any headline number over the whole corpus is really a
number about `HashMap` iteration.

**Time is not a category here, it is four tests.** With 4 TZD pairs, nothing about
clock-dependent flakiness can be claimed. The 36 TD pairs from ReproFlake are the only
real timing supply, and they are timing-*dependent* in FlakeRake's sense, not
timezone.

**Async and concurrency is 138 pairs, 72 of which are tool-generated** — and the 30
developer-authored NOD pairs span only 6 projects (§3). The honest framing is that this
category has no developer-merged evidence base, not that it has a small one.


### 1.2 The pair table

Every pair is written out to **`pairs.csv`** in this directory — 2,654 rows, one per
pair. Columns:

| Group | Columns |
| --- | --- |
| identity | `pair_id`, `source`, `tier`, `repair_author` |
| location | `project_slug`, `project_url`, `module_path`, `test_class`, `test_method`, `fq_test` |
| the pair | `before_sha`, `before_sha_reachable`, `after_type` (`pr` / `fixed_sha` / `tool_patch`), `after_ref` |
| labels | `source_category`, `idoft_status`, `flakebench_label`, `flakebench_category`, `label_confidence`, `label_candidates`, `mapping_note` |
| feasibility | `build_env`, `java_version`, `reproflake_zip`, `reproflake_url`, `reproflake_fixed_sha`, `polluter` |
| cross-ref | `in_flakebench`, `flakebench_existing_label`, `notes` |

`flakebench_category` uses FlakeBench's own numbering (0 async wait, 1 concurrency,
2 time, 3 unordered collections, 4 test order dependency, 5 non-flaky).

Label confidence is recorded rather than hidden: **2,419 high, 193 medium, 30 ambiguous,
12 unknown.** The medium and ambiguous ones are exactly where the two taxonomies do not
line up:

- **NIO has no FlakeBench equivalent** (157 pairs, `medium`). A non-idempotent-outcome
  test pollutes *its own* state and fails on a second run in the same JVM. That is
  order dependency where the polluter is the victim, so it is mapped to
  `test order dependency`, but it is not the same phenomenon and should be reported
  separately.
- **IDoFT `NOD` does not separate async from concurrency** (30 pairs, `ambiguous`).
  These carry `label_candidates = async wait|concurrency` and an empty label; they need
  manual triage. FlakeSync's 72 are unambiguous because that dataset is async by
  construction.
- **ReproFlake `TD`** (36 pairs, `medium`) is timing-dependent in FlakeRake's
  sleep-injection sense, which is closer to `async wait` than to FlakeBench's `time`
  (clock and timezone). Mapped to `async wait`, candidates recorded.

### 1.3 Overlap with FlakeBench itself

121 of the 2,654 pairs are tests that already appear in `FlakeBench_dataset.csv`.
**[verified]** The breakdown is a problem, not a convenience:

| FlakeBench's label for it | Count |
| --- | ---: |
| non-flaky | **88** |
| unordered collections | 32 |
| async wait | 1 |

**88 tests that IDoFT records as flaky with a merged developer repair are labelled
`non-flaky` in FlakeBench.** 76 of those 88 are `OD-Vic` — order-dependent victims,
which pass in isolation and fail only in an adverse order. So the most likely
explanation is that FlakeBench's non-flaky label comes from isolated reruns, which
by construction cannot observe order dependency.

Either way it has to be resolved before FlakeBench is used as ground truth alongside
this corpus: 88 rows currently carry contradictory labels between the two datasets,
and 76 of them are contradictory in a way that is systematic rather than accidental.
This is the same shortcut C-IDoFT complains about (§5), reproduced inside our own
benchmark.


---

## 2. Dedup arithmetic

Each overlap was computed by matching on `(project slug, fully-qualified test name)`,
case-insensitive. **[verified]**

| Claimed | Overlap found | Net new | How |
| --- | --- | ---: | --- |
| IDoFT 2,487 | — (base) | 2,487 | |
| ReproFlake 1,115 | 1,049 of its 1,052 iDoFT-sourced rows are in the IDoFT pair set, as are 12 of its 63 Jira-sourced rows | **54** | 1,115 − 1,061 |
| FlakeSync 72 | 71 of 72 appear in IDoFT — but **0 have a merged developer fix**, so IDoFT supplies no *after* side for any of them | **72** | overlap is on detection, not on fix |
| ODRepair 59 | all 59 are in IDoFT; **18 already have a merged developer fix** and are therefore duplicate pairs | **41** | 59 − 18 |

Two of these deserve a note.

**FlakeSync's 71/72 overlap is not a duplication.** The tests are the same tests IDoFT
lists, but IDoFT has no accepted repair for a single one of them. The async and
concurrency arm of this work has exactly one supply, and it is tool-generated. That has
to be stated in any write-up rather than blended into a mixed corpus.

**ReproFlake matches IDoFT on the test but usually not on the commit.** Only 179 of the
1,049 overlapping rows share IDoFT's `SHA Detected`; for the rest ReproFlake picked a
different flaky commit — presumably one that builds. Where the two disagree, prefer
ReproFlake's, because theirs is the one with a working environment.

---

## 3. Feasibility — measured, not assumed

### 3.1 This machine

| Component | Version | Verdict |
| --- | --- | --- |
| JDK | Temurin 11.0.32 — **the only JDK installed** | **insufficient**, see 3.4 |
| Maven | 3.9.16 | fine |
| Git | 2.55.0.windows.5 | fine, but see 3.3 |
| `gh` CLI | not installed | GitHub API limited to 60 req/hr; avoid API-based probes |

### 3.2 Are the "before" commits still there?

All 432 IDoFT build points were probed with a real shallow fetch of the exact SHA. **[verified]**

- **417 of 432 fetch successfully (96.5%).**
- 15 fail. **12 of those 15 are a single artefact**: `wildfly/wildfly` rows whose SHAs
  run `…bb76f052` through `…bb76f063` in sequence — fabricated or corrupted entries in
  IDoFT, not real commits. The genuine losses are three: `apache/rocketmq`,
  `EsotericSoftware/kryo`, `FasterXML/jackson-databind`.

Commit availability is a non-problem. All 273 repositories are alive.

### 3.3 Windows long paths — a blocker with a one-line fix

Three of the first ten build attempts failed with `Filename too long` during checkout
(`apache/cloudstack`, `apache/hadoop`, `apache/cxf`). `core.longpaths` is **not set** on
this machine. Re-running the same checkout with `core.longpaths=true` succeeds. **[verified]**

```
git config --global core.longpaths true
```

Large Apache-family Java repositories exceed Windows' 260-character path limit as a
matter of course, so without this, roughly a third of the corpus silently produces an
incomplete working tree — and it fails as a *missing file*, not as an error, which is
the dangerous kind of failure. Set it before any bulk checkout.

### 3.4 The JDK problem is the real constraint

ReproFlake declares the required JDK per subject. Its distribution is decisive: **[verified]**

| JDK | Subjects | Which categories |
| --- | ---: | --- |
| Java 8 | **465** | all NIO (125), all TD (36), 118 OD, 176 ID |
| Java 11 | 566 | 559 ID, 7 OD |
| Java 17 | 84 | ID only |

**549 of 1,115 subjects — 49% — cannot be built on the JDK installed here.** Every
timing-dependent subject and every non-idempotent-outcome subject needs Java 8. Installing
JDK 8 and JDK 17 alongside 11 is a prerequisite, not an optimisation, and Maven toolchains
or per-subject `JAVA_HOME` switching has to be part of the pipeline. ReproFlake solves
this its own way, with `Dockerfile8.id`, `Dockerfile11.id` and `Dockerfile17.id`.

For raw IDoFT there is no declared JDK at all — we would have to infer it per build point
from the POM. That is a second reason to prefer ReproFlake's environment where the two
overlap.

### 3.5 Does a raw IDoFT build actually work?

Ten random reachable build points were checked out and compiled with
`mvn -pl <module> -am -DskipTests compile` on JDK 11. **[verified]**

**9 of 10 succeeded** once `core.longpaths` was set: `fabiomaffioletti/jsondoc`,
`authorjapps/zerocode`, `runelite/runelite`, `OpenFeign/feign-vertx`, `knowm/XChange`,
`alibaba/nacos`, `dropwizard/dropwizard`, plus `apache/cxf` and `apache/cloudstack` on
the long-path retry.

The single failure is instructive and is **not** dependency rot:

```
[ERROR] Failed to execute goal org.codehaus.mojo:exec-maven-plugin:1.3.1:exec
        (convert-ms-winutils) on project hadoop-common: Command execution failed.
```

`apache/hadoop` requires a native Windows toolchain (`winutils`, Visual Studio) to
build on Windows at all. This is a **platform** failure, not a corpus failure — the same
commit builds on Linux. Some fraction of the corpus will need WSL, a Linux box, or
ReproFlake's Docker images rather than this machine.

The sample is small and it is `compile`, not `test` — a successful compile does not
imply the flaky test runs, and JaCoCo needs the test to run. Treat 9/10 as
*encouraging*, not as a rate, and expect the platform issue above to recur. The honest
number will come from a full 417-point sweep, which is the first thing worth doing.

### 3.6 Can we actually run JaCoCo?

**ReproFlake: yes, and the pipeline already exists.** Its artifact ships
`jacocoagent.jar`, `jacococli.jar`, `coverage_generator.sh`,
`modify_pom_for_coverage.sh` and `python-scripts/parse_coverage.py`. **[verified]** We
do not have to port `runAll.sh` from NOD-Test-Repair; the coverage step is solved
inside the dataset we were already going to use.

**IDoFT, FlakeSync, ODRepair: conditionally.** Each needs a working `mvn test` for one
test at the before commit, which needs the right JDK (§3.4) and a build that survives
a decade of dependency drift. Feasible, unquantified.

### 3.7 Can we run Spoon?

**Everywhere.** Spoon parses source and runs in noclasspath mode, so it needs a
checkout, not a build. That makes Spoon available on all 417 reachable IDoFT build
points regardless of whether they compile, and on every ReproFlake and FlakeSync
subject.

This asymmetry should shape the plan: **tier-2 features that need only types and
dataflow are computable on the whole corpus; features that need coverage are computable
only where a build survives.** Design the feature set so the coverage-dependent part is
additive rather than load-bearing.

### 3.8 Getting ReproFlake

Not behind the anonymous URL after all. `test_config.csv` gives, per subject, a direct
**public Zenodo download**: 300 zips across 3 Zenodo records. Sampled sizes: median
112 MB, mean 145 MB, max 393 MB — **roughly 42 GB for the complete set**. **[verified]**
Zenodo rate-limits at ~133 requests per window, so fetch selectively by category rather
than mirroring everything.

The anonymous API (`https://anonymous.4open.science/api/repo/ReproFlake-C9E6/`) works
for browsing and for the small metadata files, which is how the numbers above were
obtained.

---

## 4. Removed, with reasons

| Source | Why removed |
| --- | --- |
| **FlakyFix** (562) | Not pairs — a *label layer* over IDoFT pairs we already have. Keep it: its 13 fix categories are the ready-made external validation of Constrain/Cut/Own. Zero new pairs. |
| **Flakify** | Same pairs as IDoFT, pre-packaged. Zero new pairs, and its published numbers carry a data-leakage defect. |
| **FlakyDoctor** (ID 540 / OD 297) | Reuses IDoFT and ODRepair. Zero new pairs. Its OD file's victim+polluter pairing is useful metadata, but ReproFlake supplies polluters for its 126 OD subjects too. |
| **iFixFlakies** | The 21 merged repairs are already in IDoFT. The remaining ~37 tool-only repairs are **not enumerable** — the repo contains the tool, not a dataset, and the OD pool it drew from is the same one ODRepair uses. |
| **NOD-Test-Repair** | No pairs at all. Retained only as tooling; and §3.6 makes even that redundant, since ReproFlake ships a working coverage pipeline while `runAll.sh` has two known defects (anonymous classes dropped, dead tree-sitter API). |
| **FlakeRake** | Reproduces timing failures; produces no repairs. |
| **C-IDoFT / FlakeCI** | No fixes — labels come from 500 reruns. Still required reading for §5, but it is not a corpus for this work. |
| IDoFT `gr-data.csv` (161), `py-data.csv` (74), **ShowFlakes**, **iPFlakies** | Not Maven. |

---

## 5. The objection that still has to be answered

**"How Far Are We from Detecting Flaky Tests? On the Limits of Code-Based Detection"**,
arXiv:2607.09345 (2026), builds C-IDoFT (54,468 tests, 57 projects, 1,319
developer-confirmed flaky, 53,149 non-flaky over 500 reruns) plus FlakeCI (86 flaky
end-to-end tests from CI logs).

It agrees with our thesis — under project-disjoint evaluation with rerun-confirmed
labels, Flakify and FlakyQ fall to F1 0.035–0.070 against a 0.054 baseline, while the
same code scores 0.746 under the published protocol.

But it names **fix-commit pairing itself as a shortcut**: because the flaky and fixed
versions of a test are nearly identical, a model can separate them on superficial
similarity without learning anything about flakiness. Our reading was that pairing
*removes* confounds; theirs is that it *introduces* one. Both are true — pairing removes
project identity and introduces near-duplication. The consequence is that E0's
prediction ("hazard tokens land at chance on pairs") is uninterpretable on its own, and
E0 needs a companion condition where the model sees only one side of each pair.
Resolve before building.

---

## 6. What to do first

1. `git config --global core.longpaths true`. One line, prevents silent corruption of
   about a third of the checkouts.
2. Install **JDK 8 and JDK 17** beside 11, and add per-subject `JAVA_HOME` selection to
   the pipeline. Without this, every TD and NIO subject is unbuildable.
3. Sweep all **417 reachable IDoFT build points** with `mvn -pl <module> -am -DskipTests
   test-compile`. The surviving fraction — not 2,487 — is the true corpus size, and it
   is the number most likely to change the plan.
4. Pull **ReproFlake's `test_config.csv` and `Reproducible_iDoFT_info.csv`** (done — in
   the scratchpad) and use them as the authoritative before/after SHA map wherever they
   overlap IDoFT.
5. Fetch ReproFlake zips **selectively**: the 36 TD and 125 NIO subjects first, since
   those are the categories with no other supply. Roughly 160 zips at ~145 MB is ~23 GB.
6. Only then decide whether the async arm is worth FlakeSync's 1.5 GB artifact, given
   that its 72 pairs are entirely tool-generated.
