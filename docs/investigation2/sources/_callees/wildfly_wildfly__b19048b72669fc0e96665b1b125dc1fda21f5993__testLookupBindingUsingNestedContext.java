    public void add(final ServiceName serviceName) {
        final ConcurrentSkipListSet<ServiceName> boundServices = this.boundServices;
        if (boundServices.contains(serviceName)) {
            throw NamingLogger.ROOT_LOGGER.serviceAlreadyBound(serviceName);
        }
        boundServices.add(serviceName);
    }
    public Object lookup(Name name) throws NamingException {
        return lookup(name, true);
    }