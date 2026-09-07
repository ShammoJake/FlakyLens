    synchronized void addListener(final String target, final int scope, final NamingListener namingListener) {
        final TargetScope targetScope = new TargetScope(target, scope);
        
        ListenerHolder holder = holdersByListener.get(namingListener);
        if (holder == null) {
            holder = new ListenerHolder(namingListener, targetScope);
            final Map<NamingListener, ListenerHolder> byListenerCopy = new FastCopyHashMap<NamingListener, ListenerHolder>(holdersByListener);
            byListenerCopy.put(namingListener, holder);
            holdersByListener = byListenerCopy;
        } else {
            holder.addTarget(targetScope);
        }

        List<ListenerHolder> holdersForTarget = holdersByTarget.get(targetScope);
        if (holdersForTarget == null) {
            holdersForTarget = new CopyOnWriteArrayList<ListenerHolder>();
            final Map<TargetScope, List<ListenerHolder>> byTargetCopy = new FastCopyHashMap<TargetScope, List<ListenerHolder>>(holdersByTarget);
            byTargetCopy.put(targetScope, holdersForTarget);
            holdersByTarget = byTargetCopy;
        }
        holdersForTarget.add(holder);
    }
    void fireEvent(final EventContext context, final Name name, final Binding existingBinding, final Binding newBinding, int type, final String changeInfo, final Integer... scopes) {
        final String target = name.toString();
        final Set<Integer> scopeSet = new HashSet<Integer>(Arrays.asList(scopes));
        final NamingEvent event = new NamingEvent(context, type, newBinding, existingBinding, changeInfo);

        final Set<ListenerHolder> holdersToFire = new HashSet<ListenerHolder>();

        
        if (scopeSet.contains(EventContext.OBJECT_SCOPE)) {
            final TargetScope targetScope = new TargetScope(target, EventContext.OBJECT_SCOPE);
            final List<ListenerHolder> holders = holdersByTarget.get(targetScope);
            if (holders != null) {
                for (ListenerHolder holder : holders) {
                    holdersToFire.add(holder);
                }
            }
        }

        
        if (scopeSet.contains(EventContext.ONELEVEL_SCOPE) && !name.isEmpty()) {
            final TargetScope targetScope = new TargetScope(name.getPrefix(name.size() - 1).toString(), EventContext.ONELEVEL_SCOPE);
            final List<ListenerHolder> holders = holdersByTarget.get(targetScope);
            if (holders != null) {
                for (ListenerHolder holder : holders) {
                    holdersToFire.add(holder);
                }
            }
        }

        
        if (scopeSet.contains(EventContext.SUBTREE_SCOPE) && !name.isEmpty()) {
            for (int i = 1; i < name.size(); i++) {
                final Name parentName = name.getPrefix(i);
                final TargetScope targetScope = new TargetScope(parentName.toString(), EventContext.SUBTREE_SCOPE);
                final List<ListenerHolder> holders = holdersByTarget.get(targetScope);
                if (holders != null) {
                    for (ListenerHolder holder : holders) {
                        holdersToFire.add(holder);
                    }
                }
            }
        }

        executor.execute(new FireEventTask(holdersToFire, event));
    }