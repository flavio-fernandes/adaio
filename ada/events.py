#!/usr/bin/env python


class Base(object):
    def __init__(self, group, description, params=None):
        self.name = self.__class__.__name__
        self.group = group
        self.description = description
        self.params = params or []


class MqttMsgEvent(Base):
    def __init__(self, client_id, topic, payload):
        params = [client_id, topic, payload]
        Base.__init__(self, "mqtt", "mqtt msg", params)


class MqttConnectEvent(Base):
    def __init__(self, client_id, event, rc=None):
        params = [client_id, event, rc]
        Base.__init__(self, "mqtt", "mqtt conn", params)


class OpenWeatherEvent(Base):
    def __init__(self, payload):
        params = [payload]
        Base.__init__(self, "open_weather", "weather", params)
