    public Timer timer()
    {
        return timer;
    }
    public void updateTimer( RaftMessages.Type type, Duration duration )
    {
        long nanos = duration.toNanos();
        timer.update( nanos, TimeUnit.NANOSECONDS );
        typeTimers.get( type ).update( nanos, TimeUnit.NANOSECONDS );
    }