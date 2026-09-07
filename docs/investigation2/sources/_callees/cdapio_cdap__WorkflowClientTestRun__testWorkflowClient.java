  public List<RunRecord> getProgramRuns(ProgramId program, String state,
                                        long startTime, long endTime, int limit)
    throws IOException, NotFoundException, UnauthenticatedException, UnauthorizedException {

    String queryParams = String.format("",
                                       Constants.AppFabric.QUERY_PARAM_STATUS, state,
                                       Constants.AppFabric.QUERY_PARAM_START_TIME, startTime,
                                       Constants.AppFabric.QUERY_PARAM_END_TIME, endTime,
                                       Constants.AppFabric.QUERY_PARAM_LIMIT, limit);

    String path = String.format("",
                                program.getApplication(), program.getVersion(),
                                program.getType().getCategoryName(),
                                program.getProgram(), queryParams);
    URL url = config.resolveNamespacedURLV3(program.getNamespaceId(), path);

    HttpResponse response = restClient.execute(HttpMethod.GET, url, config.getAccessToken(),
                                               HttpURLConnection.HTTP_NOT_FOUND);
    if (response.getResponseCode() == HttpURLConnection.HTTP_NOT_FOUND) {
      throw new NotFoundException(program);
    }

    return ObjectResponse.fromJsonBody(response, new TypeToken<List<RunRecord>>() { }).getResponseObject();
  }
  public void start(ProgramId program, boolean debug, @Nullable Map<String, String> runtimeArgs) throws IOException,
    ProgramNotFoundException, UnauthenticatedException, UnauthorizedException {
    String action = debug ? "" :  "";
    String path = String.format("", program.getApplication(), program.getVersion(),
                                program.getType().getCategoryName(), program.getProgram(), action);
    URL url = config.resolveNamespacedURLV3(program.getNamespaceId(), path);
    
    HttpRequest.Builder request = HttpRequest.post(url).withBody(GSON.toJson(runtimeArgs));;
    HttpResponse response = restClient.execute(request.build(), config.getAccessToken(),
                                               HttpURLConnection.HTTP_NOT_FOUND);
    if (response.getResponseCode() == HttpURLConnection.HTTP_NOT_FOUND) {
      throw new ProgramNotFoundException(program);
    }
  }
  public ProgramRunId run(String run) {
    return new ProgramRunId(new ApplicationId(getNamespace(), getApplication(), getVersion()), type, program, run);
  }
  public static RunId generate() {
    return new RunIdImpl(generateUUIDForTime(System.currentTimeMillis()));
  }
  public void deleteWorkflowLocalDatasets(ProgramRunId workflowRunId)
    throws IOException, UnauthenticatedException, NotFoundException, UnauthorizedException {
    HttpResponse response = restClient.execute(HttpMethod.DELETE, getWorkflowLocalDatasetURL(workflowRunId),
                                               config.getAccessToken(), HttpURLConnection.HTTP_NOT_FOUND);

    if (response.getResponseCode() == HttpURLConnection.HTTP_NOT_FOUND) {
      throw new NotFoundException(workflowRunId);
    }
  }
  public Map<String, DatasetSpecificationSummary> getWorkflowLocalDatasets(ProgramRunId workflowRunId)
    throws IOException, UnauthenticatedException, NotFoundException, UnauthorizedException {
    HttpResponse response = restClient.execute(HttpMethod.GET, getWorkflowLocalDatasetURL(workflowRunId),
                                               config.getAccessToken(), HttpURLConnection.HTTP_NOT_FOUND);

    if (response.getResponseCode() == HttpURLConnection.HTTP_NOT_FOUND) {
      throw new NotFoundException(workflowRunId);
    }

    return ObjectResponse.fromJsonBody(response, new TypeToken<Map<String, DatasetSpecificationSummary>>() { })
      .getResponseObject();
  }
  public Map<String, WorkflowNodeStateDetail> getWorkflowNodeStates(ProgramRunId workflowRunId)
    throws IOException, UnauthenticatedException, NotFoundException, UnauthorizedException {
    String path = String.format("", workflowRunId.getApplication(),
                                workflowRunId.getProgram(), workflowRunId.getRun());
    NamespaceId namespaceId = workflowRunId.getNamespaceId();
    URL urlPath = config.resolveNamespacedURLV3(namespaceId, path);
    HttpResponse response = restClient.execute(HttpMethod.GET, urlPath, config.getAccessToken(),
                                               HttpURLConnection.HTTP_NOT_FOUND);

    if (response.getResponseCode() == HttpURLConnection.HTTP_NOT_FOUND) {
      throw new NotFoundException(workflowRunId);
    }

    return ObjectResponse.fromJsonBody(response,
                                       new TypeToken<Map<String, WorkflowNodeStateDetail>>() { }).getResponseObject();
  }
  public WorkflowTokenDetail getWorkflowToken(ProgramRunId workflowRunId)
    throws UnauthenticatedException, IOException, NotFoundException, UnauthorizedException {
    return getWorkflowToken(workflowRunId, null, null);
  }
  public WorkflowTokenNodeDetail getWorkflowTokenAtNode(ProgramRunId workflowRunId, String nodeName)
    throws UnauthenticatedException, IOException, NotFoundException, UnauthorizedException {
    return getWorkflowTokenAtNode(workflowRunId, nodeName, null, null);
  }
  public String getNodeId() {
    return nodeId;
  }
  public NodeStatus getNodeStatus() {
    return nodeStatus;
  }
  public Map<String, List<NodeValueDetail>> getTokenData() {
    return tokenData;
  }
  public Map<String, String> getTokenDataAtNode() {
    return tokenDataAtNode;
  }