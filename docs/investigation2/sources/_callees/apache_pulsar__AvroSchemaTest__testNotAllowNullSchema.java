    public static <T> AvroSchema<T> of(SchemaDefinition<T> schemaDefinition) {
        if (schemaDefinition.getSchemaReaderOpt().isPresent() && schemaDefinition.getSchemaWriterOpt().isPresent()) {
            return new AvroSchema<>(schemaDefinition.getSchemaReaderOpt().get(),
                    schemaDefinition.getSchemaWriterOpt().get(), parseSchemaInfo(schemaDefinition, SchemaType.AVRO));
        }
        ClassLoader pojoClassLoader = null;
        if (schemaDefinition.getPojo() != null) {
            pojoClassLoader = schemaDefinition.getPojo().getClassLoader();
        }
        return new AvroSchema<>(parseSchemaInfo(schemaDefinition, SchemaType.AVRO), pojoClassLoader);
    }