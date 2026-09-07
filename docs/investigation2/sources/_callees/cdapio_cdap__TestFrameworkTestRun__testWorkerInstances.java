  public static byte[] stopKeyForPrefix(byte[] prefix) {
    for (int i = prefix.length - 1; i >= 0; i--) {
      int unsigned = prefix[i] & 0xff;
      if (unsigned < 0xff) {
        byte[] stopKey = Arrays.copyOf(prefix, i + 1);
        stopKey[stopKey.length - 1]++;
        return stopKey;
      }
    }

    
    return null;
  }
  public static byte[] toBytes(ByteBuffer bb) {
    int length = bb.remaining();
    byte [] result = new byte[length];
    int pos = bb.position();
    bb.get(result);
    bb.position(pos);
    return result;
  }
  public static int toInt(byte[] bytes) {
    return toInt(bytes, 0, SIZEOF_INT);
  }
  public byte[] read(String key) {
    return read(Bytes.toBytes(key));
  }
  public CloseableIterator<KeyValue<byte[], byte[]>> scan(byte[] startRow, byte[] stopRow) {
    final Scanner scanner = table.scan(startRow, stopRow);

    return new AbstractCloseableIterator<KeyValue<byte[], byte[]>>() {
      private boolean closed = false;
      @Override
      protected KeyValue<byte[], byte[]> computeNext() {
        if (closed) {
          return endOfData();
        }
        Row next = scanner.next();
        if (next != null) {
          return new KeyValue<>(next.getRow(), next.get(KEY_COLUMN));
        }
        close();
        return null;
      }

      @Override
      public void close() {
        scanner.close();
        endOfData();
        closed = true;
      }
    };
  }
  public DatasetId dataset(String dataset) {
    return new DatasetId(namespace, dataset);
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