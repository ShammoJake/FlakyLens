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
  public File toFile() {
    if (!(fs instanceof LocalFileSystem)) {
       throw new IllegalArgumentException("" + path);
    }
    return ((LocalFileSystem)fs).pathToFile(path);
  }