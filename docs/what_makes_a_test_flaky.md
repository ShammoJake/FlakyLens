# What Actually Makes a Test Flaky

A conceptual note, written in response to the observation that a flaky test and its
repaired counterpart carry the same signals. If a repair tool such as FlakeSync fixes a
test and the token content barely changes, then whatever those tokens measure, it is not
flakiness. This note works out what is actually being measured, what flakiness actually
is, and what would have to be extracted instead.

---

## 1. The definition

**A test is flaky when its verdict depends on a choice the test does not control.**

Every execution makes decisions that nobody wrote down: which thread wins a race, what
order a hash table iterates, what the clock reads, what state the previous test left
behind, which of several valid responses the network returns. Call these *free choices* —
decisions made by the environment rather than by the program text.

Flakiness requires exactly two conditions, and both are necessary:

1. A free choice occurs during the run.
2. The assertion's outcome is a function of that free choice.

Condition 1 alone is not flakiness. It is ordinary code. A test that starts a thread,
iterates a `HashMap`, or reads the clock is not thereby flaky — it is flaky only if one of
those choices propagates into the verdict. A test that computes a timestamp and never
asserts on it satisfies condition 1 and is perfectly deterministic.

This distinction is the whole problem with token-based detection. Tokens report condition
1. Flakiness is condition 2.

---

## 2. Why a repaired test keeps the same signals

Because **a repair removes condition 2, and essentially never removes condition 1.**

The threads remain. The `HashMap` remains. The clock call remains. What changes is whether
the free choice still reaches the verdict. Every repair is one of three moves:

| Move | What it does | Typical edit |
| --- | --- | --- |
| **Constrain** the choice | the choice is no longer free | `join()`, `sort()`, seed the generator, inject a `Clock` |
| **Cut** the dependency | assert a property invariant under the choice | `containsAll` instead of indexed equality; set equality instead of list equality |
| **Own** the state | remove the choice from scope | fresh fixture, reset in teardown, unique temp directory |

Note what none of the three do: delete the hazard. `Constrain` adds a control alongside the
hazard. `Cut` leaves the hazard untouched and weakens the assertion. `Own` changes
lifecycle, not computation.

A model that scores a test by which hazard families are present therefore sees the same
input before and after the repair. Two identical inputs, two opposite labels. Such a model
is not merely inaccurate on this task — it is at chance by construction. The premise is
wrong, not the tuning.

---

## 3. The deeper statement

**A flaky test is a place where the code assumes a stronger guarantee than the API
actually provides.**

This one statement covers the standard categories:

| Category | What the code assumes | What is actually guaranteed |
| --- | --- | --- |
| async wait | the work completes within *N* ms | it completes eventually |
| concurrency | one particular interleaving | only what synchronization establishes |
| time | a stable, monotonic clock in a fixed zone | a reading, taken once |
| unordered collections | a specific iteration order | membership only |
| order dependency | the environment is clean on entry | no ordering between tests at all |

The framing explains the repair behaviour exactly. A repair never deletes the API. It
closes the gap from one side — either strengthening the guarantee (`sort`, `join`, a
seeded generator) or weakening the assumption (assert a weaker predicate).

The tokens name the API. The defect is the *gap*. The gap has no token, because it is the
absence of a relationship rather than the presence of a symbol.

---

## 4. What a developer actually looks for

Developers do not scan for keywords. They run backwards from the failure:

1. Which value differed between the passing run and the failing run?
2. Where did that value come from?
3. Keep walking back until reaching something the test did not decide — a clock, an
   iteration, a thread, a leftover file, a response.
4. That is the source. Everything between it and the assertion is the *reach*.
5. Is there a guard anywhere on that path, and is it a real one?

Step 5 is where experience shows. `latch.await()` is a guard. `Thread.sleep(100)` is a
guess wearing a guard's clothes, and in practice it is the single strongest tell available,
because it is the author stating in writing that they knew a race existed and picked a
number. The same applies to a hard-coded timeout and to a retry count.

The conclusion that matters for tooling:

> **The unit of flakiness is a path, not a token** — from a free choice to an assertion,
> minus any real guard along it.

---

## 5. Evidence from real repairs

Three merged fixes, drawn from the IDoFT dataset of flaky tests with accepted repair pull
requests. Each one behaves exactly as the account above predicts.

### 5.1 The repair is not in the test at all

`apache/hadoop#1868`, fixing `TestMetricsSystemImpl.testInitFirstVerifyCallBacks`:

```java
// ReflectionUtils.java  (production code)
-      for (Field field : clazz.getDeclaredFields()) {
+      Field[] sortedFields = clazz.getDeclaredFields();
+      Arrays.sort(sortedFields, new Comparator<Field>() {
+        public int compare(Field a, Field b) { return a.getName().compareTo(b.getName()); }
+      });
+      for (Field field : sortedFields) {
```

The test body is byte-identical before and after. `Class.getDeclaredFields()` documents no
order; the surrounding code treated it as though it did. This is the assumption/guarantee
gap in its purest form, and it lives in production code, not in the test.

In a sample of 90 accepted repair pull requests, 10 modify production code only and 6
modify both. So for roughly one repair in six, no test-body representation whatsoever can
distinguish the flaky version from the fixed one.

### 5.2 The repair inverts a token-count reading

`stanfordnlp/CoreNLP#1215`, fixing `DirectedMultiGraphTest.testConnectedComponents`:

```java
-    List<Set<Integer>> ccs = graph.getConnectedComponents();
-    assertEquals(ccs.size(), 4);
-    assertEquals(CollectionUtils.sorted(ccs.get(0)), Arrays.asList(1, 2, 3, 4));
+    Set<Set<Integer>> ccs = new HashSet<>(graph.getConnectedComponents());
+    Set<Set<Integer>> expectedCcs = new HashSet<>(Arrays.asList(edge1, edge2, edge3, edge4));
+    assertEquals(expectedCcs, ccs);
```

Score this by hazard families and the fixed version looks *worse*: a `HashSet` has been
added where none existed. The container is not the defect. The defect was `.get(0)` — an
index into a collection whose order was never guaranteed — and the repair is a textbook
**Cut**: same data, a predicate that no longer depends on order.

### 5.3 The repair is a Constrain

`apache/commons-lang#481`, fixing `RecursiveToStringStyleTest.testPerson`:

```java
// ReflectionToStringBuilder.java  (production code)
     final Field[] fields = clazz.getDeclaredFields();
+    Arrays.sort(fields, Comparator.comparing(Field::getName));
```

Same root cause as 5.1, repaired by imposing an order rather than by relaxing the
assertion. The accompanying test edits merely reorder the expected strings to match; they
are consequences of the repair, not the repair itself.

---

## 6. What would have to be measured instead

Per assertion, not per file:

- **Reach** — does a backward slice from the assertion's arguments touch a source of
  nondeterminism?
- **Invariance** — is the assertion's predicate stable under that choice?
  `assertEquals(list, map.keySet())` is not; `assertTrue(set.containsAll(x))` is. Identical
  container, opposite verdicts.
- **Guard quality** — a real barrier (`await`, `join`, a future's `get`), a fake one
  (`sleep`, a fixed timeout, a retry bound), or none at all.
- **Ownership** — did the test write the value it reads, or find it already there?

And one whole-test property:

- **Balance** — is everything created also destroyed, and everything written also reset?
  Order dependency is an imbalance, by definition.

Each of these is a *relation between two program points* rather than a property of one
point. Each of them changes sign across a repair. That is exactly the property that token
counts lack, and it is what makes the account testable rather than merely plausible.

One consequence for tooling: both reach and invariance need resolved types. Whether
`.get(0)` sits on a `List` or on the materialised output of a `Set` is a type question, and
no regular expression answers it. A type-resolved AST is a prerequisite, not a refinement.

---

## 7. The falsifiable claim

Build a corpus of before/after pairs from repairs that were actually merged. Then:

1. Score both sides with hazard-token features. **Prediction: chance.** If the features do
   better than chance, this account is incomplete and the tokens carry something real.
2. Score both sides with the relational features of section 6. **Prediction: separation.**
   If they also land at chance, the account is wrong, and we learn that at low cost.

The first experiment is worth running regardless of the outcome, because it converts an
argument about premises into a number.

### Available data

The IDoFT dataset (`TestingResearchIllinois/idoft`, `pr-data.csv`) supplies 2,487 rows with
an accepted or developer-authored repair and a pull-request link, spanning 709 distinct
pull requests across 481 projects. Its `SHA Detected` column gives the pre-repair commit
directly, so both sides of each pair are checkoutable without commit archaeology.

Two limitations to state up front rather than have them found:

- Repairs concentrate in implementation-dependent (1,943) and order-dependent (~340)
  flakiness. There are only 29 in the general non-deterministic category, so pairs for
  async wait, concurrency and time are effectively unavailable.
- The implementation-dependent rows were detected by NonDex, meaning the flakiness was
  induced by deliberately shuffling iteration order rather than observed in the wild. The
  `DeveloperFixed` subset (340 rows) is the cleaner ground truth, since those repairs were
  authored by the projects' own maintainers.

---

## 8. Summary

- Flakiness is not a property of a test's ingredients. It is a property of a path from an
  uncontrolled choice to an assertion.
- Equivalently: it is a gap between the guarantee an API offers and the guarantee its
  caller assumes.
- Repairs close that gap without removing the ingredients, which is why hazard tokens
  cannot distinguish a flaky test from its repaired form.
- The features that survive a repair are relations — reach, invariance, guard quality,
  ownership, balance — and computing them requires dataflow over a type-resolved AST.
