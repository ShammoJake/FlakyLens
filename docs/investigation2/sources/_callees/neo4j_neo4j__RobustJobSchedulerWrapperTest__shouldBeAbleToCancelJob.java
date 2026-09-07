    public void cancelAndWaitTermination( JobScheduler.JobHandle job )
    {
        try
        {
            job.cancel( true );

            try
            {
                job.waitTermination();
            }
            catch ( CancellationException e )
            {
                
            }
        }
        catch ( Throwable e )
        {
            log.warn( "", e );
        }
    }
    public JobScheduler.JobHandle scheduleRecurring( String name, long periodMillis, ThrowingAction<Exception> action )
    {
        return delegate.scheduleRecurring( new JobScheduler.Group( name ),
                () -> withErrorHandling( action ), periodMillis, MILLISECONDS );
    }