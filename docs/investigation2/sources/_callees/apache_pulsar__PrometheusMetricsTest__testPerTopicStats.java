    public void close() throws BrokerServiceException {
        close(false);
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
    public static void generate(PulsarService pulsar, boolean includeTopicMetrics, boolean includeConsumerMetrics,
        boolean includeProducerMetrics, OutputStream out) throws IOException {
        generate(pulsar, includeTopicMetrics, includeConsumerMetrics, includeProducerMetrics, false, out, null);
    }