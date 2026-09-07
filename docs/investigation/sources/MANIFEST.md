# Extracted Hadoop sources

Test classes for the 27 Hadoop flaky tests that resolved, pulled from
`apache/hadoop` at the commits pinned in `FlakeBench/filtered_tests_with_owner_sha.csv`.
Plus `PeerCache.java`, the one production class read at depth 1.

Files are verbatim upstream copies. Names are `<Class>__<method>.java`, so the
same class appears once per test analysed.

| File | Upstream path | Commit |
|---|---|---|
| `TestDFSIO__testRead.java` | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/fs/TestDFSIO.java` | `cceb68f` |
| `TestDFSIO__testReadBackward.java` | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/fs/TestDFSIO.java` | `cceb68f` |
| `TestDFSIO__testReadRandom.java` | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/fs/TestDFSIO.java` | `cceb68f` |
| `TestDFSIO__testReadSkip.java` | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/fs/TestDFSIO.java` | `cceb68f` |
| `TestDFSIO__testWrite.java` | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/test/java/org/apache/hadoop/fs/TestDFSIO.java` | `cceb68f` |
| `TestDelegationToken__testDelegationTokenSecretManager.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/security/token/delegation/TestDelegationToken.java` | `cceb68f` |
| `TestDelegationTokenForProxyUser__testDelegationTokenWithRealUser.java` | `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/security/TestDelegationTokenForProxyUser.java` | `cceb68f` |
| `TestDelegationTokenForProxyUser__testWebHdfsDoAs.java` | `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/security/TestDelegationTokenForProxyUser.java` | `cceb68f` |
| `TestDelegationTokenRenewer__testAddRemoveRenewAction.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/TestDelegationTokenRenewer.java` | `cceb68f` |
| `TestLocalDirAllocator__testRemoveContext.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/TestLocalDirAllocator.java` | `cceb68f` |
| `TestMetricsSystemImpl__testInitFirstVerifyCallBacks.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/metrics2/impl/TestMetricsSystemImpl.java` | `cceb68f` |
| `TestModTime__testModTime.java` | `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/TestModTime.java` | `cceb68f` |
| `TestPathData__testCwdContents.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/shell/TestPathData.java` | `cceb68f` |
| `TestPathData__testQualifiedUriContents.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/shell/TestPathData.java` | `cceb68f` |
| `TestPathData__testToFile.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/shell/TestPathData.java` | `cceb68f` |
| `TestPathData__testUnqualifiedUriContents.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/shell/TestPathData.java` | `cceb68f` |
| `TestPathData__testWithDirStringAndConf.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/shell/TestPathData.java` | `cceb68f` |
| `TestPathData__testWithStringAndConfForBuggyPath.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/shell/TestPathData.java` | `cceb68f` |
| `TestPeerCache__testAddAndRetrieve.java` | `hadoop-hdfs-project/hadoop-hdfs-client/src/test/java/org/apache/hadoop/hdfs/TestPeerCache.java` | `cceb68f` |
| `TestPeerCache__testEviction.java` | `hadoop-hdfs-project/hadoop-hdfs-client/src/test/java/org/apache/hadoop/hdfs/TestPeerCache.java` | `cceb68f` |
| `TestPeerCache__testExpiry.java` | `hadoop-hdfs-project/hadoop-hdfs-client/src/test/java/org/apache/hadoop/hdfs/TestPeerCache.java` | `cceb68f` |
| `TestRMContainerAllocator__testSimple.java` | `hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/test/java/org/apache/hadoop/mapreduce/v2/app/rm/TestRMContainerAllocator.java` | `cceb68f` |
| `TestRPCCompatibility__testVersion2ClientVersion2Server.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/ipc/TestRPCCompatibility.java` | `5537c6b` |
| `TestSecurityUtil__testBuildDTServiceName.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/security/TestSecurityUtil.java` | `cceb68f` |
| `TestSecurityUtil__testBuildTokenServiceSockAddr.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/security/TestSecurityUtil.java` | `cceb68f` |
| `TestUnderReplicatedBlocks__testSetrepIncWithUnderReplicatedBlocks.java` | `hadoop-hdfs-project/hadoop-hdfs/src/test/java/org/apache/hadoop/hdfs/server/blockmanagement/TestUnderReplicatedBlocks.java` | `5537c6b` |
| `TestWritableName__testSetName.java` | `hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/io/TestWritableName.java` | `cceb68f` |
| `PeerCache.java` | `hadoop-hdfs-project/hadoop-hdfs-client/src/main/java/org/apache/hadoop/hdfs/PeerCache.java` | `cceb68f` |

## Not resolved

Six of the 33 Hadoop flaky tests have no source here.

| Test | Reason |
|---|---|
| `TestHftpFileSystem.testHftpDefaultPorts` | class absent from all three commits |
| `TestHftpFileSystem.testHftpCustomDefaultPorts` | class absent from all three commits |
| `TestHftpFileSystem.testHftpCustomUriPortWithDefaultPorts` | class absent from all three commits |
| `TestBlockFixer.testGeneratedBlock` | class absent from all three commits |
| `TestFairScheduler.testContinuousScheduling` | class present, method absent |
| `testPendingAndInvalidate` | benchmark row carries no class name |

## How they were fetched

```
git init && git remote add origin https://github.com/apache/hadoop
git fetch --depth 1 --filter=blob:none origin <sha>
git cat-file blob FETCH_HEAD:<path>
```

Blobless partial fetch, 2.4 MB total for three commits. No working checkout.
`located.csv` records the test-to-file-to-commit mapping the scripts produced.
