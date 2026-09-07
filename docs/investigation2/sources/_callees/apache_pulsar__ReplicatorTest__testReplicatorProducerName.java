    public static TopicName get(String domain, NamespaceName namespaceName, String topic) {
        String name = domain + "" + namespaceName.toString() + '' + topic;
        return TopicName.get(name);
    }