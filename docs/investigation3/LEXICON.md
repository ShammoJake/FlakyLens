# The lexicons: what they are, where they came from, and what justifies each entry

Two vocabularies are in play, and they do opposite jobs. Conflating them is the
single easiest way to misread the results.

| | **hazard lexicon** | **control vocabulary** |
| --- | --- | --- |
| file | `docs/investigation2/lexicon.json` (v2.0) | `docs/investigation3/fix_vocabulary*.{json,csv}` |
| answers | "is a risky construct present?" | "did something close the choice?" |
| derived from | a published root-cause taxonomy plus mining of FlakeBench **flaky test bodies** | mining of **609 real repair diffs** |
| role in the study | **the object of criticism** — the thing we argue is insufficient | **an input to tier 2** — part of the proposed replacement |
| status | measured, and measured to fail as a classifier | derived, independent of the evaluation set, partial coverage |

The hazard lexicon is not our proposal. It is a faithful reconstruction of how
detectors are built, kept deliberately liberal so that its failure is a property
of the approach and not of a weak implementation.

---

## 1. The hazard lexicon (`lexicon.json` v2.0)

### 1.1 What it is

**38 regex families across the 5 FlakeBench categories.** The decision rule is
maximally liberal:

> flag a test if **any** family matches **anywhere** in **any** scope

Scopes: the test body, the test class fields, and the fixtures (`@Before`,
`@After`, `@Rule`, plus static and instance initialiser blocks), each following
the superclass chain. Comments and string/character literals are stripped before
matching, so a token inside a log message or javadoc does not count. Matching is
case-sensitive and each family counts at most once.

Applied by `extract_features_fb.py`, which scores each scope separately and then
ORs them.

### 1.2 Where it came from

Three sources, in decreasing strength:

1. **A published root-cause taxonomy.** The five categories are FlakeBench's,
   which descend from the standard empirical taxonomy of flaky-test root causes.
   The family names (`async.sleep`, `uc.hash_container`, `od.static_field`) name
   mechanisms from that taxonomy rather than inventions.
2. **Mining of FlakeBench test bodies**, by log-odds against the rest of the
   flaky pool with a floor of 5 projects and 6 tests. This produced three
   families: `time.now_call`, `uc.list_container`, `conc.thread_lifecycle`.
3. **Hand-written regexes** for the remaining families, shaped by the taxonomy.

### 1.3 What v2.0 already had to fix

v1.0 contained identifiers naming a specific product or project convention —
`MiniDFSCluster`, `MiniYARN`, `TestingServer`, `GenericTestUtils`, `TEST_ROOT`,
`HashMultiset`, `DaylightSaving`. Those **inflated results on a Hadoop-heavy
sample and would not transfer**, and were replaced with shape-based patterns.

That episode is worth keeping in view: it is direct evidence that mining a
lexicon from flaky test bodies picks up project idiom as readily as it picks up
flakiness.

### 1.4 The circularity problem

The lexicon was mined from FlakeBench and is evaluated on FlakeBench. Holding
tests out controls for memorisation, not for distribution.

There is a deeper problem than circularity, and it is the reason the fix mining
in §2 exists. **The lexicon is mined from the wrong artefact.** This study's
thesis is that *what a flaky test contains* is not *what makes it flaky*. A
vocabulary derived from flaky test **bodies** is derived from precisely the
correlation being argued to be spurious.

### 1.5 Every family, with its measured behaviour

Measured on the availability-matched subset: 164 flaky against 6,926 non-flaky.
`ratio` is flaky% ÷ non-flaky%; **1.00 means the family carries no information**.
`fix z` is the best log-odds score any construct of that family achieved in the
repair-diff mining (§2); `—` means the fix corpus is silent about it, which is
not the same as contradicting it.

| family | category | flaky | non-flaky | ratio | fix z |
| --- | --- | ---: | ---: | ---: | ---: |
| `conc.parallel` | concurrency | 1.8% | 0.1% | **12.67** | — |
| `async.latch_await` | async wait | 14.0% | 1.4% | **10.22** | — |
| `async.sleep` | async wait | 17.1% | 2.0% | **8.57** | — |
| `uc.listing` | unordered | 3.7% | 0.5% | **6.67** | — |
| `async.future_get` | async wait | 7.9% | 2.1% | 3.87 | — |
| `conc.executor` | concurrency | 11.0% | 2.9% | 3.74 | — |
| `time.wall_clock` | time | 8.5% | 2.3% | 3.65 | — |
| `conc.concurrent_coll` | concurrency | 3.0% | 1.0% | 3.06 | −0.25 |
| `od.shared_resource` | order dep. | 29.3% | 10.0% | 2.93 | — |
| `conc.interrupt` | concurrency | 10.4% | 4.0% | 2.62 | — |
| `async.explicit_wait` | async wait | 9.1% | 3.5% | 2.59 | — |
| `od.lifecycle` | order dep. | 50.0% | 22.4% | 2.23 | −0.49 |
| `conc.thread_obj` | concurrency | 15.2% | 7.2% | 2.13 | — |
| `conc.thread_lifecycle` | concurrency | 22.0% | 10.5% | 2.09 | — |
| `od.class_fixture` | order dep. | 27.4% | 13.4% | 2.05 | — |
| `time.now_call` | time | 1.8% | 0.9% | 1.95 | — |
| `conc.atomic` | concurrency | 7.3% | 3.8% | 1.92 | 0.33 |
| `time.duration` | time | 7.3% | 4.3% | 1.68 | — |
| `async.timeout_param` | async wait | 7.3% | 4.8% | 1.53 | — |
| `async.poll_loop` | async wait | 0.6% | 0.4% | 1.51 | — |
| `od.singleton_cache` | order dep. | 14.0% | 9.6% | 1.47 | 2.97 |
| `uc.index_access` | unordered | 12.8% | 8.8% | 1.46 | — |
| `od.global_write` | order dep. | 10.4% | 7.3% | 1.41 | — |
| `uc.hash_container` | unordered | 13.4% | 10.3% | 1.30 | **8.18** |
| `od.static_field` | order dep. | 19.5% | 15.2% | 1.28 | — |
| `uc.unordered_iter` | unordered | 5.5% | 4.5% | 1.23 | 1.76 |
| `uc.list_container` | unordered | 20.1% | 19.1% | **1.06** | 2.30 |
| `time.format` | time | 0.6% | 0.6% | 0.98 | — |
| `uc.sequence_assert` | unordered | 7.3% | 7.5% | **0.98** | 2.42 |
| `uc.map_set_type` | unordered | 15.9% | 16.3% | **0.97** | −0.07 |
| `async.callback` | async wait | 0.6% | 0.7% | 0.84 | — |
| `uc.to_sequence` | unordered | 7.3% | 8.9% | 0.82 | 2.57 |
| `time.date_obj` | time | 3.0% | 3.9% | 0.78 | — |
| `conc.sync_kw` | concurrency | 1.2% | 2.0% | 0.60 | — |
| `od.fs_state` | order dep. | 8.5% | 14.7% | **0.58** | 0.29 |
| `time.zone` | time | 1.2% | 2.8% | 0.43 | — |
| `time.timestamp` | time | 0.6% | 1.8% | 0.35 | — |
| `od.order_annot` | order dep. | 0.0% | 0.1% | 0.00 | — |

### 1.6 Reading the table

**The vocabulary is not uniformly bad — it is bimodal.**

Families naming the *mechanism* of flakiness discriminate well: a countdown latch
(10.2×), a sleep (8.6×), a directory listing (6.7×), an executor (3.7×). These
are constructs a program uses only when it is doing the risky thing.

Families naming the *data structure* carry almost nothing: `uc.map_set_type`
(`Map<`, `Set<`) at 0.97, `uc.list_container` at 1.06, `uc.sequence_assert` at
0.98. Every Java program uses maps and lists, so their presence separates
nothing.

**Three families run backwards.** `od.fs_state` fires on 14.7% of non-flaky
tests against 8.5% of flaky ones (0.58). `time.timestamp` is 0.35, `time.zone`
0.43. A test that touches the filesystem is, in this corpus, *less* likely to be
flaky.

**This is why the classifier fails, and how.** The any-family-match rule means
the uninformative families dominate the OR. The failure is not that hazard
tokens are meaningless; it is that a presence test cannot distinguish a hazard
that matters from a hazard that is merely there. Widening the scope makes it
worse, because more scope means more chances for a ubiquitous family to fire:
body alone gives 1.51× lift, body plus fixtures plus fields gives 1.33×.

### 1.7 Honest status of each family

| status | count | meaning |
| --- | ---: | --- |
| **corroborated** by repair evidence | 11 | some construct of the family appears in real fixes above the support floor |
| **untested** | 27 | the fix corpus is silent — see §2.4, it is 81.3% unordered collections with **zero** async or concurrency fixes |
| **contradicted** by measurement | 3 | ratio below 0.6 on FlakeBench: `od.fs_state`, `time.zone`, `time.timestamp` |

An untested family is not a discredited one. `async.sleep` scores no fix evidence
because there are no async fixes in the corpus, while measuring 8.57× on
FlakeBench — it is among the best families we have.

---

## 2. The control vocabulary (`fix_vocabulary*.{json,csv}`)

### 2.1 Why it is derived differently

A construct earns a place here if **developers actually added it to fix
flakiness**. That is causal evidence rather than correlational, and it comes from
a corpus independent of the evaluation set.

This vocabulary answers the question the hazard lexicon structurally cannot: not
"is there a risk?" but "was it closed?".

### 2.2 Method

- **609 distinct fix commits** across 250 projects, from the eligible pairs in
  `pairs_resolved.csv`, fetched through the GitHub API with no checkouts.
  609 fetched, 0 failures.
- **1,217 background commits** from the same projects, so project idiom cancels.
- Constructs extracted from `.java` hunks and scored by log-odds, with the same
  support floor as the original lexicon: **≥5 projects, ≥6 commits**.
- **hazard** = constructs in removed and context lines; **control** = constructs
  in lines the fix **adds**.
- 179 hazard and 125 control constructs pass the floor.

The log-odds implementation was verified independently before use: a balanced
construct scores ≈0, an enriched one tops the table, a twice-seen construct is
suppressed rather than promoted.

### 2.3 The control vocabulary

`indep` counts projects **not** in FlakeBench, so a high value means the entry
survives without the overlapping projects.

| construct | z | fix | background | projects | indep |
| --- | ---: | ---: | ---: | ---: | ---: |
| `type:LinkedHashMap` | 8.12 | 84 | 29 | 68 | 53 |
| `new:LinkedHashMap` | 7.86 | 80 | 29 | 66 | 51 |
| `call:sort` | 6.43 | 50 | 14 | 40 | 23 |
| `type:JSONAssert` | 5.81 | 32 | **0** | 17 | 13 |
| `static:JSONAssert.assertEquals` | 5.63 | 30 | **0** | 16 | 12 |
| `static:Arrays.sort` | 5.27 | 28 | 2 | 26 | 13 |
| `type:Comparator` | 4.80 | 33 | 16 | 27 | 17 |
| `static:Comparator.comparing` | 4.59 | 24 | 5 | 20 | 14 |
| `type:JSONException` | 4.39 | 20 | 2 | 11 | 7 |
| `annot:JsonPropertyOrder` | 4.11 | 16 | **0** | 13 | 9 |

These map onto the repair moves the study already names:

- **Constrain** — `LinkedHashMap`, `Arrays.sort`, `Comparator.comparing`: keep
  the container but fix the order.
- **Cut** — `JSONAssert.assertEquals`: compare JSON semantically so the assertion
  stops depending on order at all.
- **Own** — `@JsonPropertyOrder`: pin serialisation order at the type.

**Three entries have literally zero background occurrence** — `JSONAssert`,
`JSONAssert.assertEquals`, `@JsonPropertyOrder`. They appear only in repairs.
None is in the hazard lexicon, and none *could* be found by reading flaky test
bodies, because they exist only on the **after** side of a fix.

### 2.4 What this vocabulary does not cover

The fix corpus is not category-balanced:

| category | fix commits | share |
| --- | ---: | ---: |
| unordered collections | 495 | 81.3% |
| test order dependency | 103 | 16.9% |
| (unlabelled) | 9 | 1.5% |
| time | 2 | 0.3% |
| **async wait** | **0** | — |
| **concurrency** | **0** | — |

**The control vocabulary speaks to two of five categories.** Any claim about
async or concurrency control needs a different corpus — IDoFT's NOD rows, or
FlakeSync.

### 2.5 The hazard half of the mining is confounded, and is not used

Mining hazards from the same diffs failed. `type:Test` (8.08) and
`call:assertEquals` rank **above** `new:HashMap` (6.15), because a fix commit
touches a test by construction — 88.5% of fix commits versus 66.9% of background.
Matching the background on test-touching moved the numbers but did not remove the
effect.

The cause is structural: **added lines are the repair; removed and context lines
are mostly code the developer never touched.** Fix diffs are a good source of
control vocabulary and a poor source of hazard vocabulary. Hazard identification
stays with typed source analysis, where the receiver's resolved type decides
whether `.keySet()` is a hazard at all.

---

## 3. A category error the fix mining exposed

`uc.list_container` measures **1.06×** on FlakeBench — no information — yet is
corroborated by fix evidence at z 2.30. Both are correct, and the reconciliation
matters:

> **`ArrayList` appears in fixes as the *replacement* container. It is a control,
> not a hazard.** The lexicon files it under a hazard family.

The derived vocabulary shows the same construct on both sides of the ledger:
`type:ArrayList` scores 2.44 as a hazard and 0.48 as a control.

A lexicon mined from flaky test bodies cannot detect this class of error, because
it never observes the after side of a repair. This is the clearest single
argument for deriving vocabulary from fixes rather than from flaky code.

---

## 4. Consequences for the tier-2 analysis

`SliceAnalysis.java` currently carries hand-written `HAZARD`, `EXPOSURE` and
`CONTROL` sets. The mining changes what those should be:

- **`CONTROL` should be replaced** by the derived vocabulary. In particular
  `call:get` scores **0.96** — no support — and was included by assumption. It
  comes out. `LinkedHashMap`, `sort`, `Arrays.sort`, `Comparator.comparing`,
  `JSONAssert`, `@JsonPropertyOrder` go in.
- **`HAZARD` should stay typed and source-derived**, for the reason in §2.5.
- **`EXPOSURE` is still unvalidated.** Nothing in either corpus speaks to which
  operations reveal an unordered choice versus merely read the container. It
  remains the weakest link in the tier-2 design.

---

## 5. Limitations

1. **The hazard lexicon is circular** with respect to FlakeBench. The measured
   failure is nonetheless meaningful — a vocabulary tuned *on* the evaluation set
   still fails on it, which is a lower bound on the failure.
2. **46 of FlakeBench's 98 projects (47%) also appear in the pair corpus.** The
   `indep` column exists so a clean transfer test remains possible; a headline
   claim should report the 52 non-overlapping projects separately.
3. **The control vocabulary covers two of five categories**, with zero async and
   zero concurrency fixes.
4. **Construct extraction is lexical**, not type-resolved: `type:Map` is the
   token, not a resolved `java.util.Map`. Some entries will be conflations.
5. **No fix-level ground truth for reachability.** Whether a repair closed the
   path or merely changed the code around it is inferred from the diff, not
   verified by running anything.

---

## 6. Files

| path | content |
| --- | --- |
| `docs/investigation2/lexicon.json` | the hazard lexicon, v2.0, 38 families |
| `docs/investigation3/fix_vocabulary.json` | full derived vocabulary with per-construct statistics |
| `docs/investigation3/fix_vocabulary_matched.csv` | the same against a test-touching-matched background |
| `docs/investigation3/fix_vs_lexicon.json` | per-family corroboration, and constructs the lexicon misses |
| `docs/investigation3/FIX_MINING.md` | the mining method and results in full |
| `docs/investigation3/scripts/mine_fix_diffs.py` | `fetch` / `derive` / `compare` |
| `docs/investigation3/fb_features.csv` | the per-test measurements the ratios in §1.5 come from |
