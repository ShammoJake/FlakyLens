    public static ModelNode createAddOperation(PathAddress address, Map<Attribute, ModelNode> parameters) {
        ModelNode operation = Util.createAddOperation(address);
        for (Map.Entry<Attribute, ModelNode> entry : parameters.entrySet()) {
            operation.get(entry.getKey().getName()).set(entry.getValue());
        }
        return operation;
    }
    public static ModelNode createWriteAttributeOperation(PathAddress address, Attribute attribute, ModelNode value) {
        ModelNode operation = createAttributeOperation(ModelDescriptionConstants.WRITE_ATTRIBUTE_OPERATION, address, attribute);
        operation.get(ModelDescriptionConstants.VALUE).set(value);
        return operation;
    }