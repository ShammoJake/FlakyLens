import pandas as pd, subprocess, re, os, json
HD=os.environ.get("HADOOP_MIRROR","")  # blobless partial clone, see sources/MANIFEST.md
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..","sources")
os.makedirs(OUT,exist_ok=True)
TAGS=["sha_cceb68f","sha_5537c6b","sha_14cd969"]
def g(a): return subprocess.run(["git"]+a,cwd=HD,capture_output=True,text=True,errors="replace")
trees={t:g(["ls-tree","-r","--name-only",t]).stdout.splitlines() for t in TAGS}
f=pd.read_csv('docs/investigation/all_flaky_with_preds.csv')
h=f[f.project=='apache_hadoop'].reset_index(drop=True)
rows=[]
for _,r in h.iterrows():
    tn=r.test_name; cls=tn.split('.')[0] if '.' in tn else None
    meth=tn.split('.')[-1]
    cands=[]
    for t in TAGS:
        for p in trees[t]:
            if cls and p.endswith('/'+cls+'.java'): cands.append((t,p))
            elif not cls and p.endswith('.java') and '/test/' in p: pass
    hit=None
    for t,p in cands:
        src=g(["cat-file","blob",f"{t}:{p}"]).stdout
        if re.search(r'\b'+re.escape(meth)+r'\s*\(', src):
            hit=(t,p,src); break
    if hit:
        t,p,src=hit
        fn=f"{cls}__{meth}.java".replace('/','_')
        open(os.path.join(OUT,fn),'w',encoding='utf-8',errors='replace').write(src)
        rows.append(dict(test=tn,truth=r.truth,pred=r.pred,wrong=bool(r.wrong),sha=t,path=p,file=fn,loc=src.count('\n')+1))
    else:
        rows.append(dict(test=tn,truth=r.truth,pred=r.pred,wrong=bool(r.wrong),sha=None,path=None,file=None,loc=0))
pd.DataFrame(rows).to_csv(os.path.join(OUT,'located.csv'),index=False)
d=pd.DataFrame(rows)
print(d[['test','truth','pred','wrong','sha','loc']].to_string())
print('unresolved:',d.path.isna().sum())
