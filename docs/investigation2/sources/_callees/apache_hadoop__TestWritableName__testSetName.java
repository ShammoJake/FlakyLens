  public static synchronized Class<?> getClass(String name, Configuration conf
                                            ) throws IOException {
    Class<?> writableClass = NAME_TO_CLASS.get(name);
    if (writableClass != null)
      return writableClass.asSubclass(Writable.class);
    try {
      return conf.getClassByName(name);
    } catch (ClassNotFoundException e) {
      IOException newE = new IOException("" + name);
      newE.initCause(e);
      throw newE;
    }
  }
  public static synchronized void setName(Class<?> writableClass, String name) {
    CLASS_TO_NAME.put(writableClass, name);
    NAME_TO_CLASS.put(name, writableClass);
  }