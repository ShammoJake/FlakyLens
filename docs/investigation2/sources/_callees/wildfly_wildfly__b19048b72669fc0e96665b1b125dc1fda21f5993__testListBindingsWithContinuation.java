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