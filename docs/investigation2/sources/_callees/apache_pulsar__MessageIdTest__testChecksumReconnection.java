    public int brokerChecksumSupportedVersion() {
        return ProtocolVersion.v6.getNumber();
    }
    ClientCnx cnx() {
        return this.connectionHandler.cnx();
    }
    ClientCnx getClientCnx() {
        return this.connectionHandler.getClientCnx();
    }
    void grabCnx() {
        this.connectionHandler.grabCnx();
    }
    public void sendAsync(Message<T> message, SendCallback callback) {
        checkArgument(message instanceof MessageImpl);

        if (!isValidProducerState(callback)) {
            return;
        }

        if (!canEnqueueRequest(callback)) {
            return;
        }

        MessageImpl<T> msg = (MessageImpl<T>) message;
        MessageMetadata.Builder msgMetadataBuilder = msg.getMessageBuilder();
        ByteBuf payload = msg.getDataBuffer();

        
        int uncompressedSize = payload.readableBytes();
        ByteBuf compressedPayload = payload;
        
        
        if (!isBatchMessagingEnabled() || msgMetadataBuilder.hasDeliverAtTime()) {
            compressedPayload = compressor.encode(payload);
            payload.release();

            
            int compressedSize = compressedPayload.readableBytes();
            if (compressedSize > ClientCnx.getMaxMessageSize()) {
                compressedPayload.release();
                String compressedStr = (!isBatchMessagingEnabled() && conf.getCompressionType() != CompressionType.NONE)
                                           ? ""
                                           : "";
                PulsarClientException.InvalidMessageException invalidMessageException = new PulsarClientException.InvalidMessageException(
                    format("", compressedStr, compressedSize,
                           ClientCnx.getMaxMessageSize()));
                callback.sendComplete(invalidMessageException);
                return;
            }
        }

        if (!msg.isReplicated() && msgMetadataBuilder.hasProducerName()) {
            PulsarClientException.InvalidMessageException invalidMessageException =
                    new PulsarClientException.InvalidMessageException("");
            callback.sendComplete(invalidMessageException);
            compressedPayload.release();
            return;
        }

        if (schemaVersion.isPresent()) {
            msgMetadataBuilder.setSchemaVersion(ByteString.copyFrom(schemaVersion.get()));
        }

        try {
            synchronized (this) {
                long sequenceId;
                if (!msgMetadataBuilder.hasSequenceId()) {
                    sequenceId = msgIdGeneratorUpdater.getAndIncrement(this);
                    msgMetadataBuilder.setSequenceId(sequenceId);
                } else {
                    sequenceId = msgMetadataBuilder.getSequenceId();
                }
                if (!msgMetadataBuilder.hasPublishTime()) {
                    msgMetadataBuilder.setPublishTime(client.getClientClock().millis());

                    checkArgument(!msgMetadataBuilder.hasProducerName());

                    msgMetadataBuilder.setProducerName(producerName);

                    if (conf.getCompressionType() != CompressionType.NONE) {
                        msgMetadataBuilder.setCompression(
                                CompressionCodecProvider.convertToWireProtocol(conf.getCompressionType()));
                    }
                    msgMetadataBuilder.setUncompressedSize(uncompressedSize);
                }

                if (isBatchMessagingEnabled() && !msgMetadataBuilder.hasDeliverAtTime()) {
                    
                    
                    if (batchMessageContainer.haveEnoughSpace(msg)) {
                        batchMessageContainer.add(msg, callback);
                        lastSendFuture = callback.getFuture();
                        payload.release();
                        if (batchMessageContainer.getNumMessagesInBatch() == maxNumMessagesInBatch
                                || batchMessageContainer.getCurrentBatchSize() >= BatchMessageContainerImpl.MAX_MESSAGE_BATCH_SIZE_BYTES) {
                            batchMessageAndSend();
                        }
                    } else {
                        doBatchSendAndAdd(msg, callback, payload);
                    }
                } else {
                    ByteBuf encryptedPayload = encryptMessage(msgMetadataBuilder, compressedPayload);

                    MessageMetadata msgMetadata = msgMetadataBuilder.build();

                    
                    
                    int numMessages = msg.getMessageBuilder().hasNumMessagesInBatch()
                            ? msg.getMessageBuilder().getNumMessagesInBatch()
                            : 1;
                    ByteBufPair cmd = sendMessage(producerId, sequenceId, numMessages, msgMetadata, encryptedPayload);
                    msgMetadataBuilder.recycle();
                    msgMetadata.recycle();

                    final OpSendMsg op = OpSendMsg.create(msg, cmd, sequenceId, callback);
                    op.setNumMessagesInBatch(numMessages);
                    op.setBatchSizeByte(encryptedPayload.readableBytes());
                    pendingMessages.put(op);
                    lastSendFuture = callback.getFuture();

                    
                    
                    ClientCnx cnx = cnx();
                    if (isConnected()) {
                        
                        
                        
                        cmd.retain();
                        cnx.ctx().channel().eventLoop().execute(WriteInEventLoopCallback.create(this, cnx, op));
                        stats.updateNumMsgsSent(op.numMessagesInBatch, op.batchSizeByte);
                    } else {
                        if (log.isDebugEnabled()) {
                            log.debug("", topic, producerName,
                                    sequenceId);
                        }
                    }
                }
            }
        } catch (InterruptedException ie) {
            Thread.currentThread().interrupt();
            semaphore.release();
            callback.sendComplete(new PulsarClientException(ie));
        } catch (PulsarClientException e) {
            semaphore.release();
            callback.sendComplete(e);
        } catch (Throwable t) {
            semaphore.release();
            callback.sendComplete(new PulsarClientException(t));
        }
    }
    void setClientCnx(ClientCnx clientCnx) {
        this.connectionHandler.setClientCnx(clientCnx);
    }