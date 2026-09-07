    static Builder builder() {
        return ReflectionUtils.newBuilder("");
    }
    public Optional<String> selectBrokerForAssignment(final ServiceUnitId serviceUnit) {
        
        long startTime = System.nanoTime();

        try {
            synchronized (brokerCandidateCache) {
                final String bundle = serviceUnit.toString();
                if (preallocatedBundleToBroker.containsKey(bundle)) {
                    
                    return Optional.of(preallocatedBundleToBroker.get(bundle));
                }
                final BundleData data = loadData.getBundleData().computeIfAbsent(bundle,
                        key -> getBundleDataOrDefault(bundle));
                brokerCandidateCache.clear();
                LoadManagerShared.applyNamespacePolicies(serviceUnit, policies, brokerCandidateCache,
                        getAvailableBrokers(),
                        brokerTopicLoadingPredicate);

                
                LoadManagerShared.filterBrokersWithLargeTopicCount(brokerCandidateCache, loadData,
                        conf.getLoadBalancerBrokerMaxTopics());

                
                LoadManagerShared.filterAntiAffinityGroupOwnedBrokers(pulsar, serviceUnit.toString(),
                        brokerCandidateCache,
                        brokerToNamespaceToBundleRange, brokerToFailureDomainMap);
                

                LoadManagerShared.removeMostServicingBrokersForNamespace(serviceUnit.toString(), brokerCandidateCache,
                        brokerToNamespaceToBundleRange);
                log.info("", brokerCandidateCache.size(), bundle);

                
                try {
                    for (BrokerFilter filter : filterPipeline) {
                        filter.filter(brokerCandidateCache, data, loadData, conf);
                    }
                } catch (BrokerFilterException x) {
                    
                    LoadManagerShared.applyNamespacePolicies(serviceUnit, policies, brokerCandidateCache,
                            getAvailableBrokers(),
                            brokerTopicLoadingPredicate);
                }

                if (brokerCandidateCache.isEmpty()) {
                    
                    LoadManagerShared.applyNamespacePolicies(serviceUnit, policies, brokerCandidateCache,
                            getAvailableBrokers(),
                            brokerTopicLoadingPredicate);
                }

                
                Optional<String> broker = placementStrategy.selectBroker(brokerCandidateCache, data, loadData, conf);
                if (log.isDebugEnabled()) {
                    log.debug("", broker, brokerCandidateCache);
                }

                if (!broker.isPresent()) {
                    
                    return broker;
                }

                final double overloadThreshold = conf.getLoadBalancerBrokerOverloadedThresholdPercentage() / 100.0;
                final double maxUsage = loadData.getBrokerData().get(broker.get()).getLocalData().getMaxResourceUsage();
                if (maxUsage > overloadThreshold) {
                    
                    LoadManagerShared.applyNamespacePolicies(serviceUnit, policies, brokerCandidateCache,
                            getAvailableBrokers(),
                            brokerTopicLoadingPredicate);
                    broker = placementStrategy.selectBroker(brokerCandidateCache, data, loadData, conf);
                }

                
                loadData.getBrokerData().get(broker.get()).getPreallocatedBundleData().put(bundle, data);
                preallocatedBundleToBroker.put(bundle, broker.get());

                final String namespaceName = LoadManagerShared.getNamespaceNameFromBundleName(bundle);
                final String bundleRange = LoadManagerShared.getBundleRangeFromBundleName(bundle);
                final ConcurrentOpenHashMap<String, ConcurrentOpenHashSet<String>> namespaceToBundleRange =
                        brokerToNamespaceToBundleRange
                                .computeIfAbsent(broker.get(), k -> new ConcurrentOpenHashMap<>());
                synchronized (namespaceToBundleRange) {
                    namespaceToBundleRange.computeIfAbsent(namespaceName, k -> new ConcurrentOpenHashSet<>())
                            .add(bundleRange);
                }
                return broker;
            }
        } finally {
            selectBrokerForAssignment.observe(System.nanoTime() - startTime, TimeUnit.NANOSECONDS);
        }
    }
    public NamespaceBundle getBundle(NamespaceName nsname, Range<Long> hashRange) {
        return new NamespaceBundle(nsname, hashRange, this);
    }
    public static NamespaceName get(String tenant, String namespace) {
        validateNamespaceName(tenant, namespace);
        return get(tenant + '' + namespace);
    }
    public ServiceConfiguration getConfiguration() {
        return this.config;
    }