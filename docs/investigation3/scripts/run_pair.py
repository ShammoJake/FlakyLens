#!/usr/bin/env python3
"""Collect before/after evidence for one pair from pairs.csv.

    python run_pair.py --pair-id P0123 [--out runs] [--pairs ../pairs.csv]
                       [--tools tools] [--side both|before|after] [--keep]

For each side it checks out the commit, builds the module, runs the single flaky
test under a JaCoCo agent, turns the exec file into coverage XML, extracts the
executed methods, runs Spoon over the sources, and joins the two.

Layout produced (one directory per pair, under the master --out directory):

    <out>/<pair_id>__<slug>__<Class.method>/
        meta.json                  pair row, resolved refs, per-step status, timings
        before/  after/
            checkout.log build.log test.log report.log spoon.log
            jacoco.exec  coverage.xml
            executed_methods.csv       covered methods, with a nesting column
            spoon_methods.json         every method Spoon can see, with bodies
            executed_with_bodies.json  the join — the actual product
            test_method.json           the flaky test method itself
            source/                    the checkout (deleted unless --keep)
        summary.json               before-vs-after counts

Design notes, all learned the hard way:

  * The test is expected to FAIL on the before side — it is a flaky test at its
    flaky commit. A non-zero exit from `mvn test` is therefore not an error here;
    the check is whether jacoco.exec was written.
  * JaCoCo is attached by invoking the plugin's prepare-agent goal from the command
    line rather than by rewriting every pom.xml, which is what NOD-Test-Repair's
    modify-project.sh does. If a project pins surefire's argLine so prepare-agent's
    is ignored, we retry once with an explicit -DargLine override.
  * Quality gates (enforcer, rat, checkstyle, license, javadoc, gpg) are skipped.
    They are gates, not build steps, and their failures say nothing about whether
    the code compiles.
  * core.longpaths is set on every checkout. Without it, large Apache-family repos
    check out incomplete on Windows and report no error at all.
  * Spoon runs even when the build fails, because it needs sources only. A pair can
    therefore yield static evidence with no coverage, and meta.json records that
    rather than discarding the pair.
"""
import argparse
import csv
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN = os.name == "nt"


# --------------------------------------------------------------------------- util

def quote(cmd):
    if IS_WIN:
        return subprocess.list2cmdline(cmd)
    import shlex
    return " ".join(shlex.quote(c) for c in cmd)


def run(cmd, cwd=None, log=None, timeout=900, env=None):
    """Run a command, tee-ing to a log file. Returns (rc, tail_of_output)."""
    started = time.time()
    e = dict(os.environ)
    if env:
        e.update(env)
    try:
        p = subprocess.run(quote(cmd), cwd=cwd, shell=True, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=e)
        out = p.stdout.decode("utf-8", "replace")
        rc = p.returncode
    except subprocess.TimeoutExpired as ex:
        out = (ex.stdout or b"").decode("utf-8", "replace") + f"\n*** TIMEOUT after {timeout}s\n"
        rc = 124
    if log:
        with open(log, "w", encoding="utf-8") as f:
            f.write("$ " + quote(cmd) + "\n\n")
            f.write(out)
            f.write(f"\n\n*** rc={rc} elapsed={time.time() - started:.1f}s\n")
    return rc, out[-4000:]


def first_error(text):
    for line in text.splitlines():
        if "BUILD FAILURE" in line or line.startswith("[ERROR]"):
            return line.strip()[:300]
    return ""


def sanitize(s, n=80):
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)[:n]


def pair_dirname(row):
    """Short on purpose. Windows caps a path at 260 characters, and git creates
    files several levels below the checkout root, so a descriptive directory name
    makes `git init` itself fail — silently, with 'not a git repository' surfacing
    later at fetch time. pair_id is the real key; the rest is only for the eye."""
    repo = row["project_slug"].rsplit("/", 1)[-1]
    cls = row["test_class"].rsplit(".", 1)[-1]
    return "{}__{}__{}.{}".format(row["pair_id"], sanitize(repo, 18),
                                  sanitize(cls, 22), sanitize(row["test_method"], 18))


def _force_writable(func, path, _exc):
    """git writes its pack files read-only, and Windows refuses to unlink those.
    Clear the read-only bit and retry the operation that failed."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def rmtree_hard(path, attempts=3):
    """Remove a checkout, and say whether it worked.

    shutil.rmtree(ignore_errors=True) leaves files behind when a JVM still holds a
    handle, and reports success anyway; a leftover working tree then makes the next
    checkout fail with 'untracked working tree files would be overwritten'. This
    retries, clears read-only bits, and never raises — the caller decides what a
    failed cleanup means."""
    for _ in range(attempts):
        if not os.path.exists(path):
            return True
        try:
            try:
                shutil.rmtree(path, onexc=_force_writable)       # Python >= 3.12
            except TypeError:
                shutil.rmtree(path, onerror=_force_writable)     # older
        except Exception:
            pass
        if not os.path.exists(path):
            return True
        time.sleep(1.0)
    return not os.path.exists(path)


# ------------------------------------------------------------------- ref handling

def gh_pr(owner_repo, number):
    """Ask gh for one PR. Used only when pr_meta.csv has not been built."""
    try:
        p = subprocess.run(["gh", "api", f"repos/{owner_repo}/pulls/{number}"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        if p.returncode != 0:
            return None
        import json as _j
        return _j.loads(p.stdout)
    except Exception:
        return None


def resolve_after_refs(row, use_gh=False):
    """Candidate git refs for the 'after' side, in the order to try them.

    Order matters and was got wrong at first. `refs/pull/<n>/merge` is GitHub's
    synthetic test-merge, and GitHub DELETES it when a PR closes — every merged
    PR we tried fell straight through to `/head`. `/head` is the author's branch
    tip: not what landed if the maintainer squashed or rebased, and missing any
    base-branch movement since the branch point. `merge_commit_sha`, from
    resolve_prs.py, is the commit that actually landed, so it goes first."""
    kind = row["after_type"]
    if kind == "fixed_sha":
        return [row["after_ref"].strip()], "fixed_sha", None
    if kind == "pr":
        # A resolved commit beats any ref guess, and it is also the ONLY thing that
        # works for the handful of IDoFT rows whose "PR Link" is a /commit/ URL
        # rather than a /pull/ one — so check it before parsing a PR number.
        merge_sha = (row.get("merge_commit_sha") or "").strip()
        m = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", row["after_ref"])
        if not merge_sha and m and use_gh:
            pr = gh_pr(m.group(1), m.group(2))
            if pr and pr.get("merged"):
                merge_sha = pr.get("merge_commit_sha") or ""
        if merge_sha:
            refs = [merge_sha]
            if m:
                refs.append(f"refs/pull/{m.group(2)}/head")
            return refs, "merge_commit", None
        if not m:
            return [], "", ("after_ref is neither a PR link nor a resolved commit: "
                            + row["after_ref"])
        n = m.group(2)
        return [f"refs/pull/{n}/merge", f"refs/pull/{n}/head"], "pr_ref_guess", None
    return [], "", f"after_type={kind!r} has no git ref (tool patch); not supported yet"


def resolve_before_refs(row, mode):
    """Candidate git refs for the 'before' side.

    Two defensible choices, and they are not equivalent:

      idoft         `SHA Detected` — the commit at which the flakiness was observed.
                    Can predate the repair by years, so the pair differs by the
                    repair PLUS everything else that landed in between.
      merge-parent  the merge commit's first parent — the tree immediately before
                    the repair. A minimal pair, and the construction ReproFlake
                    uses independently (its jsondoc zip is named for 16d42fd, which
                    is exactly the first parent of that PR's merge commit).

    `minimal_pair` says whether the parent is trustworthy: yes for a true merge,
    yes for a single-commit squash, no for a multi-commit rebase where the last
    replayed commit's parent is another commit from the same PR.

    auto prefers merge-parent when it is trustworthy and falls back to idoft, and
    the choice is recorded per side so a mixed corpus stays auditable."""
    parent = (row.get("merge_parent_sha") or "").strip()
    minimal = (row.get("minimal_pair") or "").strip() == "yes"
    idoft = (row.get("before_sha") or "").strip()
    if mode == "idoft":
        return ([idoft] if idoft else []), "idoft"
    if mode == "merge-parent":
        return ([parent] if parent else []), "merge_parent"
    if parent and minimal:
        return [parent], "merge_parent"
    return ([idoft] if idoft else []), "idoft"


def checkout(url, refs, dest, log, timeout, require_pom=True):
    """Shallow-fetch one of `refs` into `dest`.

    `require_pom` is the Maven pipeline's sanity check — a tree with no pom.xml
    at the root cannot be built by anything downstream, so failing here is
    better than failing three steps later. It has to be switchable, because the
    Spoon-only pass needs no build system at all: FlakeBench includes Gradle
    projects (swankjesse/dex, androidx), and rejecting them for a missing pom
    would drop source trees Spoon reads perfectly well.
    """
    if os.path.exists(dest) and not rmtree_hard(dest):
        return None, f"could not clear previous checkout at {dest}"
    os.makedirs(dest, exist_ok=True)
    rc, out = run(["git", "init", "-q", "."], cwd=dest, timeout=120)
    if rc != 0 or not os.path.isdir(os.path.join(dest, ".git")):
        return None, ("git init failed (path too long?) len={} rc={} {}"
                      .format(len(dest), rc, out[-200:]))
    run(["git", "config", "core.longpaths", "true"], cwd=dest, timeout=60)
    # core.autocrlf is true by default on Windows (it is set globally AND
    # system-wide on this machine), so every checkout silently rewrites LF to
    # CRLF. Two consequences, both bad: projects with a line-ending checkstyle
    # rule fail the build for a reason that has nothing to do with their code —
    # that was 24 of the first 24 build failures — and `raw_body` would carry
    # CRLF that is not in the upstream source we claim to be analysing.
    run(["git", "config", "core.autocrlf", "false"], cwd=dest, timeout=60)
    run(["git", "config", "core.eol", "lf"], cwd=dest, timeout=60)
    for ref in refs:
        rc, _ = run(["git", "fetch", "-q", "--depth", "1", url, ref],
                    cwd=dest, log=log, timeout=timeout)
        if rc == 0:
            rc2, out = run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=dest, timeout=600)
            if rc2 != 0:
                return None, "checkout failed: " + out[-300:]
            if not require_pom or os.path.isfile(os.path.join(dest, "pom.xml")):
                return ref, None
            return None, "checked out but no pom.xml at root"
    return None, "none of the refs could be fetched: " + ",".join(refs)


# --------------------------------------------------------------------- maven steps

# IDoFT names a parameterised test instance `foo[ARRAY]`. Maven's -Dtest selector
# accepts that, but no Java method is called it, so anything resolving the method
# in a source model has to strip the suffix first.
BRACKET = re.compile(r"\[.*\]$")

# Gates, not build steps. Their failures say nothing about whether the code
# compiles, and dependency-check in particular fails on any machine that cannot
# reach nvd.nist.gov — which looked exactly like a broken build on the first run.
GATE_SKIPS = ["-Dmaven.javadoc.skip=true", "-Denforcer.skip=true", "-Dgpg.skip=true",
              "-Drat.skip=true", "-Dcheckstyle.skip=true", "-Dlicense.skip=true",
              "-Dspotbugs.skip=true", "-Dpmd.skip=true", "-Danimal.sniffer.skip=true",
              "-Ddependency-check.skip=true", "-Dmaven.source.skip=true",
              "-Dforbiddenapis.skip=true", "-Djapicmp.skip=true",
              "-Drevapi.skip=true", "-Dmaven.site.skip=true"]


MAVEN_REPO = []          # filled from --maven-repo; empty means the default ~/.m2
# A JVM with no -Xmx claims a quarter of physical RAM. At --jobs 2 that is a
# Maven JVM, a forked surefire JVM and a Spoon JVM per worker, which on a 14 GB
# machine is enough for the OS to start killing processes — it killed the first
# sweep after 24 pairs. Both are bounded, and --jobs is documented accordingly.
XMX = {"maven": "1536m", "spoon": "2g", "fork": "1g"}

# Windows defaults the JVM's file.encoding to the ANSI codepage (cp1252 here).
# maven-compiler-plugin 3.11 writes its incremental-build state through that
# codec and dies with "Error while storing the mojo status: Input length = 1" on
# any source tree containing non-representable characters — fastjson2's test
# resources do, and that failed 6 consecutive pairs at ~500s each before anyone
# looked at the message. Forcing UTF-8 is also simply correct: we are reading
# these sources as UTF-8 everywhere else in the pipeline.
JVM_ENCODING = "-Dfile.encoding=UTF-8 -Dsun.jnu.encoding=UTF-8"


def maven_env():
    return {"MAVEN_OPTS": "-Xmx" + XMX["maven"] + " " + JVM_ENCODING}


def mvn_build(src, module, log, timeout):
    cmd = ["mvn", "-B", "-pl", module, "-am", "-DskipTests", "install"] + GATE_SKIPS + MAVEN_REPO
    rc, out = run(cmd, cwd=src, log=log, timeout=timeout,
                  env=maven_env())
    return rc, first_error(out)


TESTS_RUN = re.compile(r"Tests run:\s*(\d+)")


def tests_actually_ran(out):
    """True if surefire reported at least one executed test.

    A jacoco.exec is produced even when surefire selects nothing, so file
    existence alone cannot tell "ran the test" from "ran no tests at all".
    """
    return any(int(n) > 0 for n in TESTS_RUN.findall(out or ""))


def mvn_test_with_jacoco(src, module, test_class, test_method, exec_file,
                         jacoco_version, agent_jar, log, timeout, fast=True):
    """Run exactly one test with coverage. Returns (rc, note, used_fallback).

    Three shapes are tried in order, each a fallback for a way the previous one
    can fail on a real project:

      1. `surefire:test` — the goal alone, no lifecycle. The build point already
         compiled main and test classes, so re-running resources/compile/
         test-compile for every test on that commit is pure overhead. Measured on
         google/TestParameterInjector with a warm target/: 8.6s for the lifecycle
         phase against 7.2s for the goal, same jacoco.exec to the byte. The
         saving grows with module size, and at 49 tests per build point on
         FlakeBench it is paid 49 times.
         It is tried first, not adopted blindly: invoking the goal from the CLI
         picks up the plugin's `<configuration>` but NOT settings that live
         inside a named `<execution>`, so a project that configures surefire
         there would silently run a differently-configured test. That is why
         "surefire reported tests run > 0" gates it rather than "a file exists".
      2. the `test` lifecycle phase — correct everywhere, just slower.
      3. `-DargLine` — for a project that pins argLine itself and so discards the
         one prepare-agent sets.
    """
    sel = f"{test_class.rsplit('.', 1)[-1]}#{test_method}"
    common = [f"-Dtest={sel}", f"-Djacoco.destFile={exec_file}",
              "-DfailIfNoTests=false",
              "-Dsurefire.failIfNoSpecifiedTests=false"] + GATE_SKIPS + MAVEN_REPO
    agent = f"org.jacoco:jacoco-maven-plugin:{jacoco_version}:prepare-agent"

    def produced():
        return os.path.isfile(exec_file) and os.path.getsize(exec_file) > 0

    if fast:
        goal = ["mvn", "-B", "-pl", module, agent, "surefire:test"] + common
        rc, out = run(goal, cwd=src, log=log + ".goal", timeout=timeout,
                      env=maven_env())
        if produced() and tests_actually_ran(out):
            return rc, "surefire:test goal", False
        if produced():
            os.remove(exec_file)          # nothing ran; do not keep a stale exec

    base = ["mvn", "-B", "-pl", module, agent, "test"] + common
    rc, out = run(base, cwd=src, log=log, timeout=timeout,
                  env=maven_env())
    if produced():
        return rc, "test lifecycle", False

    # prepare-agent sets the argLine property; a project that pins surefire's own
    # argLine silently discards it. Override directly and try once more.
    fb = ["mvn", "-B", "-pl", module, "test", f"-Dtest={sel}",
          f"-DargLine=-javaagent:{agent_jar}=destfile={exec_file}",
          "-DfailIfNoTests=false", "-Dsurefire.failIfNoSpecifiedTests=false"] + GATE_SKIPS + MAVEN_REPO
    rc, out = run(fb, cwd=src, log=log + ".fallback", timeout=timeout,
                  env=maven_env())
    if os.path.isfile(exec_file) and os.path.getsize(exec_file) > 0:
        return rc, "used -DargLine fallback", True
    return rc, first_error(out) or "no jacoco.exec produced", True


def module_roots(src, include_tests=True):
    """(classfile dirs, source dirs) over every module that actually built.

    `target/test-classes` is included by default. Leaving it out meant the report
    covered production code only, so nothing recorded whether a @Before fixture or
    a test helper actually ran on this test — and "the fixture that seeds the
    HashMap executed" is exactly the kind of fact the reachability step needs.
    JaCoCo is happy to instrument both; the cost is a larger XML.
    """
    classes, sources = [], []
    for dirpath, dirnames, _ in os.walk(src):
        if ".git" in dirpath:
            continue
        if os.path.basename(dirpath) == "target":
            dirnames[:] = []                                  # do not descend
            base = os.path.dirname(dirpath)
            if os.path.isdir(os.path.join(dirpath, "classes")):
                classes.append(os.path.join(dirpath, "classes"))
                sm = os.path.join(base, "src", "main", "java")
                if os.path.isdir(sm):
                    sources.append(sm)
            if include_tests and os.path.isdir(os.path.join(dirpath, "test-classes")):
                classes.append(os.path.join(dirpath, "test-classes"))
                st = os.path.join(base, "src", "test", "java")
                if os.path.isdir(st):
                    sources.append(st)
    return classes, sources


def jacoco_report(src, exec_file, xml_out, cli_jar, log, timeout):
    classes, sources = module_roots(src)
    if not classes:
        return 1, "no target/classes anywhere: the build produced nothing", [], []
    cmd = ["java", "-jar", cli_jar, "report", exec_file]
    for c in classes:
        cmd += ["--classfiles", c]
    for s in sources:
        cmd += ["--sourcefiles", s]
    cmd += ["--xml", xml_out]
    rc, out = run(cmd, cwd=src, log=log, timeout=timeout)
    return rc, ("" if rc == 0 else out[-300:]), classes, sources


# ---------------------------------------------------------------------- one side

def do_side(row, side, url, refs, side_dir, tools, args):
    st = {"side": side, "refs_tried": refs, "steps": {}}
    os.makedirs(side_dir, exist_ok=True)
    src = os.path.abspath(os.path.join(side_dir, "source"))
    module = row["module_path"] or "."
    t0 = time.time()

    ref, err = checkout(url, refs, src, os.path.join(side_dir, "checkout.log"),
                        args.timeout_checkout)
    st["steps"]["checkout"] = {"ok": ref is not None, "ref": ref, "error": err}
    if ref is None:
        st["status"] = "checkout_failed"
        st["seconds"] = round(time.time() - t0, 1)
        return st

    # --- build first, but treat its failure as non-fatal: Spoon needs sources only
    #     and still yields the static half of the evidence.
    rc_build, build_err = mvn_build(src, module,
                                    os.path.join(side_dir, "build.log"), args.timeout_build)
    st["steps"]["build"] = {"ok": rc_build == 0, "rc": rc_build, "error": build_err}

    # --- Spoon over the SAME source roots the coverage report will span. Scoping it
    #     to the target module alone leaves every covered upstream-module method
    #     unmatched: on the first XChange run that was 31 of 62 non-synthetic rows.
    #     When the build failed there are no target/ dirs to enumerate, so fall back
    #     to the module's own sources.
    spoon_roots = []
    _, built_sources = module_roots(src)
    spoon_roots.extend(built_sources)
    for rel in (os.path.join(module, "src", "test", "java"),
                os.path.join(module, "src", "main", "java")):
        p = os.path.join(src, rel)
        if os.path.isdir(p) and p not in spoon_roots:
            spoon_roots.append(p)
    spoon_json = os.path.join(side_dir, "spoon_methods.json")
    if spoon_roots:
        cp = open(tools["SPOON_CP_FILE"], encoding="utf-8").read().strip()
        rc, out = run(["java", "-Xmx" + XMX["spoon"], "-cp", cp,
                       os.path.join(HERE, "SpoonExtract.java"),
                       spoon_json] + spoon_roots,
                      cwd=src, log=os.path.join(side_dir, "spoon.log"),
                      timeout=args.timeout_spoon)
        n = 0
        if os.path.isfile(spoon_json):
            try:
                n = len(json.load(open(spoon_json, encoding="utf-8")))
            except Exception:
                n = -1
        st["steps"]["spoon"] = {"ok": rc == 0 and n > 0, "methods": n,
                                "roots": [os.path.relpath(r, src) for r in spoon_roots]}
    else:
        st["steps"]["spoon"] = {"ok": False, "methods": 0,
                                "error": f"no src/main|test/java under module {module!r}"}

    # the flaky test method itself, pulled straight out of the Spoon model
    if os.path.isfile(spoon_json):
        try:
            ms = json.load(open(spoon_json, encoding="utf-8"))
            short = row["test_class"].rsplit(".", 1)[-1]
            hits = [m for m in ms
                    if m["method"] == row["test_method"]
                    and (m["qualified_class"] == row["test_class"]
                         or m["simple_class"] == short)]
            json.dump(hits, open(os.path.join(side_dir, "test_method.json"), "w",
                                 encoding="utf-8"), indent=1)
            st["steps"]["test_method_found"] = len(hits) > 0
        except Exception as ex:
            st["steps"]["test_method_found"] = False
            st["steps"]["test_method_error"] = str(ex)

    # coverage needs a build; static evidence has already been collected above
    if rc_build != 0:
        st["status"] = "build_failed"
        st["seconds"] = round(time.time() - t0, 1)
        return finish_side(st, side_dir, src, args)

    # --- single test under the agent
    exec_file = os.path.abspath(os.path.join(side_dir, "jacoco.exec"))
    rc, note, fb = mvn_test_with_jacoco(
        src, module, row["test_class"], row["test_method"], exec_file,
        tools["JACOCO_VERSION"], tools["JACOCO_AGENT"],
        os.path.join(side_dir, "test.log"), args.timeout_test)
    have_exec = os.path.isfile(exec_file) and os.path.getsize(exec_file) > 0
    # rc != 0 is expected on the before side: the test is flaky at this commit.
    st["steps"]["test"] = {"ok": have_exec, "rc": rc, "note": note,
                           "argline_fallback": fb,
                           "test_passed": rc == 0}
    if not have_exec:
        st["status"] = "no_coverage"
        st["seconds"] = round(time.time() - t0, 1)
        return finish_side(st, side_dir, src, args)

    # --- coverage xml + executed methods
    xml_out = os.path.abspath(os.path.join(side_dir, "coverage.xml"))
    rc, err, classes, sources = jacoco_report(
        src, exec_file, xml_out, tools["JACOCO_CLI"],
        os.path.join(side_dir, "report.log"), args.timeout_report)
    st["steps"]["report"] = {"ok": rc == 0, "error": err,
                             "classfile_dirs": len(classes), "sourcefile_dirs": len(sources)}
    if rc != 0:
        st["status"] = "report_failed"
        st["seconds"] = round(time.time() - t0, 1)
        return finish_side(st, side_dir, src, args)

    cov_csv = os.path.join(side_dir, "executed_methods.csv")
    rc, out = run([sys.executable, os.path.join(HERE, "collect_coverage.py"), xml_out, cov_csv],
                  timeout=600)
    st["steps"]["collect_coverage"] = {"ok": rc == 0, "summary": out.strip().splitlines()[-1:]}

    # --- join
    if os.path.isfile(cov_csv) and os.path.isfile(spoon_json):
        rc, out = run([sys.executable, os.path.join(HERE, "join_spoon_coverage.py"),
                       cov_csv, spoon_json,
                       os.path.join(side_dir, "executed_with_bodies.json")], timeout=600)
        st["steps"]["join"] = {"ok": rc == 0, "summary": out.strip().splitlines()[-1:]}

    st["status"] = "ok"
    st["seconds"] = round(time.time() - t0, 1)
    return finish_side(st, side_dir, src, args)


def finish_side(st, side_dir, src, args):
    if not args.keep and os.path.isdir(src):
        st["source_removed"] = rmtree_hard(src)
        st["source_kept"] = False
    else:
        st["source_kept"] = True
    json.dump(st, open(os.path.join(side_dir, "status.json"), "w", encoding="utf-8"), indent=1)
    return st


# --------------------------------------------------------------------------- main

def load_tools(tools_dir):
    env_file = os.path.join(tools_dir, "tools.env")
    if not os.path.isfile(env_file):
        sys.exit(f"missing {env_file} — run setup_tools.sh first")
    t = {}
    for line in open(env_file, encoding="utf-8"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            t[k] = v
    # tools.env can carry a shell-flavoured path (/c/... under Git Bash) that this
    # interpreter cannot open. Fall back to the same basename inside tools_dir.
    for k in ("JACOCO_AGENT", "JACOCO_CLI", "SPOON_CP_FILE"):
        if k in t and not os.path.isfile(t[k]):
            alt = os.path.join(os.path.abspath(tools_dir), os.path.basename(t[k]))
            if os.path.isfile(alt):
                t[k] = alt
            else:
                sys.exit(f"{k} not found: {t[k]!r} (also tried {alt!r}) — rerun setup_tools.sh")
    return t


def counts(side_dir):
    p = os.path.join(side_dir, "executed_with_bodies.json")
    if not os.path.isfile(p):
        return {}
    d = json.load(open(p, encoding="utf-8"))
    return {
        "executed_methods": len(d),
        "anonymous": sum(1 for m in d if m["is_anonymous"]),
        "matched": sum(1 for m in d if m["match_level"] != "unmatched"),
        "with_body": sum(1 for m in d if m["body"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair-id", required=True)
    ap.add_argument("--pairs", default=os.path.join(HERE, "..", "pairs.csv"))
    ap.add_argument("--out", default="runs")
    ap.add_argument("--tools", default=os.path.join(HERE, "tools"))
    ap.add_argument("--side", choices=["both", "before", "after"], default="both")
    ap.add_argument("--keep", action="store_true", help="keep the checkouts")
    ap.add_argument("--force", action="store_true", help="redo a pair that already has meta.json")
    ap.add_argument("--before", choices=["auto", "idoft", "merge-parent"], default="auto",
                    help="which commit is the before side; see resolve_before_refs")
    ap.add_argument("--xmx-maven", default=XMX["maven"])
    ap.add_argument("--xmx-spoon", default=XMX["spoon"])
    ap.add_argument("--maven-repo", default="",
                    help="local Maven repository to use instead of ~/.m2; point it at "
                         "a roomy drive if the default one's disk is tight")
    ap.add_argument("--resolve-pr", action="store_true",
                    help="call gh for the merge commit when pairs.csv has no "
                         "merge_commit_sha (slower; prefer running resolve_prs.py once)")
    ap.add_argument("--timeout-checkout", type=int, default=900)
    ap.add_argument("--timeout-build", type=int, default=1800)
    ap.add_argument("--timeout-test", type=int, default=900)
    ap.add_argument("--timeout-report", type=int, default=600)
    ap.add_argument("--timeout-spoon", type=int, default=900)
    args = ap.parse_args()

    # Absolute from here down. jacococli and Spoon are invoked with cwd=<checkout>,
    # so any relative path built from the launch directory resolves to nothing —
    # and jacococli reports that as a plain FileNotFoundException.
    args.out = os.path.abspath(args.out)

    XMX["maven"], XMX["spoon"] = args.xmx_maven, args.xmx_spoon
    if args.maven_repo:
        MAVEN_REPO.append("-Dmaven.repo.local=" + os.path.abspath(args.maven_repo))

    rows = {r["pair_id"]: r for r in csv.DictReader(open(args.pairs, encoding="utf-8"))}
    if args.pair_id not in rows:
        sys.exit(f"no such pair_id: {args.pair_id}")
    row = rows[args.pair_id]
    tools = load_tools(args.tools)

    pair_dir = os.path.join(args.out, pair_dirname(row))
    if IS_WIN and len(pair_dir) > 120:
        print(f"warning: pair directory path is {len(pair_dir)} chars; on Windows a "
              f"deep checkout under it may exceed MAX_PATH. Use a shorter --out.")
    meta_path = os.path.join(pair_dir, "meta.json")
    if os.path.isfile(meta_path) and not args.force:
        print(f"{args.pair_id}: already done ({meta_path}); --force to redo")
        return 0
    os.makedirs(pair_dir, exist_ok=True)

    after_refs, after_kind, after_err = resolve_after_refs(row, use_gh=args.resolve_pr)
    before_refs, before_kind = resolve_before_refs(row, args.before)
    meta = {"pair": row, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "tools": tools, "sides": {}}

    url = row["project_url"]
    plan = []
    if args.side in ("both", "before"):
        plan.append(("before", before_refs, before_kind))
    if args.side in ("both", "after"):
        plan.append(("after", after_refs, after_kind))
    meta["ref_kinds"] = {"before": before_kind, "after": after_kind}

    for side, refs, kind in plan:
        if not refs:
            meta["sides"][side] = {"side": side, "status": "unsupported",
                                   "error": after_err or "no ref available"}
            print(f"{args.pair_id} {side}: unsupported ({meta['sides'][side]['error']})")
            continue
        print(f"{args.pair_id} {side}: {refs[0]}  [{kind}]")
        st = do_side(row, side, url, refs, os.path.join(pair_dir, side), tools, args)
        st["ref_kind"] = kind
        meta["sides"][side] = st
        print(f"{args.pair_id} {side}: {st['status']} in {st.get('seconds')}s")

    summary = {s: counts(os.path.join(pair_dir, s)) for s in ("before", "after")}
    b, a = summary.get("before") or {}, summary.get("after") or {}
    if b and a:
        summary["delta"] = {k: a.get(k, 0) - b.get(k, 0) for k in b}
    json.dump(summary, open(os.path.join(pair_dir, "summary.json"), "w", encoding="utf-8"), indent=1)

    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    meta["overall"] = "ok" if all(
        meta["sides"].get(s, {}).get("status") == "ok" for s, _, _ in plan) else "partial"
    json.dump(meta, open(meta_path, "w", encoding="utf-8"), indent=1)
    print(f"{args.pair_id}: {meta['overall']} -> {pair_dir}")
    return 0 if meta["overall"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
