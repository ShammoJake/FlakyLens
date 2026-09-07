    public void bind(final Name name, final Object object) throws NamingException {
        check(name, JndiPermission.ACTION_BIND);

        if(namingStore instanceof WritableNamingStore) {
            final Name absoluteName = getAbsoluteName(name);
            final Object value;
            if (object instanceof Referenceable) {
                value = ((Referenceable) object).getReference();
            } else {
                value = object;
            }
            if (System.getSecurityManager() == null) {
                getWritableNamingStore().bind(absoluteName, value);
            } else {
                
                final NamingException e = AccessController.doPrivileged(new PrivilegedAction<NamingException>() {
                    @Override
                    public NamingException run() {
                        try {
                            getWritableNamingStore().bind(absoluteName, value);
                        } catch (NamingException e) {
                            return e;
                        }
                        return null;
                    }
                });
                
                if (e != null) {
                    throw e;
                }
            }
        } else {
            throw NamingLogger.ROOT_LOGGER.readOnlyNamingContext();
        }

    }
    public Object lookup(final Name name) throws NamingException {
        return lookup(name, true);
    }
    public void rebind(final Name name, Object object) throws NamingException {
        check(name, JndiPermission.ACTION_REBIND);

        if(namingStore instanceof WritableNamingStore) {
            final Name absoluteName = getAbsoluteName(name);
            if (object instanceof Referenceable) {
                object = ((Referenceable) object).getReference();
            }
            getWritableNamingStore().rebind(absoluteName, object);
        } else {
            throw NamingLogger.ROOT_LOGGER.readOnlyNamingContext();
        }
    }