import pandas as pd, re, os
SP=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
F=os.path.join(SP,'sources')
loc=pd.read_csv(os.path.join(F,'located.csv'))

def parse(src):
    lines=src.split('\n'); methods=[]; ann=[]; i=0
    while i<len(lines):
        s=lines[i].strip()
        if s.startswith('@'): ann.append(s); i+=1; continue
        m=re.match(r'\s*(?:public|private|protected)[\w\s<>\[\],\.@]*?\s(\w+)\s*\(', lines[i])
        if m and not s.startswith('//') and not s.startswith('*'):
            name=m.group(1); depth=0; j=i; started=False
            while j<len(lines):
                depth+=lines[j].count('{')-lines[j].count('}')
                if '{' in lines[j]: started=True
                if started and depth<=0: break
                j+=1
            a=' '.join(ann)
            kind=('test' if '@Test' in a else 'beforeclass' if '@BeforeClass' in a
                  else 'afterclass' if '@AfterClass' in a else 'before' if '@Before' in a
                  else 'after' if '@After' in a else 'helper')
            methods.append(dict(kind=kind,name=name,src='\n'.join(lines[i:j+1])))
            ann=[]; i=j+1; continue
        ann=[]; i+=1
    covered=set()
    for m in methods:
        for l in m['src'].split('\n'): covered.add(l)
    fields=[l for l in lines if l not in covered and re.search(r'^\s*(?:private|protected|public|static|final)[^(){}=]*[\w>\]]\s+\w+\s*(=|;)',l) and 'class ' not in l]
    return methods,fields

MUT=r'(Map|List|Set|Multiset|Collection|StringBuilder|Atomic\w+|Cluster|MiniDFS|FileSystem|Configuration|Conf\b|File|Path|UserGroupInformation|Thread|Server|\[\])'
rows=[]
for _,r in loc.iterrows():
    if pd.isna(r.file):
        rows.append(dict(test=r.test,truth=r.truth,pred=r.pred,wrong=r.wrong,status='UNRESOLVED')); continue
    src=open(os.path.join(F,r.file),encoding='utf-8',errors='replace').read()
    ms,fields=parse(src)
    meth=r.test.split('.')[-1]
    body=next((m['src'] for m in ms if m['name']==meth), '')
    tests=[m for m in ms if m['kind']=='test']
    fixtures=[m for m in ms if m['kind'] in ('before','beforeclass','after','afterclass')]
    fixsrc='\n'.join(m['src'] for m in fixtures)
    bc='\n'.join(m['src'] for m in ms if m['kind']=='beforeclass')
    helpers={m['name']:m['src'] for m in ms if m['kind']=='helper'}
    fieldtxt='\n'.join(fields)
    statmut=[l.strip() for l in fields if re.search(r'\bstatic\b',l) and (not re.search(r'\bfinal\b',l) or re.search(MUT,l))]
    # sibling tests that reference a static field name
    statnames=set(re.findall(r'\b(\w+)\s*[;=]',' '.join(statmut)))
    sib=sum(1 for m in tests if m['name']!=meth and any(re.search(r'\b'+re.escape(n)+r'\s*[=.]',m['src']) for n in statnames if len(n)>2))
    # helpers actually invoked from body
    called=[h for h in helpers if re.search(r'\b'+re.escape(h)+r'\s*\(',body)]
    hsrc='\n'.join(helpers[h] for h in called)
    rows.append(dict(test=r.test,truth=r.truth,pred=r.pred,wrong=bool(r.wrong),status='ok',
      body_lines=len(body.split('\n')),
      static_mutable=len(statmut),
      beforeclass=int(bool(bc)),
      per_test_reset=int(any(m['kind']=='before' for m in ms)),
      fixture_calls_test=int(any(re.search(r'\b'+re.escape(t['name'])+r'\s*\(',bc) for t in tests)),
      shared_cluster=int(bool(re.search(r'MiniDFSCluster|MiniCluster|MiniYARN|MiniHDFS',fieldtxt+bc))),
      global_static_write=int(bool(re.search(r'(FileSystem\.setDefaultUri|System\.setProperty|\w+\.refresh\w*|setDefault\w*|\w+Provider\.set)',fixsrc+body))),
      sibling_touch_static=sib,
      helpers_called=len(called),
      helper_sorts=int(bool(re.search(r'Arrays\.sort|Collections\.sort|\.sorted\(|TreeSet|TreeMap',hsrc))),
      body_sorts=int(bool(re.search(r'Arrays\.sort|Collections\.sort|\.sorted\(|TreeSet|TreeMap',body))),
      n_tests=len(tests)))
d=pd.DataFrame(rows); d.to_csv(os.path.join(SP,'hadoop_class_features.csv'),index=False)
o=d[d.status=='ok']
pd.set_option('display.width',300)
print(o.drop(columns=['status']).to_string())
print('\n=== MEANS by wrong ===')
print(o.groupby('wrong')[['static_mutable','beforeclass','per_test_reset','fixture_calls_test','shared_cluster','global_static_write','sibling_touch_static','helper_sorts','body_lines']].mean().T)
