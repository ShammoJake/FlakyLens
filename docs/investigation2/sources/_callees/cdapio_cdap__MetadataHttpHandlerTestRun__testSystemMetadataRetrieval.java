  public String getEntityName() {
    return getApplication();
  }
  public ProgramId mr(String program) {
    return new ProgramId(this, ProgramType.MAPREDUCE, program);
  }
  public ServiceId service(String program) {
    return new ServiceId(this, program);
  }
  public ProgramId spark(String program) {
    return new ProgramId(this, ProgramType.SPARK, program);
  }
  public ProgramId worker(String program) {
    return new ProgramId(this, ProgramType.WORKER, program);
  }
  public WorkflowId workflow(String program) {
    return new WorkflowId(this, program);
  }
  public String getName() {
    return name;
  }
  public String getVersion() {
    return version;
  }
  public String getEntityName() {
    return getDataset();
  }
  public Map<String, String> getProperties() {
    return properties;
  }
  public static boolean isProfileAllowed(ProgramType programType) {
    return programType == ProgramType.WORKFLOW
      || programType == ProgramType.MAPREDUCE
      || programType == ProgramType.SPARK
      || programType == ProgramType.WORKER;
  }
  public static Builder builder() {
    return new Builder();
  }
  public static <T> void waitFor(T desiredValue, Callable<T> callable, long timeout, TimeUnit timeoutUnit,
                                 long sleepDelay, TimeUnit sleepDelayUnit, @Nullable String message)
    throws TimeoutException, InterruptedException, ExecutionException {

    long sleepDelayMs = sleepDelayUnit.toMillis(sleepDelay);
    long startTime = System.currentTimeMillis();
    long timeoutMs = timeoutUnit.toMillis(timeout);
    T actualValue = null;
    while (System.currentTimeMillis() - startTime < timeoutMs) {
      try {
        actualValue = callable.call();
        if (Objects.equals(desiredValue, actualValue)) {
          return;
        }
      } catch (Exception e) {
        throw new ExecutionException(e);
      }
      Thread.sleep(sleepDelayMs);
    }
    if (message == null) {
      message = String.format("", desiredValue, actualValue);
    }
    throw new TimeoutException(message);
  }