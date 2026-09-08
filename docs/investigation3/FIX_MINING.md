# Deriving the vocabulary from repairs, not from flaky test bodies

## 1. Why

The tier-1 lexicon (`docs/investigation2/lexicon.json`, 38 families) is mined
from flaky test **bodies** and evaluated on the corpus it was mined from. Two
problems, and the second is the serious one:

1. **Circularity.** FlakeBench in, FlakeBench out. "Held out" controls for
   memorisation, not for distribution.
2. **It is mined from the wrong thing.** The claim under investigation is that
   what a flaky test *contains* is not what makes it flaky. A vocabulary derived
   from flaky test bodies is derived from exactly the correlation we argue is
   spurious, so it cannot be used as evidence about that correlation without
   begging the question.

This mines the **repairs** instead. A construct earns its place if developers
actually changed it to fix flakiness — causal rather than correlational, and
drawn from the IDoFT pair corpus, which is not the evaluation set.

A fix diff hands over both halves of the vocabulary at once:

```diff
-      resultBuilder.add(clazz.getDeclaredMethods());            <- HAZARD
+      Method[] declaredMethods = clazz.getDeclaredMethods();
+      Arrays.sort(declaredMethods, Comparator.comparing(...));  <- CONTROL
```

The control half matters independently: `SliceAnalysis.java` currently carries a
**hand-written** `CONTROL` set, and this replaces that guess with evidence.

## 2. Method

**Corpus.** The eligible pair filter (`after_type != tool_patch`,
`before_sha_reachable != no`, `pr_merged != false`, no parameterised selector)
gives 2,214 pairs over **609 distinct fix commits across 250 projects**.

**Fetching.** `gh api repos/{slug}/commits/{sha}` returns per-file patches, so no
checkout is needed anywhere in this pipeline. Only `.java` files are kept, and a
commit touching more than 25 Java files is skipped — it says nothing about one
flaky test and its vocabulary would swamp the counts.

Fetched with **zero failures**: 609 fix commits, 1,217 background commits.

**Background.** Ordinary commits sampled from the *same* projects, so project
idiom (a house style that always reaches for Guava) cancels out instead of being
mistaken for a flakiness signal.

**Constructs, not words.** A bare identifier like `sort` is ambiguous; `.sort(`
as a call is not. Each line yields namespaced tokens — `call:`, `new:`,
`static:`, `type:`, `annot:`, `kw:` — after comments and string literals are
stripped, exactly as the tier-1 lexicon does.

**Roles.** `control` = constructs on **added** lines. `hazard` = constructs on
**removed and context** lines at the repair site.

**Scoring.** Log-odds ratio with an informative Dirichlet prior (Monroe, Colaresi
and Quinn 2008), reported as a z-score. Unlike a raw frequency ratio it does not
hand the top of the table to a construct seen twice. Verified on synthetic input:
a balanced construct scores −0.01, an enriched one tops the table, a depleted one
goes negative, and a construct appearing twice in one corpus and never in the
other is suppressed rather than promoted.

**Support floors** match the existing lexicon's mining criteria so the two are
comparable: ≥5 distinct projects and ≥6 distinct commits. Unchanged from the
defaults. 125 control and 179 hazard constructs pass.

**Background matching.** A fix commit touches a flaky test by construction; an
ordinary commit often touches no test at all — **88.5% against 66.9%**. Left
uncorrected that mismatch alone puts test scaffolding at the top of the hazard
table. `--match-test-touching` restricts the background to commits that also
touch a test file (1,217 → 814). Both variants are shipped:
`fix_vocabulary.json` (unmatched) and `fix_vocabulary_matched.json`.

## 3. The control vocabulary — the strong result

Top entries under the matched background. `indep` = projects **not** in
FlakeBench, so a family supported there transfers cleanly.

| construct | z | fix | bg | projects | independent |
| --- | ---: | ---: | ---: | ---: | ---: |
| `type:LinkedHashMap` | **8.1** | 84 | 29 | 68 | 53 |
| `new:LinkedHashMap` | 7.9 | 80 | 29 | 66 | 51 |
| `call:sort` | 6.4 | 50 | 14 | 40 | 23 |
| `type:JSONAssert` | 5.8 | 32 | **0** | 17 | 13 |
| `static:JSONAssert.assertEquals` | 5.6 | 30 | **0** | 16 | 12 |
| `static:Arrays.sort` | 5.3 | 28 | 2 | 26 | 13 |
| `type:Comparator` | 4.8 | 33 | 16 | 27 | 17 |
| `static:Comparator.comparing` | 4.6 | 24 | 5 | 20 | 14 |
| `type:JSONException` | 4.4 | 20 | 2 | 11 | 7 |
| `annot:JsonPropertyOrder` | 4.1 | 16 | **0** | 13 | 9 |
| `type:LinkedHashSet` | 3.7 | 22 | 14 | 21 | 15 |

This is a clean recovery of the **Constrain** repair move, and it is exactly what
a hand-written list would be expected to contain: swap the hash container for an
ordered one, or sort before comparing.

**Three constructs are genuine discoveries** — absent from the tier-1 lexicon and
with a background count of zero or near zero:

- **`JSONAssert.assertEquals`** (32 fix, 0 background, 17 projects). Developers
  close order flakiness by comparing JSON *semantically* rather than as a string.
  This is a **Cut** move: the assertion stops depending on order at all.
- **`@JsonPropertyOrder`** (16 fix, 0 background, 13 projects). Pinning
  serialisation order at the type — a **Constrain** move one level up from the
  test.
- **`JSONException`** — the handling that comes with the JSONAssert switch.

None of these would be found by looking at flaky test bodies, because they exist
only *after* the repair. That is the argument for this method in one example.

## 4. The hazard vocabulary — the weak result, and why

Top entries under the matched background:

| construct | z | fix | bg | projects |
| --- | ---: | ---: | ---: | ---: |
| `type:Test` | 6.9 | 301 | 395 | 146 |
| `annot:Test` | 6.8 | 266 | 332 | 130 |
| `call:assertEquals` | 6.7 | 96 | 39 | 52 |
| **`new:HashMap`** | **6.6** | 99 | 45 | 77 |
| **`type:HashMap`** | **6.5** | 130 | 91 | 93 |
| `static:Assert.assertEquals` | 6.2 | 69 | 18 | 39 |
| `type:Assert` | 5.9 | 114 | 88 | 62 |
| `type:HashSet` | 3.8 | 48 | 38 | 38 |
| `new:HashSet` | 3.1 | 33 | 26 | 26 |

The genuine signal is there — `HashMap` and `HashSet` — but it sits *below* test
scaffolding (`@Test`, `Assert`, `assertEquals`), which is an artefact of what a
fix commit is rather than evidence about flakiness.

Matching the background helped but did not remove it: `type:Test` fell 8.1 → 6.9
while `new:HashMap` rose 6.2 → 6.6, so real signal gained on scaffolding without
overtaking it.

**The asymmetry is structural, not a tuning failure.** *Added* lines are
precisely the repair, so the control side is almost pure signal. *Removed and
context* lines are mostly untouched surrounding code, so the hazard side is
mostly noise about what test files look like. **Fix diffs are a good source for
the control vocabulary and a poor one for the hazard vocabulary**, and the
honest conclusion is to take the control half from here and leave the hazard half
to typed analysis of the source.

## 5. Comparison against the tier-1 lexicon

**11 of 38 families are corroborated** by fix evidence:

| family | constructs | best z | strongest example |
| --- | ---: | ---: | --- |
| `uc.hash_container` | 11 | 8.2 | `type:LinkedHashMap` |
| `od.singleton_cache` | 3 | 3.0 | `call:reset` |
| `uc.to_sequence` | 5 | 2.6 | `static:Arrays.asList` |
| `uc.sequence_assert` | 4 | 2.4 | `call:containsExactly` |
| `uc.list_container` | 6 | 2.3 | `type:ArrayList` |
| `uc.unordered_iter` | 6 | 1.8 | `call:keySet` |
| `conc.atomic` | 1 | 0.3 | `type:AtomicReference` |
| `od.fs_state` | 1 | 0.3 | `new:File` |
| `uc.map_set_type` | 1 | −0.1 | `type:Properties` |
| `conc.concurrent_coll` | 1 | −0.2 | `type:ConcurrentHashMap` |
| `od.lifecycle` | 1 | −0.5 | `call:close` |

### The 27 families with no fix evidence are UNTESTED, not contradicted

This is the most important caveat in this document. The pair corpus is
overwhelmingly one category:

| label | fix commits | share |
| --- | ---: | ---: |
| unordered collections | 499 | **81.9%** |
| test order dependency | 105 | 17.2% |
| (none) | 10 | 1.6% |
| time | 3 | 0.5% |
| async wait | 0 | 0% |
| concurrency | 0 | 0% |

So `async.sleep` having no fix evidence means **the corpus contains no async
fixes**, not that the family is wrong. Only the `uc.*` and `od.*` families are
actually put to the test here. Any claim that this mining "invalidates" 27
families would be false, and the numbers above are the reason.

### Where it does and does not agree with the FlakeBench measurement

Comparing against the measured per-family discrimination on FlakeBench
(`STATUS.md` §3.1):

- **Agreement on the strong case.** `uc.hash_container` is the best-supported
  family here (11 constructs, best z 8.2) and it measured 1.30× on FlakeBench —
  weak, but its *typed* form is what the tier-2 prototype used to reach 3.83×.
  Fix evidence backs the construct, not the token.
- **Agreement on the noise.** `uc.map_set_type` scores **−0.1** here and measured
  **0.97×** on FlakeBench. Two independent methods agree it carries nothing.
- **Agreement on the anti-signal.** `od.fs_state` scores 0.3 here and measured
  **0.58×** on FlakeBench — no support from either direction.
- **Disagreement worth noting.** `uc.list_container` is corroborated here
  (6 constructs, z 2.3) but measured 1.06× on FlakeBench. The reconciliation is
  that `ArrayList` appears in fixes as the *replacement* container — it is a
  control, not a hazard — and the tier-1 lexicon files it under a hazard family.
  That is a category error in the lexicon that this mining exposes.

That last point is the clearest single case of the mining doing work the
FlakeBench-derived lexicon could not: it separates *what was there before* from
*what the developer put there instead*, and the tier-1 lexicon conflates them.

## 6. Overlap caveat

**46 of FlakeBench's 98 projects also appear in the pair corpus.** Derive-here /
evaluate-on-FlakeBench is therefore not fully independent.

Every row of `fix_vocabulary*.json` carries `projects_overlapping_flakebench` and
`projects_independent` so a clean transfer test stays available. The headline
control constructs hold up on the independent side alone: `LinkedHashMap` 53
independent projects, `call:sort` 23, `JSONAssert` 13, `Comparator.comparing` 14.
None of the top control findings depend on the overlap.

The recommended reporting split for the paper is the 52 non-overlapping
FlakeBench projects as the clean transfer test, the full 98 as secondary, and the
gap between them as the measure of leakage.

## 7. Limitations

- **Category coverage is the binding constraint.** 81.9% unordered collections.
  This corpus cannot say anything about async, concurrency or time repairs.
- **The hazard half is confounded** by what a fix commit is (§4). Use the control
  half; derive hazards from typed source analysis instead.
- **Context lines are noisy** by construction — they are the code the developer
  did *not* change.
- **A construct is a line-level regex**, not a resolved type. `call:get` cannot
  distinguish `map.get(key)` from `list.get(0)`, which is precisely the
  distinction that made `get` a bad entry in the hand-written `CONTROL` set.
- **Log-odds is a ranking, not a decision procedure.** Nothing here says where to
  cut the list; the support floors are inherited from the previous lexicon for
  comparability rather than chosen on evidence.

## 8. Artefacts

| file | content |
| --- | --- |
| `scripts/mine_fix_diffs.py` | `fetch` / `derive` / `compare` |
| `fix_vocabulary.json` / `.csv` | derived vocabularies, unmatched background |
| `fix_vocabulary_matched.json` / `.csv` | with the background matched on touching a test file — **use this one** |
| `fix_vs_lexicon.json` | family-by-family corroboration and the uncovered constructs |
| `mining/` | the fetch cache, 5,088 commit JSONs. Gitignored; regenerable from the GitHub API |

Reproduce with:

```bash
python docs/investigation3/scripts/mine_fix_diffs.py derive --match-test-touching --out-suffix _matched
python docs/investigation3/scripts/mine_fix_diffs.py compare
```

`derive` and `compare` are pure local computation over the cache — no network.
