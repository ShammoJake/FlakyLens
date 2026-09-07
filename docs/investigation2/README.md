# Step 2 — token-proxy check

Report (formatted): https://claude.ai/code/artifact/c1464ad7-f1d5-4486-a166-b9d10985394a

Does the class context around a test carry category signal the test body lacks,
and how much is it worth? Measured on 80 flaky tests across five projects with
a fixed token lexicon, no model training required.

Step 1 (`docs/investigation/`) read 27 Hadoop tests by hand and found the
deciding evidence outside the body in all 17 misses. This step tests the same
claim mechanically, on a larger sample, with a lexicon written before the
sources were inspected.

## Headline

Adding class fields and fixture bodies to the test body raises a zero-training
token classifier from 22.5% to 57.5% accuracy on the 5-way flaky category task,
and its macro-F1 from 0.21 to 0.44. A trained linear model gains +0.138 macro-F1
with a bootstrap CI that excludes zero, and beats a label-permutation null at
p = 0.007.

**Every point of that gain is order dependency.** Its recall roughly doubles.
No other category improves, and two get worse.

| Slice fed to the classifier | Accuracy | Macro-F1 | Trained macro-F1 |
|---|---|---|---|
| body only | 22.5% | 0.211 | 0.253 |
| body + fields + fixtures | **57.5%** | **0.442** | **0.391** |
| body + full context, merged | 38.8% | 0.326 | 0.382 |
| majority class | 57.5% | 0.146 | — |
| FlakyLens, shipped | 51.2% | 0.368 | — |

Lexicon v2.0, 38 families. Accuracy and macro-F1 are the argmax proxy with ties
broken at random over 2,000 draws, and fit nothing. Trained macro-F1 is a
scikit-learn class-balanced multinomial logistic regression under
StratifiedShuffleSplit, 50 train / 30 test, 40 splits. Trained deltas against
body-only, scipy BCa bootstrap:

| Configuration | Delta | 95% CI |
|---|---|---|
| body + fields + fixtures | +0.138 | [+0.109, +0.164] |
| body + full context, merged | +0.129 | [+0.102, +0.157] |

The difference between those two rows is that "full context" pools four slices
into a single group of five features, while "fields + fixtures" keeps three
separate groups. See **Every slice tested on its own** below: once each slice is
given its own group, siblings turn out to help on their own (+0.068) and simply
be redundant with fields and fixtures, not noisy.

## Where the true category actually appears

Share of the 80 tests whose true category has at least one lexicon family
present in that slice.

| Slice | All | Model wrong | Model right |
|---|---|---|---|
| body | 48% | 51% | 44% |
| fields | 31% | **51%** | **12%** |
| fixtures | 51% | 56% | 46% |
| siblings | 75% | 74% | 76% |
| helpers | 15% | 23% | 7% |
| callees, depth 1 | 19% | **33%** | **5%** |
| context (fields, fixtures, siblings, helpers) | 92% | 95% | 90% |

The fields row is the finding. Static field declarations carry the true
category's vocabulary four times more often for the tests the model gets wrong
than for the tests it gets right. Siblings carry it for three quarters of
everything, so this particular measure does not separate them, yet they still
classify well on their own. Coverage asymmetry and classification value are not
the same thing; see **Every slice tested on its own** below.

For 39 of the 80 tests (49%) the true category is absent from the body and
present in the context. For 3 (4%) it is absent from both, which is the
lexicon's own ceiling on this sample. Version 2.0 lifted context coverage from
86% to 92%, so the ceiling fell from 8 tests to 3.

## Per-category recall

| Category | n | Body | + fields | + fixtures | + siblings | + fields + fixtures |
|---|---|---|---|---|---|---|
| test order dependency | 46 | 15% | 41% | 70% | 28% | **76%** |
| async wait | 18 | 39% | 33% | 28% | 33% | 33% |
| concurrency | 10 | 10% | 10% | 20% | 0% | 20% |
| time | 4 | 50% | 50% | 50% | 50% | 50% |
| unordered collections | 2 | 50% | 50% | 50% | 0% | 50% |

Order dependency is the only category that gains, and it gains most from fields
and fixtures alone. Async wait and concurrency lose, because context tokens
outvote the body's own vocabulary. This says context should be added as
*separate features*, not concatenated into one bag.

## Binary task: order dependency vs everything else

Cleaner than the 5-way task given the class skew, and here full context wins.

| Slice | AUC | Best accuracy |
|---|---|---|
| body only | 0.723 | 72.5% |
| body + fields | 0.697 | 68.8% |
| body + fixtures | **0.834** | 77.5% |
| body + siblings | 0.824 | **78.8%** |
| body + helpers | 0.728 | 73.8% |

Fixtures and siblings are close on this measure, 0.834 and 0.824, and both far
ahead of the body alone. Fields score below the body here, which is the clearest
sign that coverage asymmetry and ranking power are different things.

## Effect on the tests FlakyLens got wrong

Of the 39 misclassified tests, the body-only proxy already gets 8 right. Adding
fields and fixtures recovers 13 more and breaks **none**. Fields alone recover 7,
fixtures alone recover 12.

The 13 include every case found by hand in investigation 1: all five `TestDFSIO`
tests, all three `TestPathData` tests, and `TestDelegationTokenForProxyUser`.

```
recovered by fields + fixtures
  TestDFSIO.testRead / testWrite / testReadRandom /
             testReadSkip / testReadBackward                   OD, model said time
  TestPathData.testCwdContents / testQualifiedUriContents /
             testUnqualifiedUriContents                        OD, model said UC
  TestDelegationTokenForProxyUser.testDelegationTokenWithRealUser  OD, said conc
  ProvisioningServiceTest.testCancelDeprovision                 OD, model said async
  MetadataHttpHandlerTestRun.testSystemMetadataRetrieval        async, said time
  AntiAffinityNamespaceGroupTest.testBrokerSelectionForAnt...   conc, said async

broken: none
```

## A worked example

`scripts/trace_one.py <Class.method>` prints every stage for one test.
`TestPathData.testCwdContents`, ground truth order dependency, predicted
unordered collections:

```
slice       lines   what fires
body            9   uc: listing      -> getDirectoryContents
fields          4   od: fs_state     -> TEST_ROOT
fixtures       22   od: global_write -> setDefaultUri
                    od: fs_state     -> mkdirs(, createNewFile, .delete(
                    od: lifecycle    -> cleanup, .close(
helpers         5   uc: to_sequence  -> StringBuilder

score (distinct families present)
slice         async     conc     time       uc       od
body              0        0        0        1        0
fields            0        0        0        0        1
fixtures          0        0        0        0        3
helpers           0        0        0        1        0

body only               uc=1 od=0   -> unordered collections   wrong
body + fields/fixtures  uc=1 od=4   -> order dependency        correct
body + full context     uc=3 od=3   -> tie, resolved wrong
```

The body contains exactly one signal, `getDirectoryContents`, which is a real
unordered-collections cue and is why the model answers as it does. The fixture
holds four order-dependency families and never appears in the model's input.

The helper is the cautionary half. `sortedString` builds its result with a
`StringBuilder`, which fires an unordered-collections family and pushes back
toward the wrong answer. Investigation 1 read the same helper by hand and
concluded the opposite, from its `Arrays.sort` call, which the lexicon has no
family for. That gap is the honest limit of a regex proxy: adding the helper
turns a correct answer into a tie.

A second example shows why the body has to come from the benchmark.
`TestDFSIO.testRead` is one of the 22 tests whose pinned commit holds a
different version. What the model saw:

```java
long tStart = System.currentTimeMillis();
bench.readTest(fs);
long execTime = System.currentTimeMillis() - tStart;
```

What the pinned commit holds:

```java
long execTime = bench.readTest(fs);
```

The body the model consumed contains a real wall-clock idiom twice, which is why
it answers "time". Measuring against the pinned commit's body would have hidden
that. With the correct body the proxy scores time=1, od=1 on the body alone, a
tie; adding fields and fixtures makes it od=5 and the answer flips to correct.

## Method

The lexicon (`lexicon.json`, version 1.0) defines 6 to 8 regex token families
per category, drawn from the standard empirical taxonomy of flaky-test root
causes rather than from inspecting these tests. It is applied identically to
every slice, so any difference between body and context is a property of the
code, not of the lexicon.

**The body comes from FlakeBench, not from the clone.** The two disagree for 37
of the 80 tests, because the commit pinned in
`filtered_tests_with_owner_sha.csv` often holds a different version of the test
than the one the benchmark shipped. Similarity between the benchmark's copy and
the pinned commit's copy:

| Similarity | Tests |
|---|---|
| identical | 28 |
| 0.95 to 1.00, cosmetic | 15 |
| 0.80 to 0.95, small edits | 15 |
| below 0.80, a different version | 22 |

The benchmark's copy is what the model consumed and what the label describes, so
it is the honest body. Context has no second source and comes from the clone, so
context is measured at the pinned commit while the body is measured at whatever
commit the benchmark used. Where a class was restructured between the two, the
context is approximate.

Each located test class is split into body, fields, fixtures, siblings, helpers
actually called from the body, and context (the last four combined). Comments
and string literals are blanked by a single-pass scanner before matching, so a
`/*` inside a string cannot swallow the file and a `//` inside a URL cannot
truncate a line.

Scoring uses distinct families present, not raw counts, because context is much
longer than a body and raw counts would reward length rather than signal.





## Lexicon v2.0

Version 1.0 named identifiers belonging to particular products or project
conventions, which inflated results on a Hadoop-heavy sample and would not
transfer. Version 2.0 replaces them with shape-based patterns and adds three
families mined from FlakeBench itself.

**Removed as project-specific**

| Family | Removed | Replaced with |
|---|---|---|
| `od.shared_resource` | MiniDFSCluster, MiniYARN, MiniCluster, EmbeddedServer, TestingServer | `Mini[A-Z]*`, `Embedded[A-Z]*`, `InMemory[A-Z]*`, `shared[A-Z]*` |
| `od.fs_state` | TEST_ROOT | `TEST_?ROOT`, `TMP_?DIR`, `TempDir` |
| `async.explicit_wait` | GenericTestUtils.waitFor | `waitFor*`, `awaitAtMost` |
| `uc.hash_container` | HashMultiset | `Multiset`, `LinkedHashMap` |
| `time.zone` | DaylightSaving | `withZone` |

**Added, mined from held-out FlakeBench tests** (`scripts/mine_lexicon.py`).
Tokens are ranked by log-odds against the rest of the flaky pool and must appear
in at least 5 distinct projects and 6 tests. **The 80 tests used in the study are
excluded from the mining**, so the vocabulary is discovered on data the
evaluation never sees.

| Family | Tokens | Evidence |
|---|---|---|
| `time.now_call` | `.now()` | log-odds +2.87, 6 projects, the strongest time token in the data |
| `uc.list_container` | ArrayList, LinkedList, `List<`, Lists.newArrayList | asList +2.11, ArrayList +1.13, List +0.73 |
| `conc.thread_lifecycle` | `.start()`, `.join(`, InterruptedException, isAlive, currentThread | start +1.58, InterruptedException +1.18 |

**What the mining also showed, which is a finding in itself.** Order dependency
yields **no tokens at all** that clear the thresholds. Every other category has
body-level vocabulary that generalises across projects; order dependency has
none. That is independent confirmation, from the benchmark's own data, that its
evidence does not live in the test body.

The mining also shows why concurrency is confused with async wait: the only
concurrency tokens that generalise are `start`, `Thread` and
`InterruptedException`, all of which appear just as often in async-wait tests.

**Effect of the change.** Removing the project-specific identifiers made the
result *stronger*, not weaker: the fields-plus-fixtures gain rose from +0.096 to
+0.115 at the old 40/40 split. Context coverage of the true category rose from
86% to 92%.

## Split protocol

The earlier protocol used `RepeatedStratifiedKFold`, which caps `n_splits` at
the size of the smallest class. Unordered collections has 2 examples, so it
silently ran 2-fold: 40 train, 40 test.

`StratifiedShuffleSplit` takes any ratio. Measured across ratios:

| Train / test | Unordered collections in test set | Usable |
|---|---|---|
| 40 / 40 | always 1 | yes |
| **50 / 30** | **always 1** | **yes, and the most training data** |
| 60 / 20 | sometimes 0 | no |
| 64 / 16 | always 0 | no |

At 60/20 and above, unordered collections drops out of the test set and macro-F1
would silently be computed over four classes rather than five. 50/30 is
therefore the largest training set that keeps the task intact, and is what is
now reported.

## Every slice tested on its own

The earlier version of this study only ever bundled siblings and helpers inside
a single merged "full context" slice, and compared that against fields and
fixtures kept as separate feature groups. That comparison confounded *which*
slices are used with *how many* feature groups exist. Each slice is now tested
alone, and each combination keeps every slice as its own group of five features.

| Configuration | Features | Argmax acc. | Trained macro-F1 | Delta | 95% CI |
|---|---|---|---|---|---|
| body only | 5 | 22.5% | 0.253 | — | — |
| body + fields | 10 | 36.2% | 0.358 | +0.106 | [+0.080, +0.133] |
| body + fixtures | 10 | 52.5% | **0.397** | **+0.145** | [+0.117, +0.171] |
| body + siblings | 10 | 26.2% | 0.338 | +0.085 | [+0.060, +0.107] |
| body + helpers | 10 | 25.0% | 0.267 | +0.014 | [−0.013, +0.037] |
| body + callees | 10 | 11.2% | 0.273 | +0.020 | [−0.001, +0.042] |
| **body + fields + fixtures** | 15 | **57.5%** | 0.391 | +0.138 | [+0.109, +0.164] |
| body + fields + fixtures + siblings | 20 | 41.2% | 0.397 | +0.145 | [+0.111, +0.177] |
| all six slices, separate | 30 | 37.5% | 0.347 | +0.095 | [+0.065, +0.129] |
| body + context, merged | 10 | 38.8% | 0.382 | +0.129 | [+0.102, +0.157] |

### Corrections this forces

**Siblings are not noise.** On their own they are worth +0.068 macro-F1 with an
interval that excludes zero, and they give the best binary order-dependency AUC
of any single slice, 0.795 against 0.662 for the body alone. The earlier claim
that they "add noise" was an artefact of the confounded comparison.

**Siblings are redundant, not harmful.** Added on top of fields and fixtures the
score moves from +0.096 to +0.091, which is a wash. They carry much the same
order-dependency evidence that the class fixture already carries, so there is
little left to add.

**Fixtures are the strongest single slice, not fields.** Fixtures alone reach
50.0% argmax accuracy and 61% order-dependency recall; fields alone reach 37.5%
and 43%. Fields still show the largest coverage asymmetry between the model's
misses and hits, so the two measure different things and both are worth keeping.

**Callees are the only slice that fails outright.** +0.012 with an interval
crossing zero, and a binary AUC of 0.568 which is close to chance. The negative
result for depth-1 callees survives this correction unchanged.

**More slices is not better at n = 80.** All six slices kept separate is 30
features on 80 examples and scores +0.049, well below the 15-feature
configuration. That is a dimensionality effect, not a statement about signal.

### Per-category recall, by slice

| Category | n | body | fields | fixtures | siblings | helpers | callees | fields + fixtures |
|---|---|---|---|---|---|---|---|---|
| test order dependency | 46 | 20% | 43% | 61% | 37% | 24% | 13% | **70%** |
| async wait | 18 | 56% | 39% | 44% | 39% | 50% | 50% | 44% |
| concurrency | 10 | 10% | 0% | 10% | 0% | 10% | 10% | 10% |
| time | 4 | 50% | 50% | 50% | 50% | 25% | 50% | 50% |
| unordered collections | 2 | 50% | 50% | 50% | 50% | 50% | 50% | 50% |

## Production callees at depth 1: a negative result

Investigation 1 said four of its seventeen misses needed the production class
under test. Adding that slice was the fourth extraction target. It is now
implemented, and **it does not help.**

`fetch_callees.py` resolves calls type-directed rather than by name. Local
declarations and class fields give a variable-to-type map, so `cache.put(...)`
after `PeerCache cache = new PeerCache(...)` resolves to `PeerCache.put` and not
to every `put` in the repository. A call is kept only when its receiver type is
a class under `src/main/java` in the same project, which drops JUnit, Mockito
and the JDK without needing a deny list. 78 of the 80 tests resolve at least one
callee, median 2.

Every measure gets slightly worse when callees are added:

| Measure | fields + fixtures | + callees |
|---|---|---|
| argmax accuracy | 55.0% | 51.2% |
| trained macro-F1 | 0.389 | 0.384 |
| binary OD, AUC | 0.697 | 0.672 |
| order-dependency recall | 70% | 65% |
| errors recovered | 12 | 11 |

**But the signal is there.** The coverage table shows the callees slice carrying
the true category for 33% of the tests the model gets wrong against 5% of the
ones it gets right. That 28-point gap is the second largest of any slice, behind
only fields. Concurrency recall is the one category that improves, 10% to 20%,
which is exactly what investigation 1 predicted since concurrency evidence lives
in production code.

So the slice carries evidence and the bag-of-families scoring cannot use it. Two
reasons, and both are fixable.

**Depth 1 is the wrong depth.** `TestPeerCache` was investigation 1's flagship
production-code case. At depth 1 it resolves `PeerCache.put`, `size` and
`close`, which between them contain one `synchronized` keyword. The background
`Daemon` and the `Thread.sleep(expiryPeriod)` loop live in `startExpiryDaemon`
and `run`, which `put` calls. They are at **depth 2**. The plan document
specifies depth 2 by default, and this is the measurement that says why.

**Callee bodies are long and generic.** A production method drags in vocabulary
from every category, so pouring it into one bag dilutes the body's own signal.
The same failure mode as sibling tests, one level worse.

### What this means for the plan

Do not drop the callee slice. Change how it is used:

1. Expand to depth 2, as the plan already specifies. Depth 1 provably misses the
   evidence in the one case investigation 1 examined most closely.
2. Keep callees a separate feature group, never concatenated. Their coverage
   asymmetry, 33% against 5%, says a model that can weight them independently
   should benefit where a bag cannot.
3. Expect the gain to be concurrency, not order dependency. Order dependency is
   a class-level property and is already served by fields and fixtures.

## Statistics and tooling

The analysis runs on scikit-learn 1.9.0 and scipy 1.18.1, both pinned in the
project's `requirements.txt`. A numpy implementation of the same classifier is
kept in `evaluate.py` as a fallback and as a cross-check.

**The two implementations disagree, which is why the switch mattered.**

| Configuration | numpy | scikit-learn | difference |
|---|---|---|---|
| body only | 0.244 | 0.261 | +0.017 |
| body + fields + fixtures | 0.392 | 0.351 | −0.041 |
| body + full context | 0.305 | 0.360 | +0.055 |

Differences of up to 0.055 macro-F1 on the same data mean the hand-rolled
gradient-descent model was not reliable at the third decimal. Everything
reported now comes from scikit-learn.

**Label-permutation null.** More informative than a confidence interval at
n = 80, because it asks directly whether the model beats chance on this data.
Labels are shuffled 300 times and the cross-validation rerun on each.

| Configuration | Observed | Null mean | p |
|---|---|---|---|
| body only | 0.305 | 0.158 | 0.007 |
| body + fields + fixtures | 0.423 | 0.181 | ≤ 0.003 |
| body + full context | 0.339 | 0.178 | ≤ 0.003 |

The two smallest values are at the resolution floor of 300 permutations: no
shuffle beat the observed score.

**The bootstrap interval is optimistic.** It resamples the 40 fold scores, and
those come from the same 80 tests, so they are correlated. Resampling the tests
themselves would widen it. The permutation test does not depend on it.

**One number is fitted in-sample.** In the binary task, "best accuracy at
margin > t" picks the threshold by sweeping the same 80 tests. The AUC beside
it is threshold-free, and the Mann-Whitney p-values now reported alongside are
the ones to quote.

**Folds collapse to 2, not 5.** `n_splits` is capped by the smallest class, and
unordered collections has 2 examples. Each fit therefore trains on about 40
tests and predicts the other 40. scikit-learn makes this explicit where the
hand-rolled version hid it.

## Sample

| Project | Flaky tests | Located | Analysed | Model wrong |
|---|---|---|---|---|
| apache/hadoop | 33 | 27 | 27 | 17 |
| wildfly/wildfly | 42 | 24 | 24 | 7 |
| apache/pulsar | 22 | 16 | 16 | 5 |
| cdapio/cdap | 11 | 9 | 9 | 7 |
| neo4j/neo4j | 8 | 4 | 4 | 3 |
| **total** | **116** | **80** | **80** | **39** |

## Caveats

- **Class skew.** Order dependency is 46 of 80. Unordered collections has 2 and
  time has 4, so their per-category numbers are noise. The binary
  order-dependency task is the more trustworthy summary.
- **The gain is one category.** Nothing here shows context helps async wait,
  concurrency, time, or unordered collections. On this sample it hurts the first
  two. Treat "context helps" as "context helps order dependency".
- **A lexicon is not an encoder.** A 36-family regex bag is a floor, not a
  prediction of what a fine-tuned transformer would gain. It shows the signal is
  present and machine-readable; it does not size the gain for the real model.
- **Localisation is lossy.** 36 of 116 tests could not be located. Wildfly rows
  name the test as `<commit sha>.<method>` with no class, so 24 were recovered by
  searching a checked-out tree for a unique `@Test` declaration; 11 more matched
  several classes and were dropped as ambiguous, and 7 were not found at all.
- **Proxy beating the model is not a result.** The body-plus-fixtures proxy
  scores 53.7% against FlakyLens's 51.2% on these 80 tests, but this subset
  over-represents projects where localisation succeeded and is order-dependency
  heavy. It is not a like-for-like comparison.

## What this changes about the extraction plan

Step 1 ranked the extraction targets by how many misses they reach. This step
adds how much each is worth to a classifier, and one correction.

1. **Static fields and fixture bodies pay first and pay most.** They alone
   deliver the entire measured gain. Cheapest to extract, no resolution needed.
2. **Keep slices as separate feature groups.** Concatenating siblings and
   helpers into one bag costs accuracy on async and concurrency. Step 1's
   ordering stands; the packaging changes.
3. **Sibling tests are redundant with fixtures, not useless.** Alone they are
   worth +0.068 and give the best single-slice order-dependency AUC, 0.795. On
   top of fields and fixtures they add nothing, because the fixture already
   carries the same evidence. A targeted feature, *which siblings write the
   static fields this test reads*, is still more likely to pay than their raw
   text.

## Files

| Path | Contents |
|---|---|
| `FlakyLens_token_proxy.pptx` | 12-slide deck: method, worked example, results, statistics, charts |
| `report.html` | The formatted report, same content as this file |
| `lexicon.json` | The token lexicon, version 1.0 |
| `token_counts.csv` | 80 tests x 6 slices x 5 categories, family counts and presence |
| `results.txt` | Full evaluation output |
| `sources/index.csv` | Test to file to commit mapping, with resolution notes |
| `sources/<project>/` | The located test classes, verbatim upstream |
| `sources/_callees/` | Resolved depth-1 production method bodies, one file per test |
| `scripts/fetch_sources.py` | Blobless partial clone, locate test classes by name |
| `scripts/resolve_bare_names.py` | Recover tests whose benchmark row has no class name |
| `scripts/fetch_callees.py` | Resolve and download depth-1 production callees |
| `scripts/slice_and_count.py` | Split into slices, count lexicon families |
| `scripts/mine_lexicon.py` | Ranks candidate tokens on FlakeBench tests held out from the study |
| `scripts/evaluate.py` | Tests A to E; writes nothing, prints everything |
| `scripts/trace_one.py` | Walks one named test through every stage of the pipeline |
| `scripts/deck.py` | Regenerates the pptx |

Reproduce with:

```
python docs/investigation2/scripts/slice_and_count.py
python docs/investigation2/scripts/evaluate.py
```

Re-fetching sources needs network and a mirror directory; set `FLAKY_MIRRORS`
to control where clones land. `resolve_bare_names.py` needs a real working tree,
which a blobless clone provides via `git sparse-checkout` (see the wildfly note
above).
