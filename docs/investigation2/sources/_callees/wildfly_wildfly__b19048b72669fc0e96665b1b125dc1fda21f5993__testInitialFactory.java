        public Object lookup(final Name name, boolean dereference) throws NamingException {
            final ParsedName parsedName = parse(name);
            final Context namespaceContext = findContext(name, parsedName);
            if (namespaceContext == null)
                return super.lookup(parsedName.remaining(),dereference);
            else
                return namespaceContext.lookup(parsedName.remaining());
        }