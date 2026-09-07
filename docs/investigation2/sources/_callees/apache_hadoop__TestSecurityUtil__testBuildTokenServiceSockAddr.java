  public void setBoolean(String name, boolean value) {
    set(name, Boolean.toString(value));
  }
  public static InetSocketAddress createSocketAddr(String target) {
    return createSocketAddr(target, -1);
  }
  public static Text buildTokenService(InetSocketAddress addr) {
    String host = null;
    if (useIpForTokenService) {
      if (addr.isUnresolved()) { 
        throw new IllegalArgumentException(
            new UnknownHostException(addr.getHostName())
        );
      }
      host = addr.getAddress().getHostAddress();
    } else {
      host = StringUtils.toLowerCase(addr.getHostName());
    }
    return new Text(host + "" + addr.getPort());
  }
  public static void setConfiguration(Configuration conf) {
    LOG.info("");
    setConfigurationInternal(conf);
  }