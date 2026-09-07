  public DatanodeInfo[] datanodeReport(DatanodeReportType type)
      throws IOException {
    checkOpen();
    try (TraceScope ignored = tracer.newScope("")) {
      return namenode.getDatanodeReport(type);
    }
  }
  public long getModificationTime() {
    return modification_time;
  }
  public void close() throws IOException {
    
    processDeleteOnExit();
    CACHE.remove(this.key, this);
  }
  public boolean delete(Path f) throws IOException {
    return delete(f, true);
  }
  public boolean exists(Path f) throws IOException {
    try {
      return getFileStatus(f) != null;
    } catch (FileNotFoundException e) {
      return false;
    }
  }
  public Path makeQualified(Path path) {
    checkPath(path);
    return path.makeQualified(this.getUri(), this.getWorkingDirectory());
  }
  public static boolean mkdirs(FileSystem fs, Path dir, FsPermission permission)
      throws IOException {
    
    boolean result = fs.mkdirs(dir);
    
    fs.setPermission(dir, permission);
    return result;
  }
  protected void rename(final Path src, final Path dst,
      final Rename... options) throws IOException {
    
    final FileStatus srcStatus = getFileLinkStatus(src);
    if (srcStatus == null) {
      throw new FileNotFoundException("" + src + "");
    }

    boolean overwrite = false;
    if (null != options) {
      for (Rename option : options) {
        if (option == Rename.OVERWRITE) {
          overwrite = true;
        }
      }
    }

    FileStatus dstStatus;
    try {
      dstStatus = getFileLinkStatus(dst);
    } catch (IOException e) {
      dstStatus = null;
    }
    if (dstStatus != null) {
      if (srcStatus.isDirectory() != dstStatus.isDirectory()) {
        throw new IOException("" + src + "" + dst
            + "");
      }
      if (!overwrite) {
        throw new FileAlreadyExistsException("" + dst
            + "");
      }
      
      if (dstStatus.isDirectory()) {
        FileStatus[] list = listStatus(dst);
        if (list != null && list.length != 0) {
          throw new IOException(
              "" + dst);
        }
      }
      delete(dst, false);
    } else {
      final Path parent = dst.getParent();
      final FileStatus parentStatus = getFileStatus(parent);
      if (parentStatus == null) {
        throw new FileNotFoundException("" + parent
            + "");
      }
      if (!parentStatus.isDirectory()) {
        throw new ParentNotDirectoryException("" + parent
            + "");
      }
    }
    if (!rename(src, dst)) {
      throw new IOException("" + src + "" + dst + "");
    }
  }