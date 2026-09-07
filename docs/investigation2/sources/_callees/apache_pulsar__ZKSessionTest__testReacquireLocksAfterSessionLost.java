    static MetadataStoreExtended create(String metadataURL, MetadataStoreConfig metadataStoreConfig)
            throws MetadataStoreException {
        return MetadataStoreFactoryImpl.createExtended(metadataURL, metadataStoreConfig);
    }