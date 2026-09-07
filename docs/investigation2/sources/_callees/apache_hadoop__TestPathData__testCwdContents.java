  public PathData[] getDirectoryContents() throws IOException {
    checkIfExists(FileTypeRequirement.SHOULD_BE_DIRECTORY);
    FileStatus[] stats = fs.listStatus(path);
    PathData[] items = new PathData[stats.length];
    for (int i=0; i < stats.length; i++) {
      
      String child = getStringForChildPath(stats[i].getPath());
      items[i] = new PathData(fs, child, stats[i]);
    }
    Arrays.sort(items);
    return items;
  }