    public void close() throws IOException {
      
      if (out != null) {
        out.close();
      }
    }
    public void write(int b) throws IOException {
      out.write(b);
      position++;
      if (statistics != null) {
        statistics.incrementBytesWritten(1);
      }
    }
  public long getLen() {
    return length;
  }
  public String getOwner() {
    return owner;
  }
  public String toString() {
    
    
    StringBuilder buffer = new StringBuilder();
    if (uri.getScheme() != null) {
      buffer.append(uri.getScheme())
          .append("");
    }
    if (uri.getAuthority() != null) {
      buffer.append("")
          .append(uri.getAuthority());
    }
    if (uri.getPath() != null) {
      String path = uri.getPath();
      if (path.indexOf('')==0 &&
          hasWindowsDrive(path) &&                
          uri.getScheme() == null &&              
          uri.getAuthority() == null)             
        path = path.substring(1);                 
      buffer.append(path);
    }
    if (uri.getFragment() != null) {
      buffer.append("")
          .append(uri.getFragment());
    }
    return buffer.toString();
  }
  public String getShortUserName() {
    return user.getShortName();
  }
  public FSDataOutputStream append(final Path f, final int bufferSize,
      final Progressable progress) throws IOException {
    statistics.incrementWriteOps(1);
    storageStatistics.incrementOpCounter(OpType.APPEND);

    final HttpOpParam.Op op = PostOpParam.Op.APPEND;
    return new FsPathOutputStreamRunner(op, f, bufferSize,
        new BufferSizeParam(bufferSize)
    ).run();
  }
  public FSDataOutputStream create(final Path f, final FsPermission permission,
      final boolean overwrite, final int bufferSize, final short replication,
      final long blockSize, final Progressable progress) throws IOException {
    statistics.incrementWriteOps(1);
    storageStatistics.incrementOpCounter(OpType.CREATE);

    final FsPermission modes = applyUMask(permission);
    final HttpOpParam.Op op = PutOpParam.Op.CREATE;
    return new FsPathOutputStreamRunner(op, f, bufferSize,
        new PermissionParam(modes.getMasked()),
        new UnmaskedPermissionParam(modes.getUnmasked()),
        new OverwriteParam(overwrite),
        new BufferSizeParam(bufferSize),
        new ReplicationParam(replication),
        new BlockSizeParam(blockSize)
    ).run();
  }
  public FileStatus getFileStatus(Path f) throws IOException {
    statistics.incrementReadOps(1);
    storageStatistics.incrementOpCounter(OpType.GET_FILE_STATUS);
    return getHdfsFileStatus(f).makeQualified(getUri(), f);
  }
  public Path getHomeDirectory() {
    if (cachedHomeDirectory == null) {
      final HttpOpParam.Op op = GetOpParam.Op.GETHOMEDIRECTORY;
      try {
        String pathFromDelegatedFS = new FsPathResponseRunner<String>(op, null){
          @Override
          String decodeResponse(Map<?, ?> json) throws IOException {
            return JsonUtilClient.getPath(json);
          }
        }   .run();

        cachedHomeDirectory = new Path(pathFromDelegatedFS).makeQualified(
            this.getUri(), null);

      } catch (IOException e) {
        LOG.error("", e);
        cachedHomeDirectory = new Path("" + ugi.getShortUserName())
            .makeQualified(this.getUri(), null);
      }
    }
    return cachedHomeDirectory;
  }
  public URI getUri() {
    return this.uri;
  }