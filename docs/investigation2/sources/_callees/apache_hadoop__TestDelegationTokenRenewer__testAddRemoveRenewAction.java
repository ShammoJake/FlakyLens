  public <T extends FileSystem & Renewable> RenewAction<T> addRenewAction(final T fs) {
    synchronized (this) {
      if (!isAlive()) {
        start();
      }
    }
    RenewAction<T> action = new RenewAction<T>(fs);
    if (action.token != null) {
      queue.add(action);
    } else {
      fs.LOG.error("");
    }
    return action;
  }
  protected int getRenewQueueLength() {
    return queue.size();
  }
  public <T extends FileSystem & Renewable> void removeRenewAction(
      final T fs) throws IOException {
    RenewAction<T> action = new RenewAction<T>(fs);
    if (queue.remove(action)) {
      try {
        action.cancel();
      } catch (InterruptedException ie) {
        LOG.error("" + fs.getUri()
            + "");
        LOG.debug("", ie);
      }
    }
  }
  public static long now() {
    return System.currentTimeMillis();
  }