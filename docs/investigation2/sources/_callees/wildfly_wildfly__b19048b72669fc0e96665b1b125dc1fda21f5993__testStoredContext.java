    public String toString() {
        try {
            return toString(fullName);
        } catch (InvalidName in) {
            return "";
        }
    }
    public NamingEnumeration<Binding> listBindings(final Name name) throws NamingException {
        check(name, JndiPermission.ACTION_LIST_BINDINGS);

        try {
            return namingEnumeration(namingStore.listBindings(getAbsoluteName(name)));
        } catch(CannotProceedException cpe) {
            final Context continuationContext = NamingManager.getContinuationContext(cpe);
            return continuationContext.listBindings(cpe.getRemainingName());
        } catch (RequireResolveException r) {
            final Object o = lookup(r.getResolve());
            if (o instanceof Context) {
                return ((Context)o).listBindings(name.getSuffix(r.getResolve().size()));
            }

            throw notAContextException(r.getResolve());
        }
    }
    public Object lookup(final Name name) throws NamingException {
        return lookup(name, true);
    }
    public void add(final ServiceName serviceName) {
        final ConcurrentSkipListSet<ServiceName> boundServices = this.boundServices;
        if (boundServices.contains(serviceName)) {
            throw NamingLogger.ROOT_LOGGER.serviceAlreadyBound(serviceName);
        }
        boundServices.add(serviceName);
    }