  void close() {
    clear();
    if (daemon != null) {
      daemon.interrupt();
      try {
        daemon.join();
      } catch (InterruptedException e) {
        throw new RuntimeException("");
      }
    }
    daemon = null;
  }
  public Peer get(DatanodeID dnId, boolean isDomain) {

    if (capacity <= 0) { 
      return null;
    }
    return getInternal(dnId, isDomain);
  }
  public void put(DatanodeID dnId, Peer peer) {
    Preconditions.checkNotNull(dnId);
    Preconditions.checkNotNull(peer);
    if (peer.isClosed()) return;
    if (capacity <= 0) {
      
      IOUtilsClient.cleanupWithLogger(LOG, peer);
      return;
    }
    putInternal(dnId, peer);
  }
  public synchronized int size() {
    return multimap.size();
  }