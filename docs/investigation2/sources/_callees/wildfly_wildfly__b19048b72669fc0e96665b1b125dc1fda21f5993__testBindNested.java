    public void bind(final Name name, final Object object, final Class<?> bindType) throws NamingException {
        bind(name, object);
    }
    public static void popOwner() {
        WRITE_OWNER.pop();
    }
    public static void pushOwner(final ServiceName deploymentUnitServiceName) {
        WRITE_OWNER.push(deploymentUnitServiceName);
    }