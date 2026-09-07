  public void set(String name, String value) {
    set(name, value, null);
  }
  public Path getLocalPathForWrite(String pathStr, 
      Configuration conf) throws IOException {
    return getLocalPathForWrite(pathStr, SIZE_UNKNOWN, conf);
  }
  public static boolean isContextValid(String contextCfgItemName) {
    synchronized (contexts) {
      return contexts.containsKey(contextCfgItemName);
    }
  }
  public static void removeContext(String contextCfgItemName) {
    synchronized (contexts) {
      contexts.remove(contextCfgItemName);
    }
  }