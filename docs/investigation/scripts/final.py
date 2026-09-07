import pandas as pd, os
SP=os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
cf=pd.read_csv(os.path.join(SP,'hadoop_class_features.csv'))
# manual verified evidence location per test (read from source)
EV={
 'TestDFSIO.testWrite':('class fixture + static field','@BeforeClass builds static MiniDFSCluster and calls testWrite(); comment "required for other tests"'),
 'TestDFSIO.testRead':('class fixture + static field','reads files written by testWrite() in @BeforeClass; static cluster, no @Before'),
 'TestDFSIO.testReadSkip':('class fixture + sibling test','shared static bench.getConf() key test.io.skip.size set by sibling test'),
 'TestDFSIO.testReadBackward':('class fixture + sibling test','same shared static conf key'),
 'TestDFSIO.testReadRandom':('class fixture + sibling test','writes test.io.skip.size=0 into shared static bench'),
 'TestPathData.testToFile':('class fixture','@Before mutates shared cached FileSystem working dir; static TEST_ROOT_DIR'),
 'TestPathData.testCwdContents':('same-file helper + fixture','helper sortedString() calls Arrays.sort, refuting UC; OD from @Before working dir'),
 'TestPathData.testQualifiedUriContents':('same-file helper + fixture','same'),
 'TestPathData.testUnqualifiedUriContents':('same-file helper + fixture','same'),
 'TestPeerCache.testEviction':('production callee (depth 1)','PeerCache starts Daemon thread, Thread.sleep(expiryPeriod), all methods synchronized'),
 'TestPeerCache.testExpiry':('production callee (depth 1)','same'),
 'TestPeerCache.testAddAndRetrieve':('production callee (depth 1)','same'),
 'TestDelegationTokenForProxyUser.testWebHdfsDoAs':('class fixture + static field','5 static fields; @BeforeClass sets token lifetime, FileSystem.setDefaultUri, ProxyUsers.refresh'),
 'TestDelegationTokenForProxyUser.testDelegationTokenWithRealUser':('class fixture + static field','same'),
 'TestMetricsSystemImpl.testInitFirstVerifyCallBacks':('helper + production callee','helper indexes recs.get(0); MetricsSystemImpl uses Maps.newHashMap() and iterates values()'),
 'TestRPCCompatibility.testVersion2ClientVersion2Server':('class fixture','@Before calls ProtocolSignature.resetCache(), a global static cache; static server/addr/conf'),
 'TestDelegationToken.testDelegationTokenSecretManager':('production callee (depth 1)','startThreads() spawns expiry thread over synchronized shared state in AbstractDelegationTokenSecretManager'),
}
cf['evidence_location']=cf.test.map(lambda t: EV.get(t,('body only' ,''))[0] if t in EV else ('body / n-a'))
cf['evidence_detail']=cf.test.map(lambda t: EV.get(t,('',''))[1])
cf.to_csv(os.path.join(SP,'hadoop_evidence_table.csv'),index=False)
o=cf[cf.status=='ok']
w=o[o.wrong]; r=o[~o.wrong]
print('resolved',len(o),'wrong',len(w),'right',len(r))
print('\nwrong tests: evidence location counts')
print(w.evidence_location.value_counts())
print('\nevidence outside test body:',len(w),'of',len(w))
print('\nshared_cluster wrong/right:',w.shared_cluster.sum(),'/',r.shared_cluster.sum())
print('static_mutable>0 wrong/right: %d/%d  %d/%d'%((w.static_mutable>0).sum(),len(w),(r.static_mutable>0).sum(),len(r)))
print('median body_lines wrong %.0f right %.0f'%(w.body_lines.median(),r.body_lines.median()))
print('\nunresolved:',(cf.status=='UNRESOLVED').sum())
print(cf[cf.status=='UNRESOLVED'][['test','truth','pred']].to_string())
