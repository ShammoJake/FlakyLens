    public static ByteBuf newSubscribe(String topic, String subscription, long consumerId, long requestId,
            SubType subType, int priorityLevel, String consumerName, long resetStartMessageBackInSeconds) {
        return newSubscribe(topic, subscription, consumerId, requestId, subType, priorityLevel, consumerName,
                true , null , Collections.emptyMap(), false,
                false , InitialPosition.Earliest, resetStartMessageBackInSeconds, null,
                true );
    }
    protected void close() {
        ctx.close();
    }