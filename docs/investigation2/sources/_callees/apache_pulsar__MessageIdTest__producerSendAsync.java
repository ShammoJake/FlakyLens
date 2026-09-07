    public int compareTo(MessageId o) {
        if (o == null) {
            throw new UnsupportedOperationException("");
        }
        if (o instanceof MessageIdImpl) {
            MessageIdImpl other = (MessageIdImpl) o;
            int batchIndex = (o instanceof BatchMessageIdImpl) ? ((BatchMessageIdImpl) o).getBatchIndex() : NO_BATCH;
            return messageIdCompare(
                this.ledgerId, this.entryId, this.partitionIndex, NO_BATCH,
                other.ledgerId, other.entryId, other.partitionIndex, batchIndex
            );
        } else if (o instanceof TopicMessageIdImpl) {
            return compareTo(((TopicMessageIdImpl) o).getInnerMessageId());
        } else {
            throw new UnsupportedOperationException("" + o.getClass().getName());
        }
    }