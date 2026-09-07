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