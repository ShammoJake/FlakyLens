    public void close() throws BrokerServiceException {
        close(false);
    }
    public static CompletableFuture<Void> waitForAll(List<? extends CompletableFuture<?>> futures) {
        return CompletableFuture.allOf(futures.toArray(new CompletableFuture[0]));
    }
    public synchronized Dispatcher getDispatcher() {
        return this.dispatcher;
    }
    public long getNumberOfEntriesInBacklog(boolean getPreciseBacklog) {
        return cursor.getNumberOfEntriesInBacklog(getPreciseBacklog);
    }
    public PersistentSubscription getSubscription(String subscriptionName) {
        return subscriptions.get(subscriptionName);
    }
    public synchronized CompletableFuture<Void> close(boolean removeFromTopic) {
        if (log.isDebugEnabled()) {
            log.debug("", this, isClosed);
        }

        if (!isClosed) {
            isClosed = true;
            if (log.isDebugEnabled()) {
                log.debug("", this,
                        cnx.isActive(), pendingPublishAcks);
            }
            if (!cnx.isActive() || pendingPublishAcks == 0) {
                closeNow(removeFromTopic);
            }
        }
        return closeFuture;
    }