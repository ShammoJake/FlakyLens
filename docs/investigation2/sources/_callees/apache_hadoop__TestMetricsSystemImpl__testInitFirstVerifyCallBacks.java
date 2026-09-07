  public static void shutdown() {
    INSTANCE.shutdownInstance();
  }
  public synchronized void publishMetricsNow() {
    if (sinks.size() > 0) {
      publishMetrics(sampleMetrics(), true);
    }    
  }
  T register(String name, String desc, T source) {
    MetricsSourceBuilder sb = MetricsAnnotations.newSourceBuilder(source);
    final MetricsSource s = sb.build();
    MetricsInfo si = sb.info();
    String name2 = name == null ? si.name() : name;
    final String finalDesc = desc == null ? si.description() : desc;
    final String finalName = 
        DefaultMetricsSystem.sourceName(name2, !monitoring);
    allSources.put(finalName, s);
    LOG.debug(finalName +""+ finalDesc);
    if (monitoring) {
      registerSource(finalName, finalDesc, s);
    }
    
    
    register(finalName, new AbstractCallback() {
      @Override public void postStart() {
        registerSource(finalName, finalDesc, s);
      }
    });
    return source;
  }
  synchronized void registerSink(String name, String desc, MetricsSink sink) {
    checkNotNull(config, "");
    MetricsConfig conf = sinkConfigs.get(name);
    MetricsSinkAdapter sa = conf != null
        ? newSink(name, desc, sink, conf)
        : newSink(name, desc, sink, config.subset(SINK_KEY));
    sinks.put(name, sa);
    sa.start();
    LOG.info(""+ name);
  }
  public synchronized boolean shutdown() {
    LOG.debug(""+ refCount);
    if (refCount <= 0) {
      LOG.debug("", new Throwable());
      return true; 
    }
    if (--refCount > 0) return false;
    if (monitoring) {
      try { stop(); }
      catch (Exception e) {
        LOG.warn("", e);
      }
    }
    allSources.clear();
    allSinks.clear();
    callbacks.clear();
    namedCallbacks.clear();
    if (mbeanName != null) {
      MBeans.unregister(mbeanName);
      mbeanName = null;
    }
    LOG.info(prefix +"");
    return true;
  }
  public synchronized void start() {
    checkNotNull(prefix, "");
    if (monitoring) {
      LOG.warn(prefix +"",
               new MetricsException(""));
      return;
    }
    for (Callback cb : callbacks) cb.preStart();
    for (Callback cb : namedCallbacks.values()) cb.preStart();
    configure(prefix);
    startTimer();
    monitoring = true;
    LOG.info(prefix +"");
    for (Callback cb : callbacks) cb.postStart();
    for (Callback cb : namedCallbacks.values()) cb.postStart();
  }
  public synchronized void stop() {
    if (!monitoring && !DefaultMetricsSystem.inMiniClusterMode()) {
      LOG.warn(prefix +"",
               new MetricsException(""));
      return;
    }
    if (!monitoring) {
      
      LOG.info(prefix +"");
      return;
    }
    for (Callback cb : callbacks) cb.preStop();
    for (Callback cb : namedCallbacks.values()) cb.preStop();
    LOG.info(""+ prefix +"");
    stopTimer();
    stopSources();
    stopSinks();
    clearConfigs();
    monitoring = false;
    LOG.info(prefix +"");
    for (Callback cb : callbacks) cb.postStop();
    for (Callback cb : namedCallbacks.values()) cb.postStop();
  }