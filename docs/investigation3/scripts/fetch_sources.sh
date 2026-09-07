#!/usr/bin/env bash
# Download every raw input needed to rebuild pairs.csv.
#
#   bash fetch_sources.sh [DATA_DIR]      (default: ./data)
#
# Total download is a few MB. None of the large artifacts (ReproFlake zips,
# the 1.5 GB FlakeSync tarball) are needed to build the pair table — only their
# metadata, which is what this script fetches.
#
# See ../METHODOLOGY.md §2 for why each file is used.

set -euo pipefail
DATA="${1:-data}"
mkdir -p "$DATA"

IDOFT=https://raw.githubusercontent.com/TestingResearchIllinois/idoft/main
NODREPAIR=https://raw.githubusercontent.com/shanto-Rahman/NOD-Test-Repair/master
REPROFLAKE=https://anonymous.4open.science/api/repo/ReproFlake-C9E6/file

echo "== IDoFT =="
# pr-data.csv is the Maven file and the only one in scope. The other two are
# fetched purely so the exclusion in datasets.md §4 stays checkable.
curl -fsSL -o "$DATA/pr-data.csv" "$IDOFT/pr-data.csv"
curl -fsSL -o "$DATA/gr-data.csv" "$IDOFT/gr-data.csv"   # Gradle, out of scope
curl -fsSL -o "$DATA/py-data.csv" "$IDOFT/py-data.csv"   # Python, out of scope

echo "== FlakeSync subject list =="
# The list lives in NOD-Test-Repair, not in the 1.5 GB Zenodo artifact.
# Every row is comment-prefixed there; build_pairs.py strips the leading '#'.
curl -fsSL -o "$DATA/async_wait_coming_from_flakysync.csv" \
     "$NODREPAIR/data/async_wait_coming_from_flakysync.csv"

echo "== ReproFlake metadata =="
# test_config.csv gives the required JDK and a public Zenodo URL per subject.
# The two research-data files give the flaky SHA and the fixed SHA per subject,
# which is the actual before/after pair.
curl -fsSL -o "$DATA/rf_test_config.csv" "$REPROFLAKE/test_config.csv"
curl -fsSL -o "$DATA/rf_idoft.csv" "$REPROFLAKE/research-data/Reproducible_iDoFT_info.csv"
curl -fsSL -o "$DATA/rf_jira.csv"  "$REPROFLAKE/research-data/Reproducible_JIRA_info.csv"

echo "== ODRepair patch list =="
# The patch filenames are the fully-qualified test names, which is all we need
# to identify the subjects; the patch bodies are only needed to apply the repair.
# Prefer gh: authenticated it is 5,000 requests/hour against 60 anonymous, and that
# same limit is what makes resolve_prs.py possible at all.
ODR=repos/UT-SE-Research/ODRepair/contents/experiments/data/patches
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh api "$ODR" --jq '.[] | select(.name | endswith(".patch")) | .name' > "$DATA/odrepair_patches.txt"
else
  echo "   (gh unavailable - falling back to the anonymous API, 60 req/hr)"
  curl -fsSL "https://api.github.com/$ODR" \
    | python -c "import json,sys; print('\n'.join(x['name'] for x in json.load(sys.stdin) if x['name'].endswith('.patch')))" \
    > "$DATA/odrepair_patches.txt"
fi

echo
wc -l "$DATA"/*.csv "$DATA"/*.txt
