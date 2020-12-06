#!/usr/bin/env python
from datetime import datetime
import multiprocessing
import signal
import sys
import time

import dill
from six.moves import queue
import stopit

from ada import const
from ada import events
from ada import log
from os import environ as env

# Import Adafruit IO MQTT client. It is actually an mqtt client wrapper.
from Adafruit_IO import MQTTClient
from Adafruit_IO import Client as RestClient
from Adafruit_IO import RequestError as RestRequestError

ADAFRUIT_IO_KEY = env['IO_KEY']
ADAFRUIT_IO_USERNAME = env['IO_USERNAME']
ADAFRUIT_IO_FORECAST_ID = env.get('IO_HOME_WEATHER')
ADAFRUIT_IO_RANDOM_ID = env.get('IO_RANDOM_ID')

CMDQ_SIZE = 900
CMDQ_GET_TIMEOUT = 300    # seconds
CONNECT_TIMEOUT = 180     # seconds
RE_SUBSCRIBE_TIME = 1201  # seconds
_state = None


class State(object):
    def __init__(self, queueEventFun, feed_ids, group_ids, forecasts):
        self.queueEventFun = queueEventFun  # queue for output events
        self.cmdq = multiprocessing.Queue(CMDQ_SIZE)  # queue for input commands
        self.feed_ids = feed_ids
        self.group_ids = group_ids
        self.forecasts = forecasts
        self.aio_client = None
        self.aio_client_connected = False
        self.aio_client_update_ts = None
        self.aio_rest_client = None
        self.aio_rest_feeds = set()
        self.lastMsgTimeStamp = None

    @property
    def mqtt_client_id(self):
        return const.MQTT_CLIENT_AIO


# =============================================================================


# external to this module, once
def do_init(queueEventFun=None):
    global _state

    feed_ids = const.AIO_FEED_IDS
    group_ids = {}
    # forecasts = ['current', 'forecast_hours_2', 'forecast_days_1', 'forecast_days_2']
    forecasts = ['current']

    _state = State(queueEventFun, feed_ids, group_ids, forecasts)
    # logger.debug("mqtt io client init called")
    return _state.cmdq


# =============================================================================

def _notifyMqttConnectEvent(event):
    global _state
    logger.info("got mqtt connect event %s", event)
    # reset timestamp used to checkpoint how long since a msg was received from adafruit.io
    _state.lastMsgTimeStamp = None
    _notifyEvent(events.MqttConnectEvent(_state.mqtt_client_id, event))


def _notifyMqttMsgEvent(topic, payload):
    global _state
    logger.info("got mqtt message %s %s", topic, payload)
    # reset timestamp used to checkpoint how long since a msg was received from adafruit.io
    _state.lastMsgTimeStamp = datetime.now()
    _notifyEvent(events.MqttMsgEvent(_state.mqtt_client_id, topic, payload))


def _notifyEvent(event):
    global _state
    if _state.queueEventFun:
        _state.queueEventFun(event)


# =============================================================================


def client_message_callback(_client, topic, payload):
    # logger.debug("callback for mqtt message %s %s", topic, payload)
    params = [topic, payload]
    _enqueue_cmd((_notifyMqttMsgEvent, params))


def _nuke_aio_client(_state):
    if not _state.aio_client:
        return

    try:
        with stopit.ThreadingTimeout(13.90, swallow_exc=False) as timeout_ctx:
            logger.info("releasing _state.aio_client")
            _state.aio_client.disconnect()
            _state.aio_client._client.loop_stop()
            del _state.aio_client
    except Exception as e:
        logger.error("failed to release _state.aio_client timeout_ctx %s %s",
                     timeout_ctx, e)
    _state.aio_client = None
    _state.aio_client_connected = False
    _state.aio_client_update_ts = None


def _iterate_aio_client():
    global _state

    if not _state.aio_rest_client:
        _state.aio_rest_client = RestClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)

    if not _state.aio_client:
        _state.aio_client = MQTTClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY, secure=True)
        _state.aio_client.on_message = client_message_callback
        _state.aio_client_connected = False
        _state.aio_client_update_ts = datetime.now()
        _state.aio_client.connect()
        _state.aio_client.loop_background()
        logger.debug("aio_client connect called")
        return

    is_connected = _state.aio_client.is_connected()
    if _state.aio_client_update_ts and not is_connected:
        tdelta = datetime.now() - _state.aio_client_update_ts
        tdeltaSecs = int(tdelta.total_seconds())
        if tdeltaSecs >= CONNECT_TIMEOUT:
            _nuke_aio_client(_state)
            return

    _check_subscription()
    if is_connected == _state.aio_client_connected:
        return

    # If execution makes it this far, is_connected is changing
    _state.aio_client_connected = is_connected
    _state.aio_client_update_ts = datetime.now()
    _notifyMqttConnectEvent(const.MQTT_CONNECTED
                            if _state.aio_client_connected else const.MQTT_DISCONNECTED)


def _check_subscription():
    global _state

    if not _state.aio_client_connected:
        return

    if _state.lastMsgTimeStamp:
        tdelta = datetime.now() - _state.lastMsgTimeStamp
        tdeltaSecs = int(tdelta.total_seconds())
        if tdeltaSecs < RE_SUBSCRIBE_TIME:
            return

    # slot subscriptions down, otherwise adafruit.io will ban you
    for feed_id in _state.feed_ids:
        _state.aio_client.subscribe(feed_id, qos=1)
        time.sleep(0.5)
    for group_id in _state.group_ids:
        _state.aio_client.subscribe_group(group_id, qos=1)
        time.sleep(0.5)
    if ADAFRUIT_IO_FORECAST_ID:
        for forecast in _state.forecasts:
            _state.aio_client.subscribe_weather(ADAFRUIT_IO_FORECAST_ID, forecast)
            time.sleep(0.5)
    if ADAFRUIT_IO_RANDOM_ID:
        _state.aio_client.subscribe_randomizer(ADAFRUIT_IO_RANDOM_ID)
    # _state.aio_client.subscribe_time('iso')
    logger.info("client %s subscribed to feeds, groups weather", _state.mqtt_client_id)
    # reset timer, so we do not subscribe again until next msg expiration
    _state.lastMsgTimeStamp = datetime.now()


# external to this module
def do_iterate():
    global _state
    _iterate_aio_client()
    try:
        queue_timeout = CMDQ_GET_TIMEOUT if _state.aio_client_connected else 1
        cmdDill = _state.cmdq.get(True, queue_timeout)
        cmdFun, params = dill.loads(cmdDill)
        cmdFun(*params)
        # logger.debug("executed a lambda command with params %s", params)
    except queue.Empty:
        _check_subscription()
    except (KeyboardInterrupt, SystemExit):
        pass


# =============================================================================


def _publish(feed_id, value=None, group_id=None):
    global _state
    if not _state.aio_client:
        logger.warning("no client to publish mqtt feed %s %s %s", feed_id, value, group_id)
        return
    if not _state.aio_client_connected:
        logger.warning("not connected client to publish feed %s %s %s", feed_id, value, group_id)
        return
    try:
        with stopit.ThreadingTimeout(9.90, swallow_exc=False) as timeout_ctx:
            # logger.debug("publishing mqtt topic %s %s", topic, newState)
            _state.aio_client.publish(feed_id, value, group_id)
    except Exception as e:
        logger.error("failed aio_client publish feed %s %s %s timeout_ctx %s %s",
                     feed_id, value, group_id, timeout_ctx, e)
        return
    logger.debug("published aio_client feed %s %s %s", feed_id, value, group_id)


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
def publish(feed_id, payload, group_id):
    translate_payload = {"on": 1, "off": 0}
    payload2 = translate_payload.get(payload, payload)
    params = [feed_id, payload2, group_id]
    return _enqueue_cmd((_publish, params))


# =============================================================================


def _receive_feed_value(feed_id):
    global _state

    if not _state.aio_rest_client:
        return
    if feed_id not in _state.aio_rest_feeds:
        try:
            _feed = _state.aio_rest_client.feeds(feed_id)
            _state.aio_rest_feeds.add(feed_id)
        except RestRequestError as e:
            logger.error("Requested unknown feed_id %s : %s", feed_id, e)
            return
        logger.info("feed_id %s located via aio_rest_client", feed_id)
    try:
        with stopit.ThreadingTimeout(16.16, swallow_exc=False) as timeout_ctx:
            # logger.debug("explicitly asking for feed_id/topic %s via rest", feed_id)
            feed_data = _state.aio_rest_client.receive(feed_id)
    except Exception as e:
        logger.error("failed get value for feed_id/topic %s timeout_ctx %s %s",
                     feed_id, timeout_ctx, e)
        return
    logger.debug("feed_id %s got data via rest %s", feed_id, feed_data)
    topic, payload = feed_id, feed_data.value
    _notifyEvent(events.MqttMsgEvent(_state.mqtt_client_id, topic, payload))


# external to this module
def receive_feed_value(feed_id, group=None):
    if group:
        feed_id = "{}.{}".format(group.replace("_", "-"), feed_id)
    params = [feed_id]
    return _enqueue_cmd((_receive_feed_value, params))


# =============================================================================


def _signal_handler(_signal, _frame):
    _state.aio_client.loop_stop()
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
