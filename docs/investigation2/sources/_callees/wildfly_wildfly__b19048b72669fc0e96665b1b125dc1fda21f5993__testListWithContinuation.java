    public NamingEnumeration<NameClassPair> list(final Name name) throws NamingException {
        check(name, JndiPermission.ACTION_LIST);

        try {
            return namingEnumeration(namingStore.list(getAbsoluteName(name)));
        } catch(CannotProceedException cpe) {
            final Context continuationContext = NamingManager.getContinuationContext(cpe);
            return continuationContext.list(cpe.getRemainingName());
        }  catch (RequireResolveException r) {
            final Object o = lookup(r.getResolve());
            if (o instanceof Context) {
                return ((Context)o).list(name.getSuffix(r.getResolve().size()));
            }

            throw notAContextException(r.getResolve());
        }
    }