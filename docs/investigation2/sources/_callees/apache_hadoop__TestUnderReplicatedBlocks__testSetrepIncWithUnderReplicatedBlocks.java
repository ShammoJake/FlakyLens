  void addToInvalidates(final Block block, final DatanodeInfo datanode) {
    if (!isPopulatingReplQueues()) {
      return;
    }
    invalidateBlocks.add(block, datanode, true);
  }
  public static Block getLocalBlock(final ExtendedBlock b) {
    return b == null ? null : b.getLocalBlock();
  }
  public int run(String argv[]) throws Exception {
    
    init();
    Tracer tracer = new Tracer.Builder("").
        conf(TraceUtils.wrapHadoopConf(SHELL_HTRACE_PREFIX, getConf())).
        build();
    int exitCode = -1;
    if (argv.length < 1) {
      printUsage(System.err);
    } else {
      String cmd = argv[0];
      Command instance = null;
      try {
        instance = commandFactory.getInstance(cmd);
        if (instance == null) {
          throw new UnknownCommandException();
        }
        TraceScope scope = tracer.newScope(instance.getCommandName());
        if (scope.getSpan() != null) {
          String args = StringUtils.join("", argv);
          if (args.length() > 2048) {
            args = args.substring(0, 2048);
          }
          scope.getSpan().addKVAnnotation("", args);
        }
        try {
          exitCode = instance.run(Arrays.copyOfRange(argv, 1, argv.length));
        } finally {
          scope.close();
        }
      } catch (IllegalArgumentException e) {
        displayError(cmd, e.getLocalizedMessage());
        printUsage(System.err);
        if (instance != null) {
          printInstanceUsage(System.err, instance);
        }
      } catch (Exception e) {
        
        LOG.debug("", e);
        displayError(cmd, "");
        e.printStackTrace(System.err);
      }
    }
    tracer.close();
    return exitCode;
  }