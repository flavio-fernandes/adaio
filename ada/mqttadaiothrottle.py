#!/usr/bin/env python
import multiprocessing
import signal
import sys
import time

import dill
import paho.mqtt.client as mqtt
from six.moves import queue

from ada import const
from ada import events
from ada import log
from os import environ as env

ADAFRUIT_IO_KEY = env['IO_KEY']
ADAFRUIT_IO_USERNAME = env['IO_USERNAME']
ADAFRUIT_IO_HOST = 'io.adafruit.com'

CMDQ_SIZE = 100
CMDQ_GET_TIMEOUT = 366  # seconds
TOPIC_QOS = 1
_state = None


class State(object):
    def __init__(self, queueEventFun, topics):
        self.queueEventFun = queueEventFun  # queue for output events
        self.cmdq = multiprocessing.Queue(CMDQ_SIZE)  # queue for input commands
        self.topics = topics
        self.mqtt_client = None
        self.connected = False

    @property
    def mqtt_client_id(self):
        return const.MQTT_CLIENT_AIO_THROTTLE

# =============================================================================


# external to this module, once
def do_init(queueEventFun=None):
    global _state

    topics = ['{}/errors'.format(ADAFRUIT_IO_USERNAME),
              '{}/throttle'.format(ADAFRUIT_IO_USERNAME),
              ]

    _state = State(queueEventFun, topics)
    logger.debug("{} init called".format(_state.mqtt_client_id))
    return _state.cmdq


# =============================================================================

def _notifyMqttConnectEvent(event, rc):
    global _state
    logger.info("got mqtt connect event %s %s", event, rc)
    _state.connected = event == const.MQTT_CONNECTED
    _notifyEvent(events.MqttConnectEvent(_state.mqtt_client_id, event, rc))


def _notifyMqttMsgEvent(topic, payload):
    global _state

    # filter out topics that we do not care about
    if topic not in _state.topics:
        logger.warning("ignoring mqtt message %s %s", topic, payload)
        return
    logger.debug("got mqtt message %s %s", topic, payload)
    _notifyEvent(events.MqttMsgEvent(_state.mqtt_client_id, topic, payload))


def _notifyEvent(event):
    global _state
    if _state.queueEventFun:
        _state.queueEventFun(event)


# =============================================================================


def client_connect_callback(client, userdata, flags_dict, rc):
    global _state
    if rc != mqtt.MQTT_ERR_SUCCESS:
        logger.warning("client %s connect failed with flags %s rc %s %s",
                       _state.mqtt_client_id, flags_dict, rc, mqtt.error_string(rc))
        return
    logger.info("client %s connected with flags %s rc %s", _state.mqtt_client_id, flags_dict, rc)
    # userdata is list of topics we care about
    assert isinstance(userdata, list), "Unexpected userdata from callback: {}".format(userdata)
    assert userdata[0] == 'topics', "Unexpected userdata from callback: {}".format(userdata)
    mqtt2cmd_topics = [(t, TOPIC_QOS) for t in userdata[1:]]
    if mqtt2cmd_topics:
        client.subscribe(mqtt2cmd_topics)
    _enqueue_cmd((_notifyMqttConnectEvent, [const.MQTT_CONNECTED, rc]))


def client_disconnect_callback(_client, _userdata, rc):
    _enqueue_cmd((_notifyMqttConnectEvent, [const.MQTT_DISCONNECTED, rc]))


def client_message_callback(_client, _userdata, msg):
    # logger.debug("callback for mqtt message %s %s", msg.topic, msg.payload)
    topic = msg.topic.decode('utf-8') if isinstance(msg.topic, bytes) else msg.topic
    payload = msg.payload.decode('utf-8') if isinstance(msg.payload, bytes) else msg.payload
    params = [topic, payload]
    _enqueue_cmd((_notifyMqttMsgEvent, params))


def _setup_mqtt_client(topics):
    try:
        userdata = ['topics'] + topics
        client = mqtt.Client(userdata=userdata)

        client.tls_set_context()
        client.username_pw_set(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)

        client.on_connect = client_connect_callback
        client.on_disconnect = client_disconnect_callback
        client.on_message = client_message_callback

        client.connect_async(ADAFRUIT_IO_HOST, port=8883, keepalive=169)
        return client
    except Exception as e:
        logger.info("mqtt client did not work %s", e)
    return None


# =============================================================================


# external to this module
def do_iterate():
    global _state

    if not _state.mqtt_client:
        _state.mqtt_client = _setup_mqtt_client(_state.topics)
        if not _state.mqtt_client:
            logger.warning("got no mqttt client")
            time.sleep(30)
            return
        logger.debug("have a mqtt_client now")
        _state.mqtt_client.loop_start()

    try:
        cmdDill = _state.cmdq.get(True, CMDQ_GET_TIMEOUT)
        cmdFun, params = dill.loads(cmdDill)
        cmdFun(*params)
        # logger.debug("executed a lambda command with params %s", params)
    except queue.Empty:
        # logger.debug("mqttclient iterate noop")
        pass
    except (KeyboardInterrupt, SystemExit):
        pass


# =============================================================================


def _enqueue_cmd(l_dill_raw):
    global _state
    lDill = dill.dumps(l_dill_raw)
    try:
        _state.cmdq.put(lDill, False)
    except queue.Full:
        logger.error("command queue is full: cannot add")
        return False
    return True


# =============================================================================


def _signal_handler(_signal, _frame):
    _state.mqtt_client.loop_stop()
    logger.info("process terminated")
    sys.exit(0)


# =============================================================================


logger = log.getLogger()
if __name__ == "__main__":
    log.initLogger(testing=True)
    do_init(None)
    signal.signal(signal.SIGINT, _signal_handler)
    while True:
        do_iterate()
