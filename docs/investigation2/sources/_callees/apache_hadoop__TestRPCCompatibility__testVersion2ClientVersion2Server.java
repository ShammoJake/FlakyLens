  public static InetSocketAddress getConnectAddress(Server server) {
    return getConnectAddress(server.getListenerAddress());
  }
  public T getProxy() {
    return proxy;
  }
  public synchronized boolean isMethodSupported(String methodName,
                                   Class<?>... parameterTypes)
  throws IOException {
    if (!supportServerMethodCheck) {
      return true;
    }
    Method method;
    try {
      method = protocol.getDeclaredMethod(methodName, parameterTypes);
    } catch (SecurityException e) {
      throw new IOException(e);
    } catch (NoSuchMethodException e) {
      throw new IOException(e);
    }
    if (!serverMethodsFetched) {
      fetchServerMethods(method);
    }
    if (serverMethods == null) { 
      return true;
    }
    return serverMethods.contains(
        Integer.valueOf(ProtocolSignature.getFingerprint(method)));
  }
    public Builder(Configuration conf) {
      this.conf = conf;
    }
  public static <T> ProtocolProxy<T> getProtocolProxy(Class<T> protocol,
                                long clientVersion,
                                InetSocketAddress addr, Configuration conf,
                                SocketFactory factory) throws IOException {
    UserGroupInformation ugi = UserGroupInformation.getCurrentUser();
    return getProtocolProxy(protocol, clientVersion, addr, ugi, conf, factory);
  }
  public synchronized void start() {
    responder.start();
    listener.start();
    handlers = new Handler[handlerCount];
    
    for (int i = 0; i < handlerCount; i++) {
      handlers[i] = new Handler(i);
      handlers[i].start();
    }
  }