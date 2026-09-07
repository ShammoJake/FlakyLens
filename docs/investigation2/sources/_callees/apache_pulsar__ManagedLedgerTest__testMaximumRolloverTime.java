    public ManagedLedgerConfig setMaxEntriesPerLedger(int maxEntriesPerLedger) {
        this.maxEntriesPerLedger = maxEntriesPerLedger;
        return this;
    }
    public void setMaximumRolloverTime(int maximumRolloverTime, TimeUnit unit) {
        this.maximumRolloverTimeMs = unit.toMillis(maximumRolloverTime);
        checkArgument(maximumRolloverTimeMs >= minimumRolloverTimeMs,
                "");
    }
    public void setMinimumRolloverTime(int minimumRolloverTime, TimeUnit unit) {
        this.minimumRolloverTimeMs = (int) unit.toMillis(minimumRolloverTime);
        checkArgument(maximumRolloverTimeMs >= minimumRolloverTimeMs,
                "");
    }
    public Position addEntry(byte[] data) throws InterruptedException, ManagedLedgerException {
        return addEntry(data, 0, data.length);
    }
    public List<LedgerInfo> getLedgersInfoAsList() {
        return Lists.newArrayList(ledgers.values());
    }
    public ManagedCursor openCursor(String cursorName) throws InterruptedException, ManagedLedgerException {
        return openCursor(cursorName, InitialPosition.Latest);
    }