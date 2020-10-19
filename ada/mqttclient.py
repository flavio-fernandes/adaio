#!/usr/bin/env python
import datetime
import multiprocessing
import signal
import sys
import time

import dill
import paho.mqtt.client as mqtt
from six.moves import queue
import stopit

from ada import const
from ada import events
from ada import log


CMDQ_SIZE = 100
CMDQ_GET_TIMEOUT = 66  # seconds. May affect ping publishing
TOPIC_QOS = 1
_state = None


class State(object):
    def __init__(self, queueEventFun, mqtt_broker_ip, mqtt_client_id, topics):
        self.queueEventFun = queueEventFun  # queue for output events
        self.cmdq = multiprocessing.Queue(CMDQ_SIZE)  # queue for input commands
        self.mqtt_broker_ip = mqtt_broker_ip
        self.mqtt_client_id = mqtt_client_id
        self.topics = topics
        self.mqtt_client = None
        self.connected = False
        # self.next_ping_ts = datetime.datetime.now()


# =============================================================================


# external to this module, once
def do_init(queueEventFun=None):
    global _state

    mqtt_broker_ip = const.MQTT_LOCAL_BROKER_IP
    mqtt_client_id = const.MQTT_CLIENT_LOCAL
    topics = const.MQTT_LOCAL_TOPICS

    _state = State(queueEventFun, mqtt_broker_ip, mqtt_client_id, topics)
    # logger.debug("mqttclient init called")


# =============================================================================

def _notifyMqttConnectEvent(event, rc):
    global _state
    if event == const.MQTT_CONNECTED:
        logger.info("got mqtt connect event %s %s", event, rc)
        _state.connected = True
    else:
        if _state.mqtt_client:
            logger.warning("got mqtt disconnect event %s %s . Purging client", event, rc)
            _state.mqtt_client.loop_stop()
            _state.mqtt_client = None
    _notifyEvent(events.MqttConnectEvent(_state.mqtt_client_id, event, rc))


def _notifyMqttMsgEvent(topic, payload):
    global _state
    logger.info("got mqtt message %s %s", topic, payload)
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
    logger.debug("callback for mqtt message %s %s", msg.topic, msg.payload)
    topic = msg.topic.decode('utf-8') if isinstance(msg.topic, bytes) else msg.topic
    payload = msg.payload.decode('utf-8') if isinstance(msg.payload, bytes) else msg.payload
    params = [topic, payload]
    _enqueue_cmd((_notifyMqttMsgEvent, params))


def _setup_mqtt_client(broker_ip, client_id, topics):
    try:
        userdata = ['topics'] + topics
        client = mqtt.Client(client_id=client_id, userdata=userdata)
        client.on_connect = client_connect_callback
        client.on_disconnect = client_disconnect_callback
        client.on_message = client_message_callback

        client.connect_async(broker_ip, port=1883, keepalive=179)
        logger.info("setting up mqtt client to broker %s", broker_ip)
        return client
    except Exception as e:
        logger.info("mqtt client did not work %s", e)
    return None


# =============================================================================


# external to this module
def do_iterate():
    global _state

    if not _state.mqtt_client:
        _state.mqtt_client = _setup_mqtt_client(_state.mqtt_broker_ip, _state.mqtt_client_id,
                                                _state.topics)
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
        logger.debug("executed a lambda command with params %s", params)
    except queue.Empty:
        # logger.debug("mqttclient iterate noop")
        pass
    except (KeyboardInterrupt, SystemExit):
        pass


# =============================================================================


def _mqtt_publish(topic, payload=None, qos=0, retain=False, properties=None):
    global _state
    if not _state.mqtt_client:
        logger.warning("no client to publish mqtt topic %s %s", topic, payload)
        return
    try:
        with stopit.ThreadingTimeout(9.90, swallow_exc=False) as timeout_ctx:
            # logger.debug("publishing mqtt topic %s %s", topic, newState)
            info = _state.mqtt_client.publish(topic, payload, qos, retain, properties)
            info.wait_for_publish()
    except Exception as e:
        logger.error("client failed publish mqtt topic %s %s timeout_ctx %s %s", topic, payload,
                     timeout_ctx, e)
        return
    logger.debug("published mqtt topic %s %s", topic, payload)


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


# external to this module
def do_mqtt_publish(topic, payload=None, qos=0, retain=False, properties=None):
    params = [topic, payload, qos, retain, properties]
    return _enqueue_cmd((_mqtt_publish, params))

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
