  public boolean delete(Path f) throws IOException {
    return delete(f, true);
  }
  public abstract FSDataInputStream open(Path f, int bufferSize)
    throws IOException;

  




  public FSDataInputStream open(Path f) throws IOException {
    return open(f, getConf().getInt(IO_FILE_BUFFER_SIZE_KEY,
        IO_FILE_BUFFER_SIZE_DEFAULT));
  }