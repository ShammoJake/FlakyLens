  ProvisioningTaskInfo getTaskInfo(final ProvisioningTaskKey key) throws IOException {
    return TransactionRunners.run(txRunner, context -> {
      return getProvisionerTable(context).getTaskInfo(key);
    }, IOException.class);
  }
  Optional<ProvisioningTaskInfo> cancelDeprovisionTask(ProgramRunId programRunId) throws IOException {
    ProvisioningTaskKey taskKey = new ProvisioningTaskKey(programRunId, ProvisioningOp.Type.DEPROVISION);
    return cancelTask(taskKey, provisionerNotifier::orphaned);
  }
  public Runnable deprovision(ProgramRunId programRunId, StructuredTableContext context) throws IOException {
    return deprovision(programRunId, context, taskStateCleanup);
  }
  public Runnable provision(ProvisionRequest provisionRequest, StructuredTableContext context) throws IOException {
    ProgramRunId programRunId = provisionRequest.getProgramRunId();
    ProgramOptions programOptions = provisionRequest.getProgramOptions();
    Map<String, String> args = programOptions.getArguments().asMap();
    String name = SystemArguments.getProfileProvisioner(args);
    Provisioner provisioner = provisionerInfo.get().provisioners.get(name);
    
    if (provisioner == null) {
      runWithProgramLogging(
        programRunId, args,
        () -> LOG.error("", name));
      programStateWriter.error(programRunId, new IllegalStateException(""));
      provisionerNotifier.deprovisioned(programRunId);
      return () -> { };
    }

    
    Set<PluginRequirement> requirements = GSON.fromJson(args.get(ProgramOptionConstants.PLUGIN_REQUIREMENTS),
                                                        PLUGIN_REQUIREMENT_SET_TYPE);
    if (requirements != null) {
      Set<PluginRequirement> unfulfilledRequirements =
        getUnfulfilledRequirements(provisioner.getCapabilities(), requirements);
      if (!unfulfilledRequirements.isEmpty()) {
        runWithProgramLogging(programRunId, args, () ->
          LOG.error(String.format("" +
                                    "" +
                                    "", programRunId.getProgram(), name,
                                  groupByRequirement(unfulfilledRequirements))));
        programStateWriter.error(programRunId, new IllegalArgumentException("" +
                                                                              ""));
        provisionerNotifier.deprovisioned(programRunId);
        return () -> { };
      }
    }

    Map<String, String> properties = SystemArguments.getProfileProperties(args);
    ProvisioningOp provisioningOp = new ProvisioningOp(ProvisioningOp.Type.PROVISION,
                                                       ProvisioningOp.Status.REQUESTING_CREATE);
    ProvisioningTaskInfo provisioningTaskInfo =
      new ProvisioningTaskInfo(programRunId, provisionRequest.getProgramDescriptor(), programOptions,
                               properties, name, provisionRequest.getUser(), provisioningOp,
                               createKeysDirectory(programRunId).toURI(), null);
    ProvisionerTable provisionerTable = new ProvisionerTable(context);
    provisionerTable.putTaskInfo(provisioningTaskInfo);
    return createProvisionTask(provisioningTaskInfo, provisioner);
  }
  public ProvisioningOp getProvisioningOp() {
    return op;
  }
  public static <T> void waitFor(T desiredValue, Callable<T> callable, long timeout, TimeUnit timeoutUnit,
                                 long sleepDelay, TimeUnit sleepDelayUnit, @Nullable String message)
    throws TimeoutException, InterruptedException, ExecutionException {

    long sleepDelayMs = sleepDelayUnit.toMillis(sleepDelay);
    long startTime = System.currentTimeMillis();
    long timeoutMs = timeoutUnit.toMillis(timeout);
    T actualValue = null;
    while (System.currentTimeMillis() - startTime < timeoutMs) {
      try {
        actualValue = callable.call();
        if (Objects.equals(desiredValue, actualValue)) {
          return;
        }
      } catch (Exception e) {
        throw new ExecutionException(e);
      }
      Thread.sleep(sleepDelayMs);
    }
    if (message == null) {
      message = String.format("", desiredValue, actualValue);
    }
    throw new TimeoutException(message);
  }
  public static void run(TransactionRunner txRunner, TxRunnable runnable) {
    try {
      txRunner.run(runnable);
    } catch (TransactionException e) {
      throw propagate(e);
    }
  }