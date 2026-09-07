  public static EndPoint of(String name) {
    return new EndPoint(name);
  }
  public static InputField of(String origin, String name) {
    return new InputField(origin, name);
  }
  default void addAccess(ProgramRunId run, DatasetId datasetInstance, AccessType accessType) {
    addAccess(run, datasetInstance, accessType, null);
  }
  public ProgramRunId run(String run) {
    return new ProgramRunId(new ApplicationId(getNamespace(), getApplication(), getVersion()), type, program, run);
  }
  public ProgramId getParent() {
    return new ProgramId(new ApplicationId(getNamespace(), getApplication(), getVersion()), getType(), getProgram());
  }
  public static RunId generate() {
    return new RunIdImpl(generateUUIDForTime(System.currentTimeMillis()));
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
  default void registerAll(Iterable<? extends EntityId> users, DatasetId datasetId) {
    for (EntityId user : users) {
      register(user, datasetId);
    }
  }