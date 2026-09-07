# The Evidence Runner

How `pairs.csv` becomes per-pair evidence: for each side of each pair, the executed
methods (JaCoCo) and the source model (Spoon), joined.

The design borrows its shape from `tdrepro/runAll.sh` in `shanto-Rahman/NOD-Test-Repair`
— inject JaCoCo, run one test, report to XML, parse the executed methods — and departs
from it in four places, each noted below where it matters.

---

## 1. What it produces

One directory per pair, under a master output directory:

```
runs/
  _manifest.csv                     one row per pair: status, counts, timing
  P1334__jsondoc__JSONDocApiAuthBuilderTest.testApiAuthToken/
    meta.json                       the pairs.csv row, resolved refs, per-step status
    summary.json                    before / after / delta counts
    before/
      status.json                   per-step outcome for this side
      checkout.log build.log test.log report.log spoon.log
      jacoco.exec                   raw coverage
      coverage.xml                  jacococli report
      executed_methods.csv          covered methods, with a `nesting` column
      spoon_methods.json            every method Spoon can see, with bodies
      executed_with_bodies.json     ← the join; this is the product
      test_method.json              the flaky test method itself
      source/                       the checkout (removed unless --keep)
    after/
      ... same ...
```

`executed_with_bodies.json` is what downstream analysis reads. Per covered method:

| Field | Meaning |
| --- | --- |
| `class`, `method`, `descriptor` | JVM identity, `$` preserved |
| `nesting` | `top-level` / `nested` / `anonymous` |
| `lines_covered`, `lines_total`, `branches_covered`, `branches_missed` | from JaCoCo |
| `match_level` | `exact` / `arity` / `simple` / `synthetic` / `unmatched` |
| `file`, `line_start`, `line_end` | from Spoon |
| `body` | Spoon pretty-print, every type fully qualified |
| `raw_body` | the original source text |
| `invokes` | qualified call targets in the body |
| `is_anonymous`, `is_test`, `signature`, `modifiers` | from Spoon |

Two bodies are kept on purpose. `body` has types resolved, which is what a type-aware
feature needs; `raw_body` is what the author actually wrote, which is what a token-level
baseline must see if the comparison between them is to be fair.

---

## 2. The scripts

| Script | Role |
| --- | --- |
| `setup_tools.sh` | resolves jacocoagent, jacococli and the Spoon classpath through Maven; writes `tools/tools.env` |
| `resolve_prs.py` | **`gh`** — turns each PR link into the commit that actually landed, plus its first parent and file footprint |
| `run_pair.py` | one pair, both sides — the worker |
| `SpoonExtract.java` | dumps every method Spoon can see, with descriptors and bodies |
| `collect_coverage.py` | `coverage.xml` → `executed_methods.csv` |
| `join_spoon_coverage.py` | coverage × Spoon → `executed_with_bodies.json` |
| `run_all_pairs.py` | filtered, resumable, parallel driver over `pairs.csv` |

### Usage

```bash
cd docs/investigation3/scripts
bash setup_tools.sh tools                      # once

# once, needs authenticated gh: resolve all 709 PR links to real commits,
# then fold the result into pairs.csv
python resolve_prs.py --out data/pr_meta.csv --jobs 6
FLAKYLENS_DATA=data python build_pairs.py

# one pair, keeping the checkouts so you can look at them
python run_pair.py --pair-id P1334 --out runs --tools tools --keep

# always look before you leap
python run_all_pairs.py --out runs --tools tools \
       --category "test order dependency" --reachable --dry-run

# then a bounded slice
python run_all_pairs.py --out runs --tools tools \
       --category "test order dependency" --reachable --shuffle --limit 50 --jobs 3
```

`run_all_pairs.py` filters on category, source, repair author, project, declared JDK,
`--with-env` (has a ReproFlake environment), and `--reachable`. It skips any pair whose
`after_type` is `tool_patch`, because those have no git ref — see §5. It is resumable:
a pair with `meta.json` is skipped unless `--force`, and `_manifest.csv` is rewritten
after every completion, so an interrupted sweep loses nothing.

---

## 3. What each side does, and why

**1. Resolve the refs.** This is where `gh` earns its place, and the first version of
this runner got it wrong.

*After side.* `fixed_sha` rows use the SHA. `pr` rows use `merge_commit_sha` from
`pr_meta.csv` — the commit that actually landed on the base branch. Without it the
runner falls back to `refs/pull/<n>/merge` then `refs/pull/<n>/head`, and that fallback
is bad: **GitHub deletes the `/merge` ref when a PR closes**, so every merged PR lands on
`/head`, which is the author's branch tip — not what landed if the maintainer squashed or
rebased, and missing any base-branch movement since the branch point. All four smoke-test
pairs fell through to `/head` before this was fixed.

*Before side.* `--before auto` (the default) prefers the merge commit's **first parent**
over IDoFT's `SHA Detected` whenever `minimal_pair == yes`. The two differ substantially:
`SHA Detected` is where the flakiness was observed and can predate the repair by years,
so a pair built on it differs by the repair *plus* everything else that landed meanwhile.
The merge parent is the tree immediately before the repair. `--before idoft` keeps the
old behaviour; every side records `ref_kind` in `status.json`, so a mixed corpus stays
auditable.

`minimal_pair` is not assumed — it is derived from the merge commit's parent count and
the PR's commit count. Two parents means a true merge and the first parent is the base.
One parent means squash *or* rebase, and those differ: a squash puts a single commit on
the base, but a rebase replays every commit, so for a multi-commit PR the last one's
parent is another commit from the same PR. Trustworthy only when the PR had one commit.

Cross-check that this construction is right: jsondoc PR 261 merges as `3b3907f4` with
first parent `16d42fd3`, and ReproFlake independently ships that pair as
`jsondoc=jsondoc-core=16d42fd`. Neither ref guess produced it.

**2. Check out.** Shallow, single ref, with `core.longpaths=true`. Any previous checkout
is removed first, and a failure to remove it is reported rather than swallowed.

**3. Build — and treat failure as non-fatal.** `mvn -pl <module> -am -DskipTests install`,
with the quality gates skipped: `enforcer`, `rat`, `checkstyle`, `license`, `javadoc`,
`gpg`, `spotbugs`, `pmd`, `animal-sniffer`, `dependency-check`, `forbiddenapis`,
`japicmp`, `revapi`, `site`, `source`. Those are gates, not build steps; their failures
say nothing about whether the code compiles. `dependency-check` earned its place on that
list the hard way — it tries to download NVD CVE feeds, and on the first run its network
failure was indistinguishable from a broken build.

A failed build stops coverage but not the pair: step 4 still runs.

**4. Run Spoon, over the same source roots the coverage report will span.** Spoon needs
sources, not a build, so a pair whose build fails still yields the static half of the
evidence and `meta.json` records that rather than the pair being discarded. Given 417
reachable build points of unknown build health, that is not a marginal case.

The scope matters as much as the timing. JaCoCo reports across *every* module that
produced `target/classes`, so scoping Spoon to the target module alone leaves every
covered upstream-module method unmatched — on the first XChange run that was 31 of 62
non-synthetic rows. Spoon's roots are therefore taken from the same enumeration that
builds jacococli's `--sourcefiles`, falling back to the module's own `src/main|test/java`
when the build failed and there are no `target/` directories to enumerate.

**5. Run exactly one test under the agent.**

```
mvn -pl <module> org.jacoco:jacoco-maven-plugin:0.8.11:prepare-agent test \
    -Dtest=<Class>#<method> -Djacoco.destFile=<abs path>
```

**A non-zero exit is not a failure here.** The before side is a flaky test at its flaky
commit; it is *supposed* to be able to fail. The check is whether `jacoco.exec` was
written. `test_passed` is recorded separately, because whether the test passed is itself
data.

**6. Report and parse.** `jacococli report` over every module that produced
`target/classes`, then `collect_coverage.py`.

**7. Join.** `join_spoon_coverage.py`, tiered: exact descriptor, then arity, then simple
class name.

---

## 4. Four departures from `runAll.sh`

**JaCoCo is attached from the command line, not by rewriting POMs.** `runAll.sh` runs
`modify-project.sh`, which edits every `pom.xml` in the tree through a `PomFile.java`
helper. Invoking `prepare-agent` as a CLI goal leaves the checkout pristine, which
matters when the checkout is the artefact being analysed. If a project pins surefire's
own `argLine` — which silently discards the one `prepare-agent` sets — the runner retries
once with an explicit `-DargLine=-javaagent:...` and records `argline_fallback: true`.

**Anonymous classes are kept.** `collect_method_body.py` in NOD-Test-Repair looks up
classes with `class_name.split("$")[0]` and walks only `class_declaration` nodes, so
JaCoCo's `PeerCache$1.run()` can never match — and that is exactly where concurrency
evidence lives. `SpoonExtract` descends into `CtNewClass` bodies and `collect_coverage.py`
keeps the `$`, so `a.b.Outer$1` joins normally. A `nesting` column makes the population
countable rather than assumed.

**Spoon replaces tree-sitter.** The tree-sitter API that script uses
(`Parser(); parser.set_language(...)`) was removed in tree-sitter 0.22. More to the point,
tree-sitter gives no types, and the features this investigation needs — does a backward
slice from the assertion reach a hazard, is `.get(0)` on a `List` or on a materialised
`Set` — are type questions.

**No per-project special cases.** `runAll.sh` carries hard-coded branches for
`doanduyhai/Achilles`, `zxing/zxing`, undertow, luwak and others. Those encode real
problems, and they will resurface; the intent here is to let them fail visibly in
`status.json` and fix them generically, rather than to start with a list of exceptions.

---

## 5. Known limits

**Tool-patch pairs cannot be run.** 113 pairs (72 FlakeSync, 41 ODRepair) have a
generated patch rather than a commit as their after side. Applying those needs the
FlakeSync artifact and ODRepair's patch files, and neither applies cleanly without its
own harness. The driver skips them; `after_type == "tool_patch"` marks them.

**Test selectors with parameters.** A few rows carry a method name like
`testWillMakeOrder(VertxTestContext)`, and `-Dtest=Class#method` does not accept that.
Those rows will fail at the test step with no coverage.

**JDK.** Everything runs on whatever JDK is on `PATH`. 465 subjects in the corpus need
Java 8 and 84 need Java 17 (`datasets.md` §3.4). `--java` filters the selection to one
declared version; per-subject `JAVA_HOME` switching is not implemented yet and is the
next thing this runner needs.

**Parallelism and `~/.m2`.** Concurrent Maven builds share one local repository, and
Maven does not lock it. `--jobs 2` or `3` is safe in practice; higher risks a corrupted
artifact download that then looks like a build failure. Use `-Dmaven.repo.local` per
worker if that becomes a problem.

**Disk.** Each side is a shallow checkout plus a full `target/`. Checkouts are deleted
after each side unless `--keep`, but `~/.m2` grows without bound across a sweep.

---

## 6. Verification

Four pairs were run end to end, chosen to differ in project, module layout and category.
They are a smoke test, not a sample: the aim was to make the pipeline fail in as many
ways as possible and fix each one, not to estimate a success rate.

| Pair | Project | Module layout | Category | Before | After |
| --- | --- | --- | --- | --- | --- |
| P1334 | fabiomaffioletti/jsondoc | 1 source root | unordered collections | ok | ok |
| P1198 | authorjapps/zerocode | 2 source roots | unordered collections | ok | ok |
| P1277 | dropwizard/dropwizard | 6 source roots | test order dependency | ok | ok |
| P1721 | knowm/XChange | 3 source roots | unordered collections | ok | ok |

Total 4m54s for 8 sides at `--jobs 2`, so roughly **35–60 s per side** once Maven's
local repository is warm. Join quality after the fixes below:

| Pair | Side | Spoon methods | Covered | Joined | Synthetic |
| --- | --- | ---: | ---: | ---: | ---: |
| P1334 | before / after | 645 | 90 / 90 | **100% / 100%** | 8 / 8 |
| P1198 | before / after | 1,625 / 1,802 | 7 / 2 | **100% / 100%** | 2 / 0 |
| P1277 | before / after | 718 | 9 / 9 | **100% / 100%** | 3 / 3 |
| P1721 | before / after | 1,810 | 71 / 72 | **100% / 100%** | 9 / 9 |

Every non-synthetic covered method on all eight sides was matched to its source.

P1198 is the useful one for the anonymous-class question. Its before side covers
`GsonSerDeProvider$KafkaHeadersAdapter$1.create(Gson, TypeToken)` — an anonymous class
method — and it matched **exactly**. That is the case `collect_method_body.py` in
NOD-Test-Repair cannot express at all. The same pair also shows a real before/after
difference: 7 covered methods before, 2 after, with the two anonymous ones gone.

### 6.1 Five bugs found, all of them silent

Nothing here surfaced as a clean error message; each one presented as something else.

| Symptom | Actual cause | Fix |
| --- | --- | --- |
| `jacococli` reported `FileNotFoundException` on a path that plainly existed | class and source directories were built relative to the launch directory, but the command runs with `cwd=<checkout>` | absolute paths throughout |
| `git fetch` failed in 0.2 s with "not a git repository" | the pair directory name was long enough that `git init` could not create `.git` under Windows' 260-character limit — and `git init`'s exit code was never checked | short directory names, plus an explicit check that `.git` exists |
| a re-run failed at checkout with "would be overwritten" | `shutil.rmtree(ignore_errors=True)` reports success while leaving git's read-only pack files behind | `rmtree_hard()`: clears the read-only bit, retries, never raises, and returns whether it worked |
| dropwizard "build failed" on both sides | OWASP `dependency-check` could not reach `nvd.nist.gov`. A network failure, indistinguishable from a broken build in the log | added to `GATE_SKIPS` with `forbiddenapis`, `japicmp`, `revapi`, `site`, `source` |
| XChange joined only 31 of 62 non-synthetic rows | Spoon was scoped to the target module while JaCoCo reports across every module that produced `target/classes`, so covered upstream methods were unmatchable | Spoon runs after the build over the same source-root enumeration jacococli uses; 50% → 100% |

One further refinement came out of P1198's single remaining miss: an anonymous class
declares no constructor in source, so Spoon has no `<init>` for one while javac
synthesises it. That is now classified `synthetic` rather than `unmatched` — a
distinction that matters, because the same class's `create(..)` matched exactly, so the
gap is the implicit constructor and not anonymous classes as such.

### 6.2 What this does not establish

Four pairs, all Java 11, all with a warm `~/.m2`, and all of them projects already known
to compile from the `datasets.md` §3.5 probe. It says the pipeline works; it says nothing
about how often it will work across 2,541 runnable pairs. The obvious first slice is
`--with-env --java 11 --reachable`, which is **554 pairs** — every one of them declared
by ReproFlake to need the JDK this machine actually has.

---

## 7. The extractor, and what running it on the first 57 pairs changed

`extract_features.py` is the first consumer of the collected evidence. It resolves
four scopes of source text per pair-side and applies the investigation-2 lexicon
to each one separately:

```
python docs/investigation3/scripts/extract_features.py runs2 --out features.csv
```

| scope | resolved from |
| --- | --- |
| `test_body` | the flaky test method in the Spoon model |
| `fixtures` | `@Before` / `@After` / `@Rule` methods and initialiser blocks of the test class and its superclasses |
| `fields` | declared fields of the same classes |
| `prod` | production methods JaCoCo recorded as executed by that test |

Keeping the scopes apart is the point. "The test body is clean but a field it
reads is a `HashMap`" and "the test body is clean and nothing it touches is
hazardous" are different claims, and only the second is evidence.

### 7.1 Four defects the first run exposed

Each of these was silent: the pipeline reported `ok` and produced a file with the
wrong contents in it.

| what the extractor hit | cause | fix |
| --- | --- | --- |
| `test_method.json` empty on **103 of 115 sides** | IDoFT names a parameterised instance `formatTestNameString_success[ARRAY]`; no Java method is called that. `run_group.py` matched the selector literally | strip the instance suffix (`rp.BRACKET`) before searching the model |
| the lexicon fired on tokens nobody wrote, and missed ones they did | `join_spoon_coverage.py` carried only `body`, Spoon's fully-qualified pretty-print of the block. Measured over 114 sides: `conc.parallel` matched **100%** of them against **0%** on the real source (it was matching `java.util.concurrent.` in qualified type names), while `conc.sync_kw` showed **2%** against **91%** (`synchronized` is on the declaration line, which `body` drops) | the join now carries `raw_body` and `annotations` alongside `body` |
| the `fields` scope did not exist | `SpoonExtract` emitted methods and constructors only. The two commonest places to declare order-dependence — a `private static final Map<..> CACHE = new HashMap<>()` and a `static { }` block — were both invisible | `SpoonExtract` now emits `kind: field` records, and merges static blocks into one `<clinit>` record per class, which joins directly against the `<clinit>` JaCoCo reports |
| fixtures could only be guessed from method names, and inherited ones never found | no annotation list and no superclass link in the model | `annotations`, `superclass` and `interfaces` are emitted per record; the extractor walks the superclass chain |

Coverage had a fifth gap of the same kind: `jacococli` was given `target/classes`
only, so nothing recorded whether a `@Before` fixture actually ran. `module_roots`
now includes `target/test-classes` and `src/test/java`.

Old runs are not silently rescored on scopes they never collected. The extractor
re-resolves everything from the Spoon model, and reports
`fields_available = "MISSING (model predates field extraction)"` on a model
written before these changes — `runs2` is entirely in that state and needs
re-running for the fields scope.

### 7.2 The first result, on the 57 pairs already collected

| scope | sides flagged |
| --- | --- |
| test body | 12 / 115 (10.4%) |
| fixtures | 8 / 115 (7.0%) |
| production closure | **114 / 115 (99.1%)** |

At production-closure scope the liberal tier-1 flag is saturated: `uc.hash_container`,
`uc.map_set_type`, `uc.unordered_iter`, `uc.list_container`, `uc.index_access`,
`uc.to_sequence` and `uc.sequence_assert` each fire on 100% of sides, and this is
not the pretty-print artefact above — it survives on the raw source. And the flag
is identical before and after the fix on **57 of 57 pairs**.

Both facts point the same way. A hazard token in the executed closure carries no
information, which is the claim investigation 3 exists to test — but it also means
tier 1 cannot be a filter at this scope, and everything rests on the reachability
step narrowing 138 executed methods down to the ones a verdict can actually depend
on.

### 7.3 Speed: what `test-compile` would and would not buy

Measured on `google/TestParameterInjector` (`junit4`), warm `~/.m2`:

| shape | time |
| --- | --- |
| build point: `-DskipTests install -am`, cold `target/` | 13.7 s |
| build point: `-DskipTests test-compile -am`, cold `target/` | 10.6 s |
| per test: `prepare-agent test` (the lifecycle phase) | 11.3 s, then 8.6 s |
| per test: `prepare-agent test` with `-o` | 9.1 s, then 8.2 s |
| per test: `prepare-agent surefire:test` (the goal alone) | 7.9 s, then **7.2 s** |
| per test: the goal with `-o` | 7.7 s, then 7.5 s |

All four per-test shapes produced a byte-identical `jacoco.exec` (31,732 bytes).

`test-compile` is the wrong lever. It saves about 3 s, once per build point, and
it breaks the per-test invocation: those run `-pl <module>` without `-am` and so
resolve sibling modules out of `~/.m2`, which only `install` populates.

The lever is the per-test invocation, because that is what a build point pays 49
times on FlakeBench. Replacing the `test` lifecycle phase with the `surefire:test`
goal skips resources, compile and test-compile against a tree that is already
built: **8.6 s → 7.2 s here**, and the margin grows with module size. It is tried
first and not trusted blindly — invoking the goal from the CLI picks up surefire's
plugin-level `<configuration>` but not settings inside a named `<execution>`, so
the runner keeps it only when surefire reports `Tests run: > 0`, and otherwise
falls back to the lifecycle phase and then to the `-DargLine` shape. `--no-fast-test`
disables it. Offline mode was measured and dropped: it saves little once warm and
adds a failure mode when a plugin is not yet cached.
