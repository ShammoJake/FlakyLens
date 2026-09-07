#!/usr/bin/env bash
# Check whether every IDoFT "before" commit is still fetchable.
#
#   bash probe_shas.sh [DATA_DIR]        (default: ./data)
#
# Writes DATA_DIR/sha_reach.tsv:  OK|NOSHA <tab> id <tab> url <tab> sha <tab> cat <tab> tests
#
# Method: a build point is a distinct (project URL, SHA Detected). For each one,
# init an empty repo and run a depth-1, blob-filtered fetch of that exact SHA.
# This is the real test — a repository being alive does not mean a decade-old SHA
# is still reachable from any ref.
#
# Result when this was run (2026-09-06): 417 of 432 OK. 12 of the 15 failures are
# wildfly/wildfly rows with sequential fabricated SHAs (...bb76f052 .. ...bb76f063).
#
# Note the core.longpaths setting: on Windows, checkouts of large Apache-family
# repositories silently produce an incomplete working tree without it.

set -uo pipefail
DATA="${1:-data}"
export GIT_TERMINAL_PROMPT=0

python - "$DATA" <<'PY'
import csv, collections, json, sys, os
DATA = sys.argv[1]
FIX = {'Accepted', 'DeveloperFixed', 'InspiredAFix'}
T = 'Fully-Qualified Test Name (packageName.ClassName.methodName)'
rows = [r for r in csv.DictReader(open(os.path.join(DATA, 'pr-data.csv'), encoding='utf-8'))
        if r['Status'].strip() in FIX and r['PR Link'].strip().startswith('http')]
bp = collections.OrderedDict()
for r in rows:
    k = (r['Project URL'].strip().rstrip('/'), r['SHA Detected'].strip())
    e = bp.setdefault(k, {'modules': set(), 'cats': collections.Counter(), 'tests': 0})
    e['modules'].add(r['Module Path'].strip() or '.')
    e['cats'][r['Category'].strip()] += 1
    e['tests'] += 1
# newline='\n' matters: CRLF here breaks the URLs when the shell reads them back
with open(os.path.join(DATA, 'bp.tsv'), 'w', newline='\n') as f:
    for i, ((u, s), e) in enumerate(bp.items()):
        f.write(f"{i}\t{u}\t{s}\t{e['cats'].most_common(1)[0][0]}\t{e['tests']}\t{'|'.join(sorted(e['modules']))}\n")
print('build points:', len(bp), '| distinct repos:', len({u for u, _ in bp}))
PY

cat > "$DATA/_fetchchk.sh" <<'SH'
IFS=$'\t' read -r id url sha cat tests mods <<< "$1"
d="$PROBE/$id"
rm -rf "$d"; mkdir -p "$d"
git init -q "$d"
git -C "$d" config core.longpaths true
if git -C "$d" fetch -q --depth 1 --filter=blob:none "$url" "$sha" 2>/dev/null; then
  printf 'OK\t%s\t%s\t%s\t%s\t%s\n' "$id" "$url" "$sha" "$cat" "$tests"
else
  printf 'NOSHA\t%s\t%s\t%s\t%s\t%s\n' "$id" "$url" "$sha" "$cat" "$tests"
fi
rm -rf "$d"
SH

export PROBE="$DATA/_probe"
mkdir -p "$PROBE"
xargs -d '\n' -P 12 -I{} bash "$DATA/_fetchchk.sh" {} < "$DATA/bp.tsv" > "$DATA/sha_reach.tsv" 2>/dev/null
rm -rf "$PROBE" "$DATA/_fetchchk.sh"

# Classify the failures, when gh is available. A failed fetch has two very
# different causes: the commit is absent from the repository altogether (a bad
# row in IDoFT), or it exists but is not reachable from any ref (history rewrite,
# force-push). Only the API can tell them apart, and the answer changes whether
# the row is worth chasing.
#
# Result on the 2026-09-06 run: all 15 failures came back HTTP 422 "No commit
# found for SHA" — every one absent, none merely unreachable. Twelve of them are
# wildfly/wildfly rows with sequential SHAs ...bb76f052 through ...bb76f063, which
# confirms those are fabricated entries rather than lost commits.
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  echo
  echo "classifying failures via gh..."
  : > "$DATA/sha_missing.tsv"
  grep '^NOSHA' "$DATA/sha_reach.tsv" | cut -f3,4 | while IFS=$'\t' read -r url sha; do
    slug="${url#https://github.com/}"
    if gh api "repos/$slug/commits/$sha" --jq .sha >/dev/null 2>&1; then
      printf 'unreachable\t%s\t%s\n' "$url" "$sha" >> "$DATA/sha_missing.tsv"
    else
      printf 'absent\t%s\t%s\n' "$url" "$sha" >> "$DATA/sha_missing.tsv"
    fi
  done
  cut -f1 "$DATA/sha_missing.tsv" | sort | uniq -c
fi

echo
cut -f1 "$DATA/sha_reach.tsv" | sort | uniq -c
