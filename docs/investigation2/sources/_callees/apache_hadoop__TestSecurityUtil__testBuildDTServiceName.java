  public void setBoolean(String name, boolean value) {
    set(name, Boolean.toString(value));
  }
  public static String buildDTServiceName(URI uri, int defPort) {
    String authority = uri.getAuthority();
    if (authority == null) {
      return null;
    }
    InetSocketAddress addr = NetUtils.createSocketAddr(authority, defPort);
    return buildTokenService(addr).toString();
   }
  public static void setConfiguration(Configuration conf) {
    LOG.info("");
    setConfigurationInternal(conf);
  }