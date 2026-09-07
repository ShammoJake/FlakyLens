# Program-Analysis Features for FlakyLens — Implementation Plan

Status: draft for team review, 2026-09-03.
Scope: extend FlakyLens (Rahman, Dutta, Shi — OOPSLA 2025) with three kinds of program-analysis
context — focal-method slices, call-graph reachability, and dataflow — and measure whether they
improve flaky-test category prediction on FlakeBench under the paper's project-disjoint protocol.

---

## 1. Thesis

FlakyLens classifies a test from its method body alone. The paper itself shows why that ceiling is
low: 25 of 37 Concurrency tests are mispredicted (mostly as Async Wait), 40 of 93 Order-Dependent
tests likewise, and injecting category-specific tokens into dead code drops macro-F1 by 18.37pp.
The model is matching surface tokens because surface tokens are all it is given.

Flakiness is usually caused by what the test *reaches*, not what it *says*: the focal method that
spawns a thread, the helper that reads `System.currentTimeMillis()`, the static field another test
mutated, the `HashMap` whose iteration order leaks into an assertion. None of that is visible in
the test body. This plan builds that context, validates it independently of any model, and then
tests three ways of feeding it to the classifier.

Expected outcome: a measurable gain on the categories the paper flags as weakest (Concurrency,
Order-Dependent, Async Wait), and a feature branch that is immune by construction to four of the
five perturbations in the paper's RQ4.

---

## 2. Facts that shape the plan

From the paper and the repository as it stands today.

**Data.** FlakeBench: 8,574 tests, 280 flaky across five categories (Async Wait 76, Concurrency
37, Time 33, Unordered Collections 41, Order-Dependent 93) and 8,294 non-flaky, from 98 projects
(the paper says 97; the dataset and the repo list both have 98, and every dataset `project`
maps to a repo row — one via a naming variant, `commercetools-project-sync`).
`FlakeBench/filtered_tests_with_owner_sha.csv` lists `owner/repo` plus one or more commit SHAs
per project, headerless; all 98 are GitHub repositories (175 distinct SHAs, 1 to 16 per
project). `FlakeBench/project_repos.csv` is the derived table with URLs. There is **no per-test commit mapping**: a project with six SHAs gives
no hint which SHA a given test came from. Test localization is therefore a real step, not a join.

**Protocol.** Four project-disjoint folds; each test set must hold at least four tests per
category. Paper: 50/20/30 train/valid/test, ≤30 epochs, patience 5 on validation loss. Code as
shipped: 25 test projects per fold, 40 epochs, patience 20 on validation macro-F1, and an
**unseeded** `random.shuffle` in `create_train_test_groups`, so folds differ every run. Phase 0
freezes one seeded split and every later experiment uses it.

**Model.** CodeBERT-base, 512-token truncation (25.3% of test-set tests are longer), CLS → 512 →
6, dropout 0.3, focal loss γ=2 with balanced class weights, AdamW lr 1e-5, wd 0.01. The chunking
loop in `BERT_Arch.forward` is vestigial — `fc1` expects exactly 768 inputs, so any input over 512
tokens would crash rather than chunk. Adding context as raw text needs a different input design,
not a longer sequence.

**Baseline numbers.** Macro-F1 65.79 (Async 58.37, Conc 35.92, Time 72.73, UC 73.63, OD 64.35,
Non-flaky 100.00). These are on the authors' split; our own re-run on the frozen folds is the
comparison point, not the paper's table.

**Compute.** Kaggle T4 (P100 is unusable: Kaggle's torch build dropped sm_60). One fold of
baseline training is ~2–3 h at 30 epochs with early stopping. GPU quota is 30 h/week, session
cap 12 h, output cap 20 GB, and "Save Version" re-executes the whole notebook from scratch.

---

## 3. What each analysis should reveal, per category

| Category | Mechanism in the code | Reachability signal (call graph) | Dataflow signal |
|---|---|---|---|
| Async Wait | Test waits a fixed time for work it never synchronizes with | Reaches thread/executor/future creation **and** `Thread.sleep` / `wait` / timed `await` somewhere in the slice; sleep often in test, spawn in focal method | Value produced on another thread (Future, callback, shared field) read after a sleep with no join/await in between |
| Concurrency | Shared mutable state under real thread interleaving | Reaches `synchronized`, `java.util.concurrent` locks/atomics, thread spawn without join; focal method is itself concurrent | Field written inside a `Runnable`/lambda and read on the test thread; two spawned tasks touch the same field |
| Time | Assertion depends on wall clock, timezone, or elapsed time | Reaches `currentTimeMillis`, `nanoTime`, `Instant.now`, `LocalDate.now`, `Clock`, `TimeZone.getDefault`, `ZoneId.systemDefault` | A clock-derived value flows into an assertion argument or a comparison that gates an assertion |
| Unordered Collections | Iteration order of `HashMap`/`HashSet` assumed stable | Reaches `keySet`/`values`/`entrySet`/`iterator`/`toString`/`toArray` on hash-based collections, reflection `getDeclaredMethods`, `Set` streams | A hash-collection value flows to an ordered consumer (`List`, string concat, `assertEquals` on a sequence, index access) |
| Order-Dependent | State left behind by an earlier test | Reaches static non-final field writes, `System.setProperty`, singletons, file/DB side effects, static caches; class lacks `@After*` reset | Static state read but not written in this test; static write with no corresponding teardown |
| Non-flaky | None of the above | No sink family reached, or only at depth 0 in obviously benign form | No source-to-assertion flow |

The important distinction throughout is **depth**. Depth 0 (the test body) is what the current
model already sees. The new information is at depth ≥1. Every feature is recorded per depth so
ablations can show whether gains come from genuinely new context or from re-encoding tokens the
model already had.

---

## 4. Design decisions

Each has a recommendation. The team should confirm or overrule before Phase 1 starts.

**D1. Analysis engine: source-level (Spoon) first, bytecode (WALA/Soot) only where cheap.**
Building 98 projects at years-old commits (Maven resolution, JDK mismatches, private
repositories) is the single biggest schedule risk in this plan. Spoon with a no-classpath symbol
resolver parses without building, gives an AST, a class-hierarchy call graph (over-approximate on
virtual dispatch), and enough structure for intra-procedural dataflow. Precision loss is
acceptable and measurable. Bytecode analysis is an optional upgrade for whichever projects build
cleanly, reported as a separate row.

**D2. Representation: structured feature vector first, slice text second, both together third.**
The feature vector (~65 dims) is cheap, has no token budget, is interpretable, and can be
evaluated with a gradient-boosted-tree baseline in minutes before any GPU time is spent. Slice
text is where the larger gain should be, but it collides with the 512-token limit and needs a
two-tower encoder. Sequencing this way means the first model result arrives in week 5 rather than
week 7 and de-risks the text work.

**D3. Folds: keep the repository's 25-projects-per-fold construction, seed it, freeze it.**
Switching to the paper's exact 50/20/30 is not reproducible from the artifact (the shuffle was
unseeded). What matters is that every variant, baseline included, is trained and tested on
identical folds. Publish the folds as a versioned Kaggle Dataset and never regenerate them.

**D4. Tests whose source cannot be located: keep them, mark them, report both ways.**
Dropping them changes the benchmark and makes the baseline non-comparable. Unresolved tests get
an all-zero feature vector plus an explicit `resolved=0` indicator and an empty slice. Results
are reported on all 8,574 tests (primary) and on the resolved subset (secondary).

**D5. Where extraction runs: a lab machine, not Kaggle.**
Cloning 98 repositories at multiple SHAs and running Spoon over Hadoop- or Neo4j-sized trees is
disk- and RAM-bound (Kaggle CPU sessions: 4 cores, 30 GB RAM, 12 h). Run extraction once on the
lab machine, upload the outputs (a few hundred MB) as a Kaggle Dataset, and use Kaggle only for
what it is good at: GPU training and light CPU evaluation. If no lab machine is available,
Phase 1–4 can run in a Kaggle CPU notebook, one project batch per session, at roughly 3× the
wall-clock.

**D6. Early-stopping criterion: validation macro-F1, as the code does, not validation loss.**
Documented as a deviation from the paper's text. It is the criterion the shipped weights were
selected with, and macro-F1 is the metric being optimized.

---

## 5. Pipeline

Phases are sequential; each ends at a gate. Validation is described inside each phase and
collected again as its own phase (5.6) because it must exist as runnable code, not as a
one-off check.

### 5.0 Freeze the baseline

1. Seed `create_train_test_groups`; generate the four folds once; write
   `folds/fold_{1..4}/{train,valid,test}.csv` with test ids only.
2. Re-run unmodified FlakyLens on the frozen folds, 3 seeds. This is **M0**, the number every
   variant is compared against.
3. Record per-test predictions and probabilities for every fold and seed — later significance
   tests are paired per test.

Gate: M0 macro-F1 within a few points of 65.79 on our folds. If it is far off, the fold
construction differs materially from the paper's and that must be understood before continuing.

### 5.1 Source corpus and test localization

Inputs: `FlakeBench_dataset.csv` (`id, project, test_name, full_code, label, category`),
`filtered_tests_with_owner_sha.csv` (`owner/repo, sha;sha;…`).

1. Use `FlakeBench/project_repos.csv` (project → GitHub URL → SHAs); the one naming variant is already mapped.
2. For each repository and each listed SHA: `git fetch --depth 1 origin <sha>`, check out into
   `corpus/<owner>__<repo>/<sha>/`. Keep only `**/src/test/**` and `**/src/main/**` trees plus
   build files; delete the rest to control disk.
3. Localize every test: `test_name` is `SimpleClassName.methodName`. Search test trees at each
   SHA for a class with that simple name declaring that method; confirm by comparing the method
   body to `full_code` after whitespace normalization. Record `(id, sha, file_path, start_line,
   end_line, match_kind)` where `match_kind ∈ {exact, normalized, signature_only, unresolved}`.
4. When a test matches at several SHAs with identical bodies, pick the earliest listed SHA
   (deterministic) and record all candidates.

Validation:
- Resolution rate overall and per project; per-category resolution rate (a category resolving
  much worse than others would bias every downstream result).
- Manual audit of 30 `signature_only` matches to decide whether they count as resolved.
- Duplicate check: distinct ids resolving to the same `(sha, file, line)`.

Gate: ≥90% of tests resolved with `exact` or `normalized`; no flaky category below 85%. Below
that, fix the localizer before spending effort on analysis.

### 5.2 Focal-method slices

Definition: the production methods a test exercises, ranked by how likely they are to be the
method under test.

1. Parse the test class and its project with Spoon (no-classpath mode). Resolve every
   invocation in the test body to a declaration when the resolver can; otherwise fall back to
   name-and-arity matching over an index of all method declarations in the project's main tree.
2. Exclude assertion and framework calls (JUnit, TestNG, Hamcrest, AssertJ, Mockito, JDK,
   logging) via an allow/deny list checked into the repo.
3. Score candidates using the Methods2Test heuristics: same-simple-name-minus-`Test` class,
   invoked immediately before an assertion, argument of an assertion, most-invoked production
   method. Rank; keep the top `F` (default 3) as focal methods.
4. Expand each focal method transitively to depth `k` (default 2) inside the project; stop at
   external code. Record every method with `(depth, signature, file, lines, source)`.
5. Emit the slice as text in a fixed order — focal methods first, then depth-2 callees — with a
   per-method token count so the training code can budget deterministically.

Validation:
- Fixture suite: ~20 hand-written miniature projects (one test class, a few production classes)
  with known focal methods; the extractor must recover them. This is the regression net for all
  later changes.
- Manual audit: 100 random resolved tests (stratified: 60 flaky, 40 non-flaky), two annotators,
  record whether the top-1 and top-3 focal methods are the real methods under test. Target
  top-3 precision ≥80%.
- Distribution stats: tests with zero focal methods (mock-only or pure-JUnit tests), median
  slice size in tokens, share of slices exceeding 512 tokens.

Gate: fixture suite green; audit precision ≥80%; zero-focal rate explained (and not concentrated
in one flaky category).

### 5.3 Call-graph reachability

1. Build a class-hierarchy call graph per `(project, sha)` from the Spoon model: nodes are
   methods, edges are invocations, virtual calls edge to every overriding implementation in the
   project. Cache the graph per SHA; it is reused by every test at that SHA.
2. From each test method, breadth-first traversal up to depth `D` (default 5), recording the
   minimum depth at which each method is reached and each external API is called.
3. Prune unreachable statements before recording anything: bodies under `while(false)`,
   `if(false)`, and constant-false conditions are skipped. This is what makes the branch immune
   to the paper's deadcode perturbation, and it must be a deliberate, tested behaviour.
4. Match reached calls, field accesses, and modifiers against **sink families** kept in a YAML
   file in the repo:

   | Family | Members (non-exhaustive) |
   |---|---|
   | `SLEEP_WAIT` | `Thread.sleep`, `Object.wait`, `TimeUnit.sleep`, `CountDownLatch.await`, `Future.get(timeout)`, `Thread.join(timeout)`, Awaitility |
   | `THREAD_SPAWN` | `new Thread`, `Thread.start`, `ExecutorService.submit/execute`, `CompletableFuture.*Async`, `Timer.schedule`, `ScheduledExecutorService` |
   | `SYNC` | `synchronized`, `ReentrantLock`, `volatile`, `Atomic*`, `ConcurrentHashMap` |
   | `CLOCK` | `System.currentTimeMillis`, `System.nanoTime`, `new Date()`, `Calendar.getInstance`, `*.now()`, `Clock.*`, `TimeZone.getDefault`, `ZoneId.systemDefault` |
   | `RANDOM` | `java.util.Random`, `Math.random`, `UUID.randomUUID`, `ThreadLocalRandom`, `SecureRandom` |
   | `UNORDERED` | `HashMap`/`HashSet`/`Hashtable` construction; `keySet`/`values`/`entrySet`/`iterator`/`toString`/`toArray` on them; `getDeclaredMethods`/`getDeclaredFields`; streams over `Set` |
   | `STATIC_STATE` | read/write of static non-final fields, `getInstance()` singletons, `System.setProperty`/`getProperty`, `Locale.setDefault`, static caches |
   | `IO_FS` | `java.io.File`, `java.nio.file.Files`, temp files, streams on paths |
   | `NETWORK` | `Socket`, `ServerSocket`, `HttpURLConnection`, `URL.openConnection`, `InetAddress`, port binding |
   | `EXTERNAL` | JDBC, `DataSource`, embedded databases, process spawning |
   | `ORDER_ANNOT` | `@FixMethodOrder`, `@Order`, static `@BeforeClass`/`@BeforeAll` setup with no matching teardown |

5. Encode per family: `hit_d0`, `hit_d1`, `hit_d2plus`, `min_depth` (capped at D+1 for
   "unreached"), `count`. Add structural features: reachable-method count, max depth reached,
   external-call count, fan-out of the test, count of `synchronized` blocks reached, count of
   static fields written. About 65 dimensions.

Validation:
- Fixture suite extended with one project per family whose test reaches the family only at
  depth 2 — proves the graph, the depth accounting, and the pruning.
- Separation table: for each family and depth, hit rate per category versus non-flaky. Expected
  before modelling: `SLEEP_WAIT` and `THREAD_SPAWN` far higher for Async Wait and Concurrency,
  `CLOCK` for Time, `UNORDERED` for UC, `STATIC_STATE` for OD. If a family shows no separation
  at any depth, either the family list or the graph is wrong; find out which before training.
- Precision spot-check: 50 reached-sink instances, verify by reading the code that the call is
  real and on a real path.
- Leakage check: no feature may encode project identity (no name, no repository-level counts).
  Any scaler is fit on the fold's training split only.

Gate: fixtures green; the separation table shows the predicted pattern for at least four of the
five flaky categories.

### 5.4 Dataflow

Intra-procedural def-use on the test method and each focal method, with summary-based
propagation across the focal-method boundary (parameters in, return value out; no heap model).
Built on the Spoon AST — assignments, local declarations, method arguments, returns, lambda
captures, field reads and writes.

Facts to compute:

| Fact | Meaning |
|---|---|
| `DF_SRC_TO_ASSERT[family]` | A value derived from a `CLOCK`, `RANDOM`, `UNORDERED`, `THREAD_SPAWN` (e.g. `Future.get`) or `IO_FS` source reaches an assertion argument or a comparison that guards an assertion |
| `DF_UNORDERED_TO_ORDERED` | A hash-collection value flows into a `List`, an index access, string concatenation, or a sequence assertion |
| `DF_STATIC_WRITE_NO_RESET` | Test or focal method writes a static field; the test class has no `@After*` method that writes it back |
| `DF_STATIC_READ_UNWRITTEN` | Test reads static mutable state it never initializes |
| `DF_CROSS_THREAD_RW` | A field or captured local is written inside a `Runnable`/lambda body and read on the test thread with no `join`/`await`/`get` between start and read |
| `DF_SLEEP_BEFORE_READ` | A `SLEEP_WAIT` call precedes a read of cross-thread state on the same path |
| `DF_TIMEOUT_MAGNITUDE` | Bucketed literal milliseconds passed to sleep/await (0–100, 100–1000, >1000) |

Each fact becomes a Boolean feature; the two path-shaped facts also record path length. Every
fact is additionally rendered as one compact text line (for example
`DF: HashMap<String,Integer> counts -> counts.keySet() -> assertEquals(arg 1)`) so the text-fusion
models can see the same evidence in prose.

Validation:
- Fixture suite: at least two positive and two negative snippets per fact.
- Real-data check: each fact's positive rate per category. `DF_SRC_TO_ASSERT[CLOCK]` should be
  concentrated in Time, `DF_UNORDERED_TO_ORDERED` in UC, `DF_STATIC_*` in OD.
- Manual audit of 40 positives across facts for true-positive rate; target ≥75% (dataflow
  without a heap model will over-approximate, and that is acceptable if it is known).

Gate: fixtures green; no fact fires on more than 40% of non-flaky tests (a fact that common
carries no information and inflates the text rendering).

### 5.5 Dataset assembly and versioning

1. Join features and slices to the benchmark by `id`. Every row keeps `resolved`, `sha`,
   `file_path`, and the extractor version.
2. Files: `features.parquet` (one row per test), `slices.jsonl` (per test: ordered methods
   with depth, signature, source, token count), `dataflow.jsonl` (facts plus rendered lines),
   `coverage.json` (resolution and fixture results), `provenance.json` (Spoon version, sink
   YAML hash, git commit of the extractor).
3. Publish as Kaggle Dataset `flakebench-pa-features`, versioned; the folds dataset is
   separate and never changes.

Gate: a notebook can load folds + features + benchmark and reconstruct every fold's train,
valid, and test tensors without network access.

### 5.6 Validation as a deliverable

Everything above is gathered into `src/pa/validate.py` and a CPU notebook that runs it end to
end and writes one report: resolution rates, fixture pass/fail, the separation table, the
dataflow positive-rate table, audit spreadsheets with annotator agreement. This report is
attached to each dataset version. An extractor change that does not re-run it is not merged.

### 5.7 Models and training

All variants share the frozen folds, the paper's hyperparameters (lr 1e-5, wd 0.01, dropout 0.3,
focal γ=2, balanced weights, batch 8, ≤30 epochs, patience 5 on validation macro-F1), and three
seeds. CodeBERT is reloaded fresh per fold.

| Variant | Input | Architecture | Purpose |
|---|---|---|---|
| **M0** | test body | current FlakyLens | baseline on frozen folds |
| **GBT** | feature vector only | gradient-boosted trees | cheapest possible signal check; interpretable; runs on CPU in minutes |
| **M1** late fusion | test body + feature vector | CodeBERT CLS (768) ⊕ MLP(65→64) → 832 → 512 → 6 | does structured context help without touching the token budget |
| **M2** two-tower | test body ‖ slice text | shared CodeBERT encodes each separately; CLS ⊕ CLS (1536) → 512 → 6 | does focal-method source help; avoids truncating the test to make room |
| **M3** full | test body ‖ (slice + dataflow lines) + feature vector | M2 towers ⊕ M1 feature MLP → 1600 → 512 → 6 | the proposed system |
| **M4** stretch | single long sequence | long-context code encoder (e.g. UniXcoder 1024 or a ModernBERT-class model) | is two-tower fusion needed, or does a longer window suffice |

Ablations, run only on the best of M1–M3: callee-only features (drop all depth-0 dimensions);
drop-one sink family; slice depth `k` ∈ {1, 2}; resolved-only subset; slice text without
dataflow lines.

Implementation notes:
- Slice budget for M2/M3: the slice tower truncates at 512 tokens in the fixed order from 5.2,
  so focal methods survive and deep callees are what gets cut.
- Feature scaler fit on the training split of each fold; feature MLP has its own dropout.
- Two-tower doubles activation memory. On a T4, batch 8 at 2 × 512 tokens fits in fp32 for
  CodeBERT-base; if not, gradient accumulation of 2 × 4, never a smaller effective batch.
- Remove the per-epoch evaluation pass over the full training set (it roughly doubles epoch
  cost and only feeds a TensorBoard scalar); log train loss from the training pass instead.

### 5.8 Evaluation and analysis

- Primary: 6-class macro-F1 on the frozen folds, mean ± std over seeds, alongside flaky-only
  5-class macro-F1 and per-class F1. Non-flaky F1 is ~100 for everything and should not mask
  movement in the classes that matter.
- Significance: paired bootstrap over test ids (1,000 resamples) for ΔF1 against M0; McNemar on
  per-test correctness. Small classes (33 Time tests) make single-run deltas unreliable.
- Confusion analysis: Conc→Async and OD→Async counts before and after; these are the paper's
  named failure modes.
- Robustness: rerun the paper's RQ4 protocol (deadcode, print, variable rename, multi-line
  comment, single-line comment, using its most-important tokens) on every variant. Expected:
  the feature branch is unchanged under deadcode, comments, and renames by construction (pruned,
  not parsed, type-based); M1/M3 should degrade less than M0. Report the ΔF1 table in the
  paper's format.
- Interpretability: Integrated Gradients on the text towers as in RQ3; permutation importance
  and SHAP on the feature branch; a qualitative table of tests that flip from wrong to right
  with the reached sink that explains the flip.
- Cost: extraction seconds per test, inference latency per test, so the added cost is stated.

---

## 6. Kaggle organization

**Recommendation: separate notebooks per stage, chained through versioned Kaggle Datasets and
Models. Do not merge.**

Reasons, in order of weight:

1. **Save Version re-executes the entire notebook.** A merged notebook would re-clone
   repositories and re-run extraction on every training commit. That alone rules it out.
2. Extraction is CPU, RAM, and disk bound and needs no GPU; training is GPU bound. Kaggle bills
   GPU quota by session, so extraction in a GPU notebook burns the 30 h/week budget on Spoon.
3. A fold of two-tower training is 4–5 h. Four folds by three seeds by four variants does not
   fit in any 12 h session; it has to be many small runs, each pinned to one input version.
4. Reproducibility: each notebook version records exactly which dataset version it consumed.
5. Failure isolation: a Spoon crash on one repository must not take down a 5 h training run.

Notebook chain:

| Notebook | Accelerator | Inputs | Outputs | Notes |
|---|---|---|---|---|
| `00-freeze-folds` | CPU | benchmark CSV | Dataset `flakebench-folds` v1 | run once, never regenerate |
| `01-localize-and-extract` | CPU (prefer lab machine; see D5) | benchmark, owner/sha CSV, internet | Dataset `flakebench-pa-features` vN | one project batch per session if on Kaggle |
| `02-validate-features` | CPU | features vN, folds | validation report attached to vN | must be green before any training on vN |
| `03-train` | GPU T4 | folds, features vN, repo at pinned commit | Kaggle Model `flakylens-pa` (one variation per variant/fold/seed), predictions CSV | one fold per run; parameters in a single CONFIG cell |
| `04-evaluate` | CPU | all prediction CSVs | tables, confusion matrices, bootstrap CIs, perturbation ΔF1 | cheap; rerun freely |
| `05-attribution` | GPU T4 | one chosen model, features | IG and SHAP outputs | optional, last |

Conventions:
- Notebooks are thin. They clone the repository at a pinned commit and call `src/pa/*` and
  `src/models/*`; no analysis or model logic lives in cells. The existing
  `notebooks/flakebench_kaggle_train.ipynb` becomes `03-train` once the variants exist.
- `03-train` takes `VARIANT`, `FOLD`, `SEED`, `FEATURES_VERSION` from one CONFIG cell. Runs are
  launched by editing that cell and saving a version, or from a laptop with `kaggle kernels push`
  and a per-run metadata file — the latter is worth setting up once 20+ runs are queued.
- After every training run: delete the duplicate `EarlyStopping` checkpoint (only
  `*_project_group_N.pt` is loaded by evaluation), then Quick Save before the session ends.
- Java on Kaggle: check `java -version` in the first cell of `01`; the image normally carries an
  OpenJDK for PySpark, otherwise `apt-get install -y openjdk-17-jdk-headless` with internet on.

GPU budget: M0, M1 ≈ 2.5 h per fold; M2, M3 ≈ 5 h per fold. One seed of all four variants over
four folds is ~60 h — two weeks of quota. Plan: one seed for every variant first, then the
remaining seeds only for M0 and the best fused variant.

---

## 7. Repository layout

```
src/pa/
  localize_tests.py        # Phase 5.1
  extractor/               # Java (Spoon) project; builds one fat jar
    src/main/java/.../FocalMethods.java
    src/main/java/.../CallGraph.java
    src/main/java/.../Dataflow.java
    src/main/java/.../DeadCodePruner.java
    src/test/resources/fixtures/   # Phase 5.2-5.4 fixture projects
  sink_families.yaml       # Phase 5.3
  build_features.py        # extractor JSON -> features.parquet, slices.jsonl, dataflow.jsonl
  validate.py              # Phase 5.6 report
src/models/
  fused_model.py           # M1, M2, M3 heads
  datasets.py              # fold loading, slice budgeting, feature scaling
  train.py                 # replaces the per-epoch train-set evaluation pass
  evaluate.py              # bootstrap, McNemar, confusion, perturbation
notebooks/
  00-freeze-folds.ipynb ... 05-attribution.ipynb
docs/
  plan-program-analysis-features.md   # this file
```

---

## 8. Schedule with gates

| Week | Work | Gate to pass |
|---|---|---|
| 1 | 5.0 freeze folds, M0 on frozen folds; 5.1 clone and localize | ≥90% resolved; M0 near paper's number |
| 2–3 | 5.2 focal methods, 5.3 call graph, fixtures, separation table | fixtures green; separation shows expected pattern in ≥4 categories |
| 4 | 5.4 dataflow, fixtures, positive-rate table | fixtures green; no fact fires on >40% of non-flaky |
| 5 | 5.5 dataset v1; GBT and M1 training | GBT or M1 beats M0 on macro-F1 with bootstrap CI excluding zero — if not, diagnose here, before spending GPU on text fusion |
| 6–7 | M2 and M3, four folds, one seed | M3 ≥ M1 |
| 8 | remaining seeds, ablations, RQ4 rerun, attribution, write-up | — |

The week-5 gate is the important one. If structured context alone shows nothing, the likely
causes are localization errors or a wrong sink list, and both are cheaper to fix than a model.

---

## 9. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Test localization below 90% (multiple SHAs, moved files, renamed methods) | Every downstream number biased toward resolved projects | Measure in week 1; fuzzy body matching; report resolved-subset results separately (D4) |
| Spoon no-classpath resolution fails on generics/overloads | Missing or wrong call edges | Name-and-arity fallback index; precision spot-check; accept over-approximation |
| Repository sizes (Hadoop, Neo4j) exhaust RAM or disk | Extraction stalls | Keep only `src/main` and `src/test`; per-module processing; lab machine (D5) |
| Features leak project identity | Inflated results | Per-project folds already isolate; no repository-level features; scalers fit on train only; check per-project feature separability |
| Minority classes (33–41 tests) make deltas noisy | False conclusions either way | Three seeds, paired bootstrap, McNemar; report per-class CIs |
| Slice text truncation drops the informative callee | M2/M3 underperform for the wrong reason | Fixed ordering with focal methods first; report share of truncated slices; ablate `k` |
| Two-tower memory on T4 | OOM | Gradient accumulation; fp16 autocast as a last resort with a check that F1 is unchanged on one fold |
| Kaggle quota (30 h/week) | Schedule slips | Sequence per section 6; run M0/M1 seeds while M2/M3 code is being written |

---

## 10. Decisions needed from the team

1. Confirm D1 (Spoon-first) or commit to building projects for bytecode analysis.
2. Confirm D3 (keep the code's fold construction, seeded) or re-implement the paper's 50/20/30.
3. Confirm D5 (extraction on a lab machine) and name the machine.
4. Choose the M4 long-context encoder, or drop M4 from scope.
