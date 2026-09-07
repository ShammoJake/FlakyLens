# Investigation 3 — Do Flakiness Signals Survive a Repair?

**Status:** plan, not yet executed.
**Companion note:** [`../what_makes_a_test_flaky.md`](../what_makes_a_test_flaky.md) — the conceptual
argument this plan tests.

---

## 1. The claim under test

Existing flaky-test predictors learn the **hazard**, not the **defect**.

A hazard is a source of nondeterminism: a thread, a clock, a hash container, a leftover
file. A defect is a *path* from that hazard to an assertion with no adequate control on it.
A repair removes the path; it almost never removes the hazard. So a representation built
from the tokens present in a test cannot distinguish a flaky test from its repaired form,
because the token content barely moves.

If that is right, then a model that scores well on ordinary flaky-test benchmarks should
score at **chance** when asked to tell a flaky test from its own repaired version. That is a
sharp, falsifiable prediction, and the whole investigation is built to test it.

### Why the paired design is the right instrument

The unit of analysis is a **pair**: the same test, same class, same project, same author,
same style, before and after a merged repair. Everything except the defect is held constant
by construction. There is no project confound, no class imbalance, no style confound, and
no need for a matched negative sample. The task reduces to a single clean question:

> Given the two versions of one test, which one is the flaky one?

Chance is exactly 50%. That number needs no calibration and no argument.

---

## 2. Corpus

### 2.1 Primary source — IDoFT

`TestingResearchIllinois/idoft`, file `pr-data.csv`.

| Quantity | Count |
| --- | --- |
| Rows total | 8,075 |
| Projects | 481 |
| Rows with a repair and a PR link (`Accepted`, `DeveloperFixed`, `InspiredAFix`) | 2,487 |
| Distinct repair PRs | 709 |

The `SHA Detected` column gives the pre-repair commit, so the "before" side is checkoutable
without commit archaeology. The "after" side is the merge commit of the PR.

Repairs by category:

| Category | Repairs | Maps to |
| --- | --- | --- |
| ID (implementation-dependent) | 1,943 | unordered collections |
| OD-Vic / OD / OD-Brit | ~342 | test order dependency |
| NIO (non-idempotent-outcome) | 145 | — |
| NOD (non-deterministic) | 29 | async wait / concurrency |

### 2.2 The coverage gap, and how to close it

IDoFT is dominated by order-of-iteration and order-of-execution flakiness. It supplies
almost nothing for **async wait, concurrency and time**, which are 146 of FlakeBench's 280
flaky tests. Three supplementary sources:

- **NOD-Test-Repair** (`shanto-Rahman/NOD-Test-Repair`) — a repair tool targeting exactly
  the non-deterministic category IDoFT lacks. Its benchmark carries before/after versions by
  construction.
- **FlakeSync** — concurrency repairs, before/after by construction.
- **Repair commits mined from history.** `git log --grep` for flaky-fix commits over the 98
  FlakeBench projects, filtered to commits that touch a test file and mention flakiness.
  Noisier, but it is the only route to time-category pairs and it costs nothing.

### 2.3 Quality tiers

- **Tier A — `DeveloperFixed` (340 rows).** Repairs authored by the project's own
  maintainers. Cleanest ground truth; the primary result should be reported on this tier.
- **Tier B — `Accepted` (2,303 rows).** Researcher-authored PRs that maintainers merged. Far
  larger, but carries a real risk described in §7.
- **Tier C — mined commits.** Used only to extend category coverage; reported separately.

### 2.4 Filtering rules

A PR enters the corpus only if:

1. it is reachable and its diff parses;
2. it touches at most 10 Java files (excludes sweeping refactors that happen to include a
   repair);
3. it touches either the named test, its class, or a production method reachable from it;
4. the named test exists at both commits with a resolvable body.

Record for each surviving pair whether the **test body changed at all**. In a 90-PR sample,
10 repairs touched production code only and 6 touched both — so roughly one repair in six
leaves the test byte-identical. That subset is treated separately in E5 and is the single
most decisive slice in the whole plan.

### 2.5 Fix-move labelling

Every pair is hand-labelled with which of the three moves the repair used:

| Move | Definition | Signature edit |
| --- | --- | --- |
| **Constrain** | the free choice is no longer free | `sort`, `join`, seed, injected `Clock`, lock |
| **Cut** | the assertion no longer depends on the choice | `containsAll`, set equality, removal of an index |
| **Own** | the choice is removed from scope | fresh fixture, reset in teardown, unique temp dir |

This labelling is a deliverable in its own right — it turns the theory in
`what_makes_a_test_flaky.md` into a categorical variable that the experiments can condition
on. Label at least 100 pairs, two raters, report Cohen's κ.

**Target corpus size:** 300–500 usable pairs, of which ≥150 Tier A.

---

## 3. Features

Two feature sets, deliberately competing.

### 3.1 Set H — hazard features (the incumbent)

- Lexicon v2.0, 38 families, scored as distinct families present.
- Raw token counts of the same families.
- **CodeBERT embedding of the test body.** This matters: it moves the claim from "our
  regexes are weak" to "learned code representations are weak on this task", which is the
  version worth publishing.

### 3.2 Set R — relational features (the challenger)

Each is a relation between two program points. Each is expected to change sign across a
repair, which is the property Set H lacks.

#### 3.2.1 The unit of extraction is a path, not a set

The defect is the *absence* of an adequate control, so absence is what has to be computed.
The naive form — `hazard present AND control absent`, both evaluated over the whole file —
is wrong, and wrong in a way that would quietly inflate results. Four counterexamples, all
of them common in practice:

- **Fake control.** `Thread.sleep(100)` is a control by any token lexicon; it sits in the
  async family. It is a guess. Present, and the test is still flaky. This is the most
  frequent case by a wide margin.
- **Wrong target.** `join()` on thread A, while the assertion reads what thread B wrote.
- **Wrong lock.** `synchronized` on a different monitor than the one guarding the data.
- **Wrong path.** `sort()` applied to a different collection than the asserted one.

So a control existing *somewhere in the file* carries no information. Extraction runs per
**(hazard definition → assertion use) path**, and asks four questions of each:

1. **Is there a path at all?** If not, the hazard is inert regardless of controls.
2. **Does a control dominate the path?** Dominance in the CFG sense — *every* path from the
   definition to the use passes through it. A control on one branch is not a control.
3. **Does it act on the same value?** Must-alias on the same variable, not merely a
   coincidence of type.
4. **Is the assertion invariant anyway?** If the predicate does not depend on the choice, no
   control is needed and none should be expected.

The live-hazard predicate is therefore

```
flaky-path  ≈  path ∧ ¬invariant ∧ ¬(real control ∧ dominating ∧ same value)
```

This is also why the fix-move taxonomy of §2.5 falls out cleanly: **Constrain** adds a
dominating control on the path, **Cut** makes condition 4 true, **Own** removes the path.
Each move flips exactly one field. A control *count*, by contrast, moves in the same
direction for real and fake controls alike — which is precisely why the incumbent cannot
tell the two versions apart.

#### 3.2.2 The families

| # | Family | Extraction |
| --- | --- | --- |
| R1 | **Reach** | Backward slice from every assertion argument over local def-use. Does any definition on the slice originate at a hazard API (clock, iteration of an unordered container, thread start, random, directory listing, network read)? Binary, plus a count of distinct hazards reached. Establishes condition 1. |
| R2 | **Invariance** | For each assertion, is its predicate stable under the reached choice? Order-sensitive: `assertEquals` on a `List`/array/`String` derived from an unordered source, indexed access, `assertArrayEquals`. Order-insensitive: `containsAll`, set equality, size, `hasItems`. Establishes condition 4. **Requires static types.** |
| R3 | **Guard adequacy** | For each reached path: does a control dominate it (conditions 2 and 3), and is it real (`join`, `await`, `Future.get`, lock acquire, predicate wait loop) or fake (`Thread.sleep` on a literal, fixed timeout, bounded retry)? Encoded as four fields per path — `dominating`, `same_value`, `kind ∈ {real, fake, none}`, `scope_searched` — never as a single boolean. |
| R4 | **Ownership** | Was each asserted value produced by a statement in this test or its `@Before`, or read from a static field, shared fixture, or external resource? |
| R5 | **Balance** | Multiset of acquisitions (`new File`, `mkdir`, `setProperty`, static assignment, cluster start, registration) against releases (`delete`, `clearProperty`, `reset`, `shutdown`, deregistration) across test plus fixtures. Feature is the count of unmatched acquisitions. |
| R6 | **Constant magnitude** | Minimum sleep/timeout literal in milliseconds; number of sleeps. Deliberately included because the current lexicon discards magnitude entirely. |
| R7 | **Post-barrier distance** | Statements between the last real barrier and the first assertion. |

R1, R2 and R3 all need resolved types — whether `.get(0)` sits on a `List` or on the
materialised output of a `Set` is a type question, and must-alias in R3 needs the same. This
is where **Spoon** earns its place; a regular expression cannot answer it. R5, R6 and R7 are
computable from a plain AST.

#### 3.2.3 Absence is not directly observable

Presence can be found; absence can only be *failed to find*. An absence claim is therefore
only as strong as two things that must be fixed in advance and recorded with the feature:

- **Scope.** No control found *within what*? The test body alone, plus `@Before`, plus
  helpers, plus production callees? Too narrow, and a control that genuinely exists is
  reported absent. E5 is exactly this failure mode: for repairs that touch production code
  only, a body-scoped view reports absence on both sides of the pair.
- **Vocabulary.** Every construct counting as a control must be enumerated. Miss
  `Awaitility`, a project's own `waitFor`, or a custom `eventually`, and each reads as
  absence.

Both failures push the same direction — **false absence produces false flaky** — so R3
carries its `scope_searched` field into the model rather than presenting itself as a clean
boolean, and the vocabulary is versioned alongside the lexicon.

#### 3.2.4 Design rule: prefer pairing over enumeration

Where a hazard has a natural inverse, formulate the feature as an **imbalance** rather than
as a missing token. R5 already does this for state: instead of enumerating every possible
cleanup and reporting none found, it pairs acquisitions against releases over a closed
vocabulary and counts what is unmatched. Async admits the same treatment — `start`/`join`,
`submit`/`get`.

The difference is in how each fails. Enumeration fails open whenever the vocabulary is
incomplete, which is often. Pairing fails only when *both* sides of a pair are unknown, which
is rare. Use the pairing form wherever the construct allows it, and reserve enumeration for
hazards with no inverse.

### 3.3 Paired encoding

Because the design is paired, the model consumes **differences**: `f(before) − f(after)` for
each feature, predicting which side is flaky. A feature that is high on both sides
contributes nothing, which is precisely the discipline we want to impose.

---

## 4. Experiments

| ID | Question | Design | Prediction |
| --- | --- | --- | --- |
| **E0** | Are the pairs real? | Manual inspection of 30 pairs; confirm each repair addresses flakiness; assign a fix move. | ≥90% valid after filtering |
| **E1** | Do hazard features survive a repair? | Set H on the paired task. Exact binomial against 0.5. Run separately for lexicon and CodeBERT. | **≈50%** |
| **E2** | Do relational features survive? | Set R on the same pairs, same splits. McNemar against E1. | Meaningfully above 50% |
| **E3** | Which relation carries it? | Leave-one-family-out ablation over R1–R7, and per fix-move breakdown. | R1×R2 dominant for Cut; R3 for Constrain; R5 for Own |
| **E4** | Does any of it transfer? | Add Set R to the standard FlakeBench flaky/non-flaky task. | Improvement, or an honest negative |
| **E5** | The decisive subset | Pairs where the test body is unchanged (~1 in 6). Set H is at chance *by construction* — same bytes, two labels. Compute Set R over the changed production methods. | Set R separates; Set H cannot |

E1 alone answers the professor's question with a number rather than an argument, and it is
cheap. E5 is the most rhetorically powerful, because for that subset the failure of
body-only representation is not an empirical finding but a mathematical certainty.

### Statistical protocol

- **Split by project**, never by pair. Two tests from the same class must not straddle the
  train/test boundary.
- Bootstrap confidence intervals clustered on project.
- **McNemar's test** for classifier comparison — appropriate because both models see the
  same pairs.
- Exact binomial for any single accuracy against the 0.5 null.
- Report Tier A separately from Tier B throughout.

---

## 5. Phasing

| Phase | Work | Cost | Output |
| --- | --- | --- | --- |
| **0** | Build the pair corpus: resolve PRs, checkout both commits, extract test bodies and changed production methods, apply filters. Pure git and GitHub API; no builds. | ~1 day | `pairs.csv`, `pairs/` source tree |
| **1** | E0 + E1. Manual validation, fix-move labelling, hazard baseline. | ~2 days | The number for the supervisor |
| **2** | Spoon extractor for R1–R7. The real engineering. | ~1 week | `RelationalFeatures.java`, `features.csv` |
| **3** | E2 + E3. | ~2 days | Main result, ablation |
| **4** | E5 on the production-only subset. | ~2 days | The decisive slice |
| **5** | E4 transfer to FlakeBench. | ~3 days | The result that makes it a paper rather than a critique |

Phases 0 and 1 are worth doing before the next supervisor meeting regardless of what
follows. They convert a disagreement about premises into a measurement.

### Interprocedural reach (optional, phase 4+)

R1 is intraprocedural in phase 2. Extending it across call boundaries needs the set of
methods a test actually executes. That can be obtained dynamically from JaCoCo per-test
coverage, at the cost of building and running each project at its pinned commit — expensive
and best deferred until the static version has shown whether reach carries any signal at
all.

---

## 6. What would falsify this

Stated in advance so the result cannot be rationalised after the fact:

- **E1 scores well above chance.** Then hazard tokens do carry defect information and the
  central claim is wrong. Worth knowing, and worth publishing.
- **E2 scores at chance too.** Then the relational account is also wrong, and flakiness is
  not recoverable from static structure at all. This is a real possibility and would be an
  honest negative result.
- **E2 succeeds but E4 fails.** Then the features detect *repairs*, not flakiness — see
  §7.1. This is the most likely disappointing outcome and the one to guard against hardest.

---

## 7. Threats to validity

### 7.1 Learning the repair tool rather than the defect

**The most serious threat.** Tier B repairs were authored by researchers using automated
tooling. iFixFlakies-style repairs have a recognisable fingerprint — a cleaner method added,
a `sort` inserted at a standard location. A model could reach high accuracy by detecting
that fingerprint while learning nothing about flakiness.

Mitigations, all of which should be run:

- Report Tier A (`DeveloperFixed`) as the primary result.
- Test a deliberately trivial baseline — "does the diff add a call to `sort`?" — and
  report it. If it matches Set R, Set R is learning the tool.
- Require E4 to succeed. Transfer to a corpus with no repairs in it is the only real defence.

### 7.2 The "after" side is not verified non-flaky

A merged repair addresses one root cause; it does not certify the test deterministic. Treat
"after" as *repaired for the identified cause*, and say so. Optional mitigation: rerun a
sample of after-versions under NonDex or a rerun campaign.

### 7.3 Induced versus observed flakiness

IDoFT's ID rows were detected by NonDex, which deliberately shuffles iteration order. That
flakiness was provoked, not observed in production CI. It is legitimate for studying the
assumption/guarantee gap — the code genuinely assumed an order it was not promised — but it
should not be described as field-observed.

### 7.4 Category coverage

Order-of-iteration and order-of-execution dominate. Async, concurrency and time depend
entirely on the supplementary sources of §2.2 and may end up too small to analyse
separately. If so, report the restriction rather than pooling categories to hide it.

### 7.5 False absence

The central feature is the absence of an adequate control, and absence is only ever "not
found within a scope, using a vocabulary" (§3.2.3). Both an under-sized scope and an
incomplete vocabulary produce the same error — a control that exists is reported missing,
and a sound test is scored flaky. Two controls on this: report R3 results broken down by
`scope_searched`, so the effect of widening scope is visible rather than baked in; and use
the pairing formulation of §3.2.4 wherever the construct admits one, since it degrades far
more gracefully than enumeration.

### 7.6 Multi-purpose pull requests

A PR may fix flakiness and do three other things. The ≤10-file filter is a blunt instrument;
E0's manual inspection is the real control.

---

## 8. Contributions if it works

1. **A paired before/after benchmark** for flaky-test detection — the first instrument that
   holds project, class, author and style constant while varying only the defect.
2. **A demonstration that hazard-based representations, including learned ones, are at
   chance on it** — reframing what existing detectors actually measure.
3. **A relational feature set** grounded in an explicit account of what flakiness is, with a
   labelled fix-move taxonomy connecting theory to edits.
4. **A transfer result** showing whether relational features improve detection on the
   standard task.

The one-line framing: *existing flaky-test predictors learn the hazard, not the defect.*
