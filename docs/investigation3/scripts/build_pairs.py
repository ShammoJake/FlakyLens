"""Build docs/investigation3/pairs.csv from the four pair sources.

Inputs are expected in the directory given by FLAKYLENS_DATA (default: ./data),
laid down by fetch_sources.sh, plus sha_reach.tsv from probe_shas.sh:

    pr-data.csv                          IDoFT, Maven
    rf_test_config.csv                   ReproFlake test_config.csv
    rf_idoft.csv                         ReproFlake research-data/Reproducible_iDoFT_info.csv
    rf_jira.csv                          ReproFlake research-data/Reproducible_JIRA_info.csv
    async_wait_coming_from_flakysync.csv FlakeSync subject list
    odrepair_patches.txt                 one ODRepair patch filename per line
    sha_reach.tsv                        output of probe_shas.sh
    pr_meta.csv                          OPTIONAL, output of resolve_prs.py — the
                                         commit each PR actually merged as, and its
                                         first parent. Without it the pr_* and
                                         merge_* columns are left empty and the
                                         runner falls back to guessing refs.

See METHODOLOGY.md for where each of these comes from and why.
"""
import csv, collections, os

DATA = os.environ.get('FLAKYLENS_DATA', 'data')
REPO = os.environ.get('FLAKYLENS_REPO', os.path.join(os.path.dirname(__file__), '..', '..', '..'))
OUT  = os.environ.get('FLAKYLENS_OUT') or os.path.join(os.path.dirname(__file__), '..', 'pairs.csv')
FB   = os.path.join(REPO, 'FlakeBench', 'FlakeBench_dataset.csv')


def d(name):
    return os.path.join(DATA, name)

FIX = {'Accepted', 'DeveloperFixed', 'InspiredAFix'}
T   = 'Fully-Qualified Test Name (packageName.ClassName.methodName)'


def slug(u):
    return u.strip().rstrip('/').replace('https://github.com/', '').lower()


def split_test(fq):
    fq = fq.strip().replace('#', '.')
    if '.' not in fq:
        return '', fq
    cls, meth = fq.rsplit('.', 1)
    return cls, meth


# FlakeBench label mapping; code follows FlakeBench's own numbering.
def to_flakebench(cat, source):
    """returns (label, code, confidence, candidates, note)"""
    c = cat.strip().split(';')[0].strip().upper()
    if c == 'ID':
        return ('unordered collections', 3, 'high', '',
                'NonDex-induced iteration order over hash containers or reflection')
    if c in ('OD', 'OD-VIC', 'OD-BRIT', 'BRITLE'):
        return ('test order dependency', 4, 'high', '', '')
    if c == 'NIO':
        return ('test order dependency', 4, 'medium', '',
                'non-idempotent-outcome: test pollutes its own state; FlakeBench has no '
                'distinct label, closest is order dependency')
    if c == 'NOD':
        if source == 'flakesync':
            return ('async wait', 0, 'high', '',
                    'FlakeSync subject set is async-specific by construction')
        return ('', None, 'ambiguous', 'async wait|concurrency',
                'IDoFT NOD does not separate async from concurrency; needs manual triage')
    if c == 'TD':
        return ('async wait', 0, 'medium', 'async wait|time',
                'ReproFlake timing-dependent in the FlakeRake sense, not clock or timezone')
    if c == 'TZD':
        return ('time', 2, 'high', '', '')
    return ('', None, 'unknown', '', 'source category is UD or unclassified')


idoft = [r for r in csv.DictReader(open(d('pr-data.csv'), encoding='utf-8'))
         if r['Status'].strip() in FIX and r['PR Link'].strip().startswith('http')]
idset = {(slug(r['Project URL']), r[T].strip().lower()) for r in idoft}

reach = {}
for line in open(d('sha_reach.tsv'), encoding='utf-8'):
    p = line.rstrip('\n').split('\t')
    if len(p) >= 4:
        reach[(p[2].strip().rstrip('/'), p[3].strip())] = (p[0] == 'OK')

rf_idoft = list(csv.DictReader(open(d('rf_idoft.csv'), encoding='utf-8')))
rf_jira  = list(csv.DictReader(open(d('rf_jira.csv'), encoding='utf-8')))
rf_cfg   = list(csv.DictReader(open(d('rf_test_config.csv'), encoding='utf-8')))

cfg_by_zip = {}
for r in rf_cfg:
    cfg_by_zip.setdefault(r['zip'].strip(), r)

rf_env = {}
for r in rf_idoft:
    k = (slug(r['Project (Github Link)']), r['Flaky Test Name'].strip().lower())
    z = r['Zip name'].strip()
    c = cfg_by_zip.get(z, {})
    rf_env[k] = dict(java=c.get('java', ''), zip=z, url=c.get('url', ''),
                     fixed_sha=r['Fixed commit SHA'].strip(),
                     polluter=r['Polluter/State-setter (For OD test only)'].strip(),
                     module=r['Module'].strip(), rf_type=r['Type'].strip())
for r in rf_jira:
    k = (slug(r['Project (Github Link)']), r['Flaky test name'].strip().lower())
    z = r['Zip name'].strip()
    c = cfg_by_zip.get(z, {})
    rf_env.setdefault(k, dict(java=c.get('java', ''), zip=z, url=c.get('url', ''),
                              fixed_sha=r['Fixed commit SHA'].strip(),
                              polluter=r['Polluter/State-setter (For OD test only)'].strip(),
                              module=(r.get('Module ') or r.get('Module') or '').strip(),
                              rf_type=r['Type'].strip()))

# Optional: what each PR actually merged as. Absent when gh was never run, in
# which case every merge_*/pr_* column stays empty and run_pair.py falls back to
# refs/pull/<n>/head — which is the author's branch tip, not what landed.
pr_meta = {}
_pm = d("pr_meta.csv")
if os.path.isfile(_pm):
    for r in csv.DictReader(open(_pm, encoding="utf-8")):
        pr_meta[r["pr_url"].strip()] = r
print("pr_meta.csv:", len(pr_meta), "PRs" if pr_meta else "(absent - run resolve_prs.py)")

PR_COLS = ["merge_commit_sha", "merge_parent_sha", "merge_kind", "minimal_pair",
           "pr_merged", "pr_merged_at", "pr_commits", "pr_changed_files",
           "pr_touch", "pr_files_java_main", "pr_files_java_test"]


def pr_fields(pr_url):
    m = pr_meta.get((pr_url or "").strip())
    if not m:
        return {c: "" for c in PR_COLS}
    # GitHub still returns a merge_commit_sha for a CLOSED-BUT-UNMERGED PR: it is
    # the last synthetic test-merge it computed, not a commit that ever landed on
    # the base branch. Checking that out would silently analyse a phantom tree, so
    # the column is blanked unless the PR really merged. pr_meta.csv keeps the raw
    # API answer; the filtering happens here, at the join.
    merged = m.get("merged", "") == "true"
    return {
        "merge_commit_sha": m.get("merge_commit_sha", "") if merged else "",
        "merge_parent_sha": m.get("merge_parent_sha", "") if merged else "",
        "merge_kind": m.get("merge_kind", ""),
        "minimal_pair": m.get("minimal_pair", ""),
        "pr_merged": m.get("merged", ""),
        "pr_merged_at": m.get("merged_at", ""),
        "pr_commits": m.get("pr_commits", ""),
        "pr_changed_files": m.get("changed_files", ""),
        "pr_touch": m.get("touch", ""),
        "pr_files_java_main": m.get("files_java_main", ""),
        "pr_files_java_test": m.get("files_java_test", ""),
    }


fb = collections.defaultdict(list)
for r in csv.DictReader(open(FB, encoding='utf-8')):
    fb[(r['project'].strip().lower().replace('_', '/'),
        r['test_name'].strip().lower())].append(r['label'])

rows = []
counter = [0]


def emit(**kw):
    counter[0] += 1
    kw['pair_id'] = 'P%04d' % counter[0]
    rows.append(kw)


def fb_lookup(sl, cls, meth):
    short = cls.rsplit('.', 1)[-1]
    hits = fb.get((sl, (short + '.' + meth).lower()), [])
    if not hits:
        return '', ''
    return 'yes', '|'.join(sorted(set(hits)))


# 1. IDoFT
for r in idoft:
    url = r['Project URL'].strip().rstrip('/')
    sl  = slug(url)
    sha = r['SHA Detected'].strip()
    fq  = r[T].strip()
    cls, meth = split_test(fq)
    cat = r['Category'].strip()
    lab, code, conf, cand, note = to_flakebench(cat, 'idoft')
    env = rf_env.get((sl, fq.lower()), {})
    infb, fblab = fb_lookup(sl, cls, meth)
    emit(source='idoft', tier='A', repair_author='developer',
         project_url=url, project_slug=sl,
         module_path=r['Module Path'].strip() or '.',
         test_class=cls, test_method=meth, fq_test=fq,
         before_sha=sha, after_type='pr', after_ref=r['PR Link'].strip(),
         source_category=cat, idoft_status=r['Status'].strip(),
         flakebench_label=lab, flakebench_category=code if code is not None else '',
         label_confidence=conf, label_candidates=cand, mapping_note=note,
         before_sha_reachable={True: 'yes', False: 'no'}.get(reach.get((url, sha)), 'unknown'),
         build_env='reproflake' if env else 'none',
         java_version=env.get('java', ''),
         reproflake_zip=env.get('zip', ''), reproflake_url=env.get('url', ''),
         reproflake_fixed_sha=env.get('fixed_sha', ''),
         polluter=env.get('polluter', ''),
         in_flakebench=infb, flakebench_existing_label=fblab,
         notes=r['Notes'].strip()[:200],
         **pr_fields(r['PR Link']))

# 2. ReproFlake net-new
for src, rlist, tname in (('idoft-src', rf_idoft, 'Flaky Test Name'),
                          ('jira-src',  rf_jira,  'Flaky test name')):
    for r in rlist:
        url = r['Project (Github Link)'].strip().rstrip('/')
        sl  = slug(url)
        fq  = r[tname].strip()
        if (sl, fq.lower()) in idset:
            continue
        cls, meth = split_test(fq)
        z = r['Zip name'].strip()
        c = cfg_by_zip.get(z, {})
        cat = r['Type'].strip()
        lab, code, conf, cand, note = to_flakebench(cat, 'reproflake')
        infb, fblab = fb_lookup(sl, cls, meth)
        emit(source='reproflake', tier='B', repair_author='developer',
             project_url=url, project_slug=sl,
             module_path=(r.get('Module') or r.get('Module ') or '.').strip() or '.',
             test_class=cls, test_method=meth, fq_test=fq,
             before_sha=r['Flaky commit SHA'].strip(),
             after_type='fixed_sha', after_ref=r['Fixed commit SHA'].strip(),
             source_category=cat, idoft_status='',
             flakebench_label=lab, flakebench_category=code if code is not None else '',
             label_confidence=conf, label_candidates=cand, mapping_note=note,
             before_sha_reachable='unknown',
             build_env='reproflake', java_version=c.get('java', ''),
             reproflake_zip=z, reproflake_url=c.get('url', ''),
             reproflake_fixed_sha=r['Fixed commit SHA'].strip(),
             polluter=r['Polluter/State-setter (For OD test only)'].strip(),
             in_flakebench=infb, flakebench_existing_label=fblab,
             notes='ReproFlake ' + src + '; container ' + r['Container Name'].strip())

# 3. FlakeSync
for line in open(d('async_wait_coming_from_flakysync.csv'), encoding='utf-8'):
    line = line.strip().lstrip('#')
    if not line:
        continue
    p = [x.strip() for x in line.split(',')]
    if len(p) < 4:
        continue
    sl, sha, mod, fq = p[0].lower(), p[1], p[2] or '.', p[3]
    cls, meth = split_test(fq)
    lab, code, conf, cand, note = to_flakebench('NOD', 'flakesync')
    infb, fblab = fb_lookup(sl, cls, meth)
    emit(source='flakesync', tier='C', repair_author='tool',
         project_url='https://github.com/' + p[0], project_slug=sl,
         module_path=mod, test_class=cls, test_method=meth,
         fq_test=fq.replace('#', '.'),
         before_sha=sha, after_type='tool_patch',
         after_ref='https://zenodo.org/records/10460139',
         source_category='NOD (async)', idoft_status='',
         flakebench_label=lab, flakebench_category=code, label_confidence=conf,
         label_candidates=cand, mapping_note=note,
         before_sha_reachable='unknown', build_env='none', java_version='',
         reproflake_zip='', reproflake_url='', reproflake_fixed_sha='', polluter='',
         in_flakebench=infb, flakebench_existing_label=fblab,
         notes='FlakeSync barrier-insertion repair; no merged developer fix exists')

# 4. ODRepair net-new
by_test = collections.defaultdict(list)
for r in idoft:
    by_test[r[T].strip().lower()].append(r)
for name in open(d('odrepair_patches.txt'), encoding='utf-8').read().split('\n'):
    name = name.strip()
    if not name.endswith('.patch'):
        continue
    fq = name[:-6]
    hits = by_test.get(fq.lower(), [])
    if any(h['Status'].strip() in FIX and h['PR Link'].strip().startswith('http') for h in hits):
        continue
    src = hits[0] if hits else None
    cls, meth = split_test(fq)
    url = src['Project URL'].strip().rstrip('/') if src else ''
    sl  = slug(url) if url else ''
    lab, code, conf, cand, note = to_flakebench('OD-Vic', 'odrepair')
    infb, fblab = fb_lookup(sl, cls, meth)
    emit(source='odrepair', tier='C', repair_author='tool',
         project_url=url, project_slug=sl,
         module_path=(src['Module Path'].strip() or '.') if src else '.',
         test_class=cls, test_method=meth, fq_test=fq,
         before_sha=src['SHA Detected'].strip() if src else '',
         after_type='tool_patch',
         after_ref='UT-SE-Research/ODRepair experiments/data/patches/' + name,
         source_category=(src['Category'].strip() if src else 'OD-Vic'),
         idoft_status=(src['Status'].strip() if src else ''),
         flakebench_label=lab, flakebench_category=code, label_confidence=conf,
         label_candidates=cand, mapping_note=note,
         before_sha_reachable='unknown', build_env='none', java_version='',
         reproflake_zip='', reproflake_url='', reproflake_fixed_sha='', polluter='',
         in_flakebench=infb, flakebench_existing_label=fblab,
         notes='ODRepair generated state-setter test; no merged developer fix')

COLS = ['pair_id', 'source', 'tier', 'repair_author', 'project_slug', 'project_url',
        'module_path', 'test_class', 'test_method', 'fq_test',
        'before_sha', 'before_sha_reachable', 'after_type', 'after_ref',
        'source_category', 'idoft_status',
        'flakebench_label', 'flakebench_category', 'label_confidence',
        'label_candidates', 'mapping_note',
        'build_env', 'java_version', 'reproflake_zip', 'reproflake_url',
        'reproflake_fixed_sha', 'polluter',
        'in_flakebench', 'flakebench_existing_label', 'notes'] + PR_COLS

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore')
    w.writeheader()
    for r in rows:
        w.writerow(r)

print('wrote', len(rows), 'rows ->', OUT)
print()
print('by source:', dict(collections.Counter(r['source'] for r in rows)))
print('by flakebench_label:', dict(collections.Counter(r['flakebench_label'] or '(unlabelled)' for r in rows)))
print('by confidence:', dict(collections.Counter(r['label_confidence'] for r in rows)))
print('build_env=reproflake:', sum(1 for r in rows if r['build_env'] == 'reproflake'))
print('java declared:', dict(collections.Counter(r['java_version'] for r in rows if r['java_version'])))
print('already in FlakeBench:', sum(1 for r in rows if r['in_flakebench'] == 'yes'))
if pr_meta:
    print('with merge_commit_sha:', sum(1 for r in rows if r.get('merge_commit_sha')))
    print('minimal_pair usable:  ', sum(1 for r in rows if r.get('minimal_pair') == 'yes'))
    print('pr_touch:             ',
          dict(collections.Counter(r.get('pr_touch') for r in rows if r.get('pr_touch'))))
print('FlakeBench existing labels for those:',
      dict(collections.Counter(r['flakebench_existing_label'] for r in rows if r['in_flakebench'] == 'yes')))
