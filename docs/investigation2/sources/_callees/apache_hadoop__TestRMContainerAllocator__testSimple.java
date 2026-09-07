  public static JobId newJobId(ApplicationId appId, int id) {
    JobId jobId = Records.newRecord(JobId.class);
    jobId.setAppId(appId);
    jobId.setId(id);
    return jobId;
  }
  public static JobReport newJobReport(JobId jobId, String jobName,
      String userName, JobState state, long submitTime, long startTime,
      long finishTime, float setupProgress, float mapProgress,
      float reduceProgress, float cleanupProgress, String jobFile,
      List<AMInfo> amInfos, boolean isUber, String diagnostics) {
    return newJobReport(jobId, jobName, userName, state, submitTime, startTime,
        finishTime, setupProgress, mapProgress, reduceProgress,
        cleanupProgress, jobFile, amInfos, isUber, diagnostics,
        Priority.newInstance(0));
  }
  public static Resource newInstance(int memory, int vCores) {
    return new LightWeightResource(memory, vCores);
  }