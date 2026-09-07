  public Path makeQualified(Path path) {
    checkPath(path);
    return path.makeQualified(this.getUri(), this.getWorkingDirectory());
  }
  public String toString() {
    return uriToString(uri, inferredSchemeFromPath);
  }