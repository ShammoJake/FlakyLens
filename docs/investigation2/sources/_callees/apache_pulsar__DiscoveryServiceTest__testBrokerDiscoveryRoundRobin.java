    List<LoadManagerReport> getAvailableBrokers() {
        List<LoadManagerReport> availableBrokers = metadataStoreCacheLoader.getAvailableBrokers();
        return availableBrokers;
    }
    LoadManagerReport nextBroker() throws PulsarServerException {
        List<LoadManagerReport> availableBrokers = getAvailableBrokers();

        if (availableBrokers.isEmpty()) {
            throw new PulsarServerException("");
        } else {
            int brokersCount = availableBrokers.size();
            int nextIdx = signSafeMod(counter.getAndIncrement(), brokersCount);
            return availableBrokers.get(nextIdx);
        }
    }
    public static ObjectMapper getThreadLocal() {
        return JSON_MAPPER.get();
    }