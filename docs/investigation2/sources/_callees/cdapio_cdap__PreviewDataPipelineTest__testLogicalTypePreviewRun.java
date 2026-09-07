  public String getEntityName() {
    return getApplication();
  }
  public static DatasetProperties of(Map<String, String> props) {
    return builder().addAll(props).build();
  }
  public static ETLPlugin getPlugin() {
    Map<String, String> properties = new HashMap<>();
    return new ETLPlugin("", Transform.PLUGIN_TYPE, properties, null);
  }
  public static ETLPlugin getPlugin(String tableName) {
    Map<String, String> properties = new HashMap<>();
    properties.put("", tableName);
    return new ETLPlugin("", BatchSink.PLUGIN_TYPE, properties, null);
  }
  public static ETLPlugin getPlugin(String tableName) {
    Map<String, String> properties = new HashMap<>();
    properties.put("", tableName);
    return new ETLPlugin("", BatchSource.PLUGIN_TYPE, properties, null);
  }
  public static void writeInput(DataSetManager<Table> tableManager,
                                Iterable<StructuredRecord> records) throws Exception {
    writeInput(tableManager, null, records);
  }
  public Status getStatus() {
    return status;
  }
    public static Field of(String name, Schema schema) {
      return new Field(name, schema);
    }
  public static Schema recordOf(String name) {
    if (name == null) {
      throw new IllegalArgumentException("");
    }
    return new Schema(Type.RECORD, null, null, null, null, null, name, null, null, 0, 0);
  }
    public String toString() {
      return String.format("", name, schema);
    }
  public static Builder builder(Schema schema) throws UnexpectedFormatException {
    if (schema == null || schema.getType() != Schema.Type.RECORD || schema.getFields().size() < 1) {
      throw new UnexpectedFormatException("");
    }
    return new Builder(schema);
  }
  public <T> T get(String fieldName) {
    return (T) fields.get(fieldName);
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