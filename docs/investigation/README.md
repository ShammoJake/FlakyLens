# Where the flakiness evidence lives

Investigation into why the fine-tuned FlakyLens model misclassifies flaky tests,
run on `apache/hadoop` ahead of the 2026-09-04 meeting.

Report (formatted): https://claude.ai/code/artifact/7f678373-13ac-4a7a-9142-3a0146d26f27

## Headline

Of the 17 misclassified Hadoop flaky tests that could be located at the pinned
commits, **all 17** have the evidence for their true category outside the test
method body. Of the 10 correctly classified, 6 have it inside the body. Fisher
exact two-sided p = 0.00071.

Seven misses and zero hits sit in a test class that holds a shared static
`MiniDFSCluster`. Median body length is 9 lines for misses and 17 for hits.

## Where the error is

The shipped predictions classify 8,293 of 8,294 non-flaky tests correctly. Every
error lives in the 280 flaky tests, of which 105 are wrong. Top confusions:

| Confusion | Count |
|---|---|
| concurrency read as async wait | 20 |
| order dependency read as async wait | 13 |
| order dependency read as concurrency | 11 |
| order dependency read as unordered collections | 10 |
| async wait read as order dependency | 10 |

Hadoop misses 20 of its 33 flaky tests, a 61% error rate against 37.5% across
the benchmark, and contains classes with both hits and misses. That makes it a
within-class control rather than a between-project comparison.

## Evidence locations for the 17 misses

| Location | Tests |
|---|---|
| Class fixture and static fields | 4 |
| Class fixture and sibling test | 3 |
| Same-file helper and fixture | 3 |
| Class fixture only | 2 |
| Production callee at depth 1 | 4 |
| Same-file helper and production callee | 1 |

## Worked cases

**TestDFSIO** (5 tests, order dependency read as time). The five-line body holds
a local named `execTime`. The class fixture declares a static `MiniDFSCluster`,
runs once via `@BeforeClass` with no per-test reset, and calls `testWrite()`
under the comment `/** Check write here, as it is required for other tests */`.
A sibling test writes `test.io.skip.size` into the shared static `bench`.

**TestPathData** (4 wrong, 3 right, same class). The three misses list a
directory and compare against an expected set, which reads as unordered
collections. The private helper `sortedString` calls `Arrays.sort` on both
sides, ruling that out. The real dependency is in `@Before`, which calls
`FileSystem.setDefaultUri` and `fs.setWorkingDirectory` on a process-cached
`FileSystem`, while a sibling test reassigns that working directory.

**TestMetricsSystemImpl** (unordered collections read as async wait). Body ends
on `verify(sink1, timeout(200).times(2))` and contains no collection. The helper
`checkMetricsRecords` does `recs.get(0)` and `recs.get(1)`. The production class
builds `allSources = Maps.newHashMap()` and iterates `sources.entrySet()`. Two
hops from the body.

**TestPeerCache** (3 tests, order dependency read as async wait). No static
field, no fixture, no threading vocabulary in the test class at all. The
production `PeerCache` starts a `Daemon` that loops on
`Thread.sleep(expiryPeriod)` calling `evictExpired`, with every accessor
`synchronized`. Only one of the three tests calls `close()`.

**TestRPCCompatibility / TestDelegationTokenForProxyUser** (3 tests). Fixtures
name the dependency almost explicitly: `ProtocolSignature.resetCache()` in
`@Before`, and five static fields plus `FileSystem.setDefaultUri` and
`ProxyUsers.refreshSuperUserGroupsConfiguration` in `@BeforeClass`.

## Extraction priority

1. Static field declarations plus setup and teardown bodies, and whether a
   per-test reset exists. Reaches 9 of 17. No symbol resolution, no call graph,
   no build.
2. Same-file private helper bodies invoked by the test. Reaches 4 more.
3. Sibling-test writes to the static fields this test reads. This is the fact
   that makes an order dependency an order dependency.
4. Production callees at depth 1, per the focal-method expansion in
   `docs/plan-program-analysis-features.md` section 5.2. Reaches the last 4.

Steps 1 to 3 need only the test file already downloaded for the benchmark.
Only step 4 needs Spoon or an equivalent, and only to depth 1.

## Proposed verification

Cheap, no training: run the existing zero-shot prompt on the 280 flaky tests
twice, body only and body plus class context, and count how many of the 105
errors flip. Real: fine-tune the same encoder on the same folds with context
appended. The existing weights cannot be reused, since they were trained on
bodies only and feeding them context measures distribution shift rather than
information gain.

Both should report flaky-subset macro-F1 and full-benchmark macro-F1
separately, because the 8,294 non-flaky tests are already perfect and context
can only cost accuracy there.

## Caveats

- 6 of 33 Hadoop tests did not resolve at the pinned commits. `TestHftpFileSystem`
  (3 tests) and `TestBlockFixer` name classes absent from all three commits,
  `TestFairScheduler.testContinuousScheduling` is missing from a class that
  exists, and one benchmark row carries a bare method name with no class. An 18%
  localization failure on one project is a schedule risk for extraction.
- One project only. cdap misses 8 of 11 and is the natural second.
- Evidence locations are my reading. Each traces to lines quoted in the report,
  but a second reader should check the 17 before this becomes a paper claim.
- Label noise is not ruled out. `TestPeerCache` is labelled order dependency but
  the production code reads closer to concurrency. Worth sampling before scoping
  the extraction work.

## Files

| Path | Contents |
|---|---|
| `FlakyLens_evidence_investigation.pptx` | 13-slide deck: what we did, what we found, code exhibits |
| `hadoop_evidence_table.csv` | 33 Hadoop flaky tests, class-level features, evidence location |
| `hadoop_class_features.csv` | Same rows without the manual evidence assignment, as `feat.py` emits them |
| `misclassified_flaky.csv` | All 105 misclassified flaky tests, benchmark-wide |
| `all_flaky_with_preds.csv` | All 280 flaky tests with prediction and ground truth |
| `sources/` | The 28 Java files read for this investigation, verbatim upstream |
| `sources/MANIFEST.md` | Each file mapped to its upstream path and commit, plus the six that did not resolve |
| `sources/located.csv` | Test to file to commit mapping produced by `locate.py` |
| `scripts/locate.py` | Finds and downloads each test class from a partial Hadoop clone |
| `scripts/feat.py` | Extracts class-level features from the kept sources |
| `scripts/final.py` | Joins the manual evidence assignment and prints the headline counts |
| `scripts/deck.py` | Regenerates the pptx; run it from the scripts directory |

`feat.py` and `final.py` run against `sources/` and need nothing else. `locate.py`
needs a blobless partial clone of Hadoop; point `HADOOP_MIRROR` at one built the
way `sources/MANIFEST.md` describes.

Sources: `FlakeBench/FlakeBench_dataset.csv`,
`src/FlakyLens_Categorization_PerProject-result/Finetuned_Result_with_tokens.csv`,
`results/FlakyLens_Result_Found_By_Author.csv`.
Commits inspected: `cceb68f`, `5537c6b`, `14cd969`.
