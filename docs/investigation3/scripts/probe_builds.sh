#!/usr/bin/env bash
# Check whether IDoFT build points actually compile, which is the precondition
# for per-test JaCoCo coverage.
#
#   bash probe_builds.sh [DATA_DIR] [N] [PARALLEL]
#       DATA_DIR  default ./data      (needs sha_reach.tsv and bp.tsv)
#       N         default 10          sample size, or "all" for every reachable point
#       PARALLEL  default 4
#
# Writes DATA_DIR/build_probe.tsv:
#   BUILD_OK | BUILD_FAIL(n) | FETCH_FAIL | NO_POM  <tab> id <tab> url <tab> sha
#   <tab> module <tab> category [<tab> first error line]
#
# Two things this probe established (2026-09-06, JDK 11, sample of 10):
#
#   1. core.longpaths is mandatory on Windows. Without it, apache/cloudstack,
#      apache/hadoop and apache/cxf all check out incomplete with "Filename too
#      long" and no non-zero exit — a silent failure, not an error.
#   2. With it set, 9 of 10 compiled. The one failure was apache/hadoop, on
#      exec-maven-plugin's convert-ms-winutils goal, which needs a native Windows
#      toolchain. That is a platform failure, not dependency rot.
#
# `compile` is deliberately weaker than what the pipeline finally needs: a build
# that compiles may still fail to run the flaky test. Use test-compile or a real
# single-test run for the authoritative sweep.

set -uo pipefail
DATA="${1:-data}"
N="${2:-10}"
PAR="${3:-4}"
export GIT_TERMINAL_PROMPT=0
export MAVEN_OPTS="${MAVEN_OPTS:--Xmx2g}"

python - "$DATA" "$N" <<'PY'
import sys, os, random
DATA, N = sys.argv[1], sys.argv[2]
mods = {}
for line in open(os.path.join(DATA, 'bp.tsv'), encoding='utf-8'):
    p = line.rstrip('\n').split('\t')
    mods[(p[1], p[2])] = p[5].split('|')[0]
ok = [l.rstrip('\n').split('\t') for l in open(os.path.join(DATA, 'sha_reach.tsv'), encoding='utf-8')
      if l.startswith('OK\t')]
if N != 'all':
    random.seed(7)
    ok = random.sample(ok, min(int(N), len(ok)))
with open(os.path.join(DATA, 'probe_list.tsv'), 'w', newline='\n') as f:
    for _, i, url, sha, cat, _t in ok:
        f.write(f"{i}\t{url}\t{sha}\t{mods.get((url, sha), '.')}\t{cat}\n")
print('probing', len(ok), 'build points')
PY

cat > "$DATA/_buildchk.sh" <<'SH'
IFS=$'\t' read -r id url sha mod cat <<< "$1"
d="$BPROBE/$id"
rm -rf "$d"; mkdir -p "$d"
git init -q "$d"
git -C "$d" config core.longpaths true          # mandatory, see header
if ! git -C "$d" fetch -q --depth 1 "$url" "$sha" >/dev/null 2>&1; then
  printf 'FETCH_FAIL\t%s\t%s\t%s\t%s\t%s\n' "$id" "$url" "$sha" "$mod" "$cat"; rm -rf "$d"; exit
fi
git -C "$d" checkout -q FETCH_HEAD 2>/dev/null
if [ ! -f "$d/pom.xml" ]; then
  printf 'NO_POM\t%s\t%s\t%s\t%s\t%s\n' "$id" "$url" "$sha" "$mod" "$cat"; rm -rf "$d"; exit
fi
log="$BPROBE/$id.log"
# The skips are quality gates, not build steps; leaving them on adds failures
# that say nothing about whether the code compiles.
if timeout 900 mvn -B -q -f "$d/pom.xml" -pl "$mod" -am -DskipTests \
     -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dgpg.skip=true \
     -Drat.skip=true -Dcheckstyle.skip=true -Dlicense.skip=true \
     compile > "$log" 2>&1; then
  printf 'BUILD_OK\t%s\t%s\t%s\t%s\t%s\n' "$id" "$url" "$sha" "$mod" "$cat"
else
  r=$?
  err=$(grep -m1 -E 'BUILD FAILURE|ERROR\]' "$log" | head -c 160)
  printf 'BUILD_FAIL(%s)\t%s\t%s\t%s\t%s\t%s\t%s\n' "$r" "$id" "$url" "$sha" "$mod" "$cat" "$err"
fi
rm -rf "$d"
SH

export BPROBE="$DATA/_bprobe"
mkdir -p "$BPROBE"
xargs -d '\n' -P "$PAR" -I{} bash "$DATA/_buildchk.sh" {} < "$DATA/probe_list.tsv" \
  > "$DATA/build_probe.tsv" 2>&1
rm -f "$DATA/_buildchk.sh"

echo
cut -f1 "$DATA/build_probe.tsv" | sort | uniq -c
