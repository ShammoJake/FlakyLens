    public static BindingType forName(String localName) {
        if (localName == null) return null;
        final BindingType directoryGrouping = MAP.get(localName.toLowerCase());
        return directoryGrouping == null ? BindingType.valueOf(localName.toUpperCase()) : directoryGrouping;
    }