    public static ModelNode createWriteAttributeOperation(PathAddress address, Attribute attribute, ModelNode value) {
        ModelNode operation = createAttributeOperation(ModelDescriptionConstants.WRITE_ATTRIBUTE_OPERATION, address, attribute);
        operation.get(ModelDescriptionConstants.VALUE).set(value);
        return operation;
    }