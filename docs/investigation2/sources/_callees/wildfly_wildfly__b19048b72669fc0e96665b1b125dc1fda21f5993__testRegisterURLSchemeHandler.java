    public static synchronized void addUrlContextFactory(final String scheme, ObjectFactory factory) {
        Map<String, ObjectFactory> factories = new HashMap<String, ObjectFactory>(urlContextFactories);
        factories.put(scheme, factory);
        urlContextFactories = Collections.unmodifiableMap(factories);
    }
        public Object lookup(final Name name, boolean dereference) throws NamingException {
            final ParsedName parsedName = parse(name);
            final Context namespaceContext = findContext(name, parsedName);
            if (namespaceContext == null)
                return super.lookup(parsedName.remaining(),dereference);
            else
                return namespaceContext.lookup(parsedName.remaining());
        }
    public static synchronized void removeUrlContextFactory(final String scheme, ObjectFactory factory) {
        Map<String, ObjectFactory> factories = new HashMap<String, ObjectFactory>(urlContextFactories);

        ObjectFactory f = factories.get(scheme);
        if (f == factory) {
            factories.remove(scheme);
            urlContextFactories = Collections.unmodifiableMap(factories);
            return;
        } else {
            throw new IllegalArgumentException();
        }
    }