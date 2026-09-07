  public UserGroupInformation getUser() {
    UserGroupInformation ugi = ugiCache.get(this);
    if (ugi == null) {
      ugi = super.getUser();
      ugiCache.put(this, ugi);
    }
    return ugi;
  }
  public <T> T doAs(PrivilegedAction<T> action) {
    logPrivilegedAction(subject, action);
    return Subject.doAs(subject, action);
  }