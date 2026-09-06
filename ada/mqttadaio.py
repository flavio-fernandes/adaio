#!/usr/bin/env python
from datetime import datetime
from datetime import timedelta
import multiprocessing
import paho.mqtt.client as mqtt
from ratelimiter import RateLimiter
import requests
import signal
import sys
import threading
import time

import dill
from six.moves import queue
import stopit

from ada import const
from ada import events
from ada import log
from ada.publishfilter import PublishFilter
from ada.publishfilter import feed_key
from os import environ as env

# Import Adafruit IO MQTT client. It is actually an mqtt client wrapper.
from Adafruit_IO import MQTTClient
from Adafruit_IO import Client as RestClient
from Adafruit_IO import Feed as RestFeed
from Adafruit_IO import Group as RestGroup
from Adafruit_IO import RequestError as RestRequestError

ADAFRUIT_IO_KEY = env['IO_KEY']
ADAFRUIT_IO_USERNAME = env['IO_USERNAME']
ADAFRUIT_IO_TIMEZONE = env.get('IO_TIMEZONE', 'America/New_York')
ADAFRUIT_IO_RANDOM_ID = env.get('IO_RANDOM_ID')

CMDQ_SIZE = 900
CMDQ_GET_TIMEOUT = 300    # seconds
CONNECT_TIMEOUT = 180     # seconds
RE_SUBSCRIBE_TIME = 1201  # seconds
# adafruit.io answers a client that redials too eagerly with "Not authorized",
# so wait longer between attempts instead of hammering it.
CONNECT_BACKOFF_MIN_SECS = 5
CONNECT_BACKOFF_MAX_SECS = 300
# Publishes paho refuses in a row before the client counts as broken.
PUBLISH_FAILURES_MAX = 5
# How long the client may stay unusable before this process gives up and exits
# to be rebuilt from scratch.
STUCK_TIMEOUT = 900       # seconds
LOOP_STOP_TIMEOUT = 15    # seconds
_state = None

TIME_SERVICE = (
    "https://io.adafruit.com/api/v2/%s/integrations/time/strftime?x-aio-key=%s&tz=%s"
)
# our strftime is %Y-%m-%d %H:%M:%S.%L %j %u %z %Z see http://strftime.net/ for decoding details
# See https://apidock.com/ruby/DateTime/strftime for full options
TIME_SERVICE_STRFTIME = (
    "&fmt=%25Y-%25m-%25d+%25H%3A%25M%3A%25S.%25L+%25j+%25u+%25z+%25Z"
)

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
        # Last moment the client was known good. The decision to stop trying
        # and let the process be restarted is measured against it.
        self.aio_client_healthy_ts = datetime.now()
        self.aio_connect_after_ts = None
        self.aio_connect_backoff_secs = CONNECT_BACKOFF_MIN_SECS
        self.publish_failures = 0
        self.aio_rest_client = None
        self.aio_rest_feeds = set()
        self.aio_rest_feeds_primed = False
        self.lastMsgTimeStamp = None
        # Fork-boundary invariant: publish() runs in the parent, while _publish()
        # runs in the child. Keep mutable dedup state in the child so only
        # successful publishes refresh the last-published timestamp.
        self.publish_filter = PublishFilter()

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


def _elapsed_secs(since_ts):
    if not since_ts:
        return 0
    return int((datetime.now() - since_ts).total_seconds())


def _harden_aio_client(aio_client):
    """Keep a callback from taking the paho network loop down with it.

    Adafruit_IO's own on_connect/on_disconnect handlers raise MQTTError on any
    non-zero result code, and an unexpected disconnect is a non-zero result
    code. paho re-raises that out of its network thread, which ends the thread
    for good: nothing reconnects afterwards, the flags the callbacks maintain
    keep reporting whatever they last reported, and published packets pile up
    in an out queue no one drains any more. That is how feeds go stale for
    hours while the service still looks like it is running.
    """
    paho_client = aio_client._client
    paho_client.suppress_exceptions = True
    paho_client.reconnect_delay_set(min_delay=CONNECT_BACKOFF_MIN_SECS,
                                    max_delay=CONNECT_BACKOFF_MAX_SECS)


def _aio_client_is_connected():
    """Whether the client is connected, without trusting a flag that can lie.

    Adafruit_IO answers from a bool it sets in its callbacks, so a network loop
    that died before running them leaves it answering True forever. Ask paho as
    well, and believe neither one once the loop that maintains them is gone.

    Every client we hold has had loop_background() called on it -- one that
    could not be looped never makes it into the state -- so no network thread
    at all is as good as a dead one. paho clears the attribute in loop_stop()
    and could grow other reasons to; a client whose loop we cannot see is one
    whose flags nobody is maintaining.
    """
    global _state

    aio_client = _state.aio_client
    if not aio_client:
        return False
    paho_client = aio_client._client
    loop_thread = getattr(paho_client, "_thread", None)
    if loop_thread is None or not loop_thread.is_alive():
        return False
    return bool(aio_client.is_connected() and paho_client.is_connected())


def _stop_network_loop(paho_client):
    """loop_stop() with a bound on the wait; False when the loop will not end.

    paho's own loop_stop() joins its network thread with no timeout, and a join
    that never returns cannot be broken out of by stopit: an asynchronous
    exception is delivered between bytecodes, never inside a blocking lock
    acquire. Waiting there forever would wedge this whole process.
    """
    loop_thread = getattr(paho_client, "_thread", None)
    paho_client._thread_terminate = True
    if loop_thread is None or loop_thread is threading.current_thread():
        return True
    loop_thread.join(LOOP_STOP_TIMEOUT)
    if loop_thread.is_alive():
        return False
    paho_client._thread = None
    return True


def _give_up_if_stuck():
    """Exit once the client cannot be talked back into working.

    Restarting is what a person ends up doing anyway, so do it for them: the
    parent notices this child died and takes the service down with it, and
    systemd starts everything again from scratch.
    """
    global _state

    stuck_secs = _elapsed_secs(_state.aio_client_healthy_ts)
    if stuck_secs < STUCK_TIMEOUT:
        return
    raise RuntimeError(
        "adafruit.io client unusable for {} seconds; exiting to be restarted".format(stuck_secs))


def _nuke_aio_client(_state):
    if not _state.aio_client:
        return

    logger.info("releasing _state.aio_client")
    paho_client = _state.aio_client._client
    try:
        with stopit.ThreadingTimeout(13.90, swallow_exc=False) as timeout_ctx:
            _state.aio_client.disconnect()
    except Exception as e:
        logger.error("failed to disconnect _state.aio_client timeout_ctx %s %s",
                     timeout_ctx, e)
    loop_stopped = _stop_network_loop(paho_client)

    _state.aio_client = None
    _state.aio_client_connected = False
    _state.aio_client_update_ts = None
    _state.publish_failures = 0
    _state.aio_connect_after_ts = (datetime.now() +
                                   timedelta(seconds=_state.aio_connect_backoff_secs))
    _state.aio_connect_backoff_secs = min(_state.aio_connect_backoff_secs * 2,
                                          CONNECT_BACKOFF_MAX_SECS)
    if not loop_stopped:
        raise RuntimeError("adafruit.io network loop will not stop; exiting to be restarted")


def _build_aio_client():
    global _state

    aio_client = MQTTClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY, secure=True)
    aio_client.on_message = client_message_callback
    _harden_aio_client(aio_client)
    _state.aio_client = aio_client
    _state.aio_client_connected = False
    _state.aio_client_update_ts = datetime.now()
    _state.publish_failures = 0
    try:
        aio_client.connect()
        aio_client.loop_background()
    except Exception as e:
        logger.error("failed to connect aio_client: %s", e)
        _nuke_aio_client(_state)
        return
    logger.debug("aio_client connect called")


def _iterate_aio_client():
    global _state

    if not _state.aio_rest_client:
        _state.aio_rest_client = RestClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY)

    if not _state.aio_client:
        _give_up_if_stuck()
        if _state.aio_connect_after_ts and datetime.now() < _state.aio_connect_after_ts:
            return
        _build_aio_client()
        return

    is_connected = _aio_client_is_connected()
    if is_connected != _state.aio_client_connected:
        # Report the change before acting on it. A disconnect that goes
        # unreported leaves the parent with nothing to watch: it only starts
        # its own clock once it is told this client dropped.
        _state.aio_client_connected = is_connected
        _state.aio_client_update_ts = datetime.now()
        _notifyMqttConnectEvent(const.MQTT_CONNECTED
                                if is_connected else const.MQTT_DISCONNECTED)
        if is_connected:
            _state.aio_connect_backoff_secs = CONNECT_BACKOFF_MIN_SECS
            _state.publish_failures = 0

    if is_connected and _state.publish_failures < PUBLISH_FAILURES_MAX:
        _state.aio_client_healthy_ts = datetime.now()
        _check_subscription()
        return

    _give_up_if_stuck()

    # A client that says it is connected but will not send anything is the
    # worst of the failures: nothing looks wrong while every value is lost.
    if _state.publish_failures >= PUBLISH_FAILURES_MAX:
        logger.error("recycling aio_client after %d publishes it would not send",
                     _state.publish_failures)
        _nuke_aio_client(_state)
        return

    if _elapsed_secs(_state.aio_client_update_ts) >= CONNECT_TIMEOUT:
        logger.warning("recycling aio_client: not connected for %d seconds",
                       CONNECT_TIMEOUT)
        _nuke_aio_client(_state)


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
    if ADAFRUIT_IO_RANDOM_ID:
        _state.aio_client.subscribe_randomizer(ADAFRUIT_IO_RANDOM_ID)
    # _state.aio_client.subscribe_time('iso')
    logger.info("client %s subscribed to feeds", _state.mqtt_client_id)
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

# Throttle adafruit calls
# https://pypi.org/project/ratelimiter/
# https://github.com/RazerM/ratelimiter
def _limited(until):
    duration = int(round(until - time.time()))
    logger.warning('Self rate limited publish, sleeping for {:d} seconds'.format(duration))


def _aio_feed_topic(feed_id, group_id=None):
    # The very topics Adafruit_IO's MQTTClient.publish() builds.
    if group_id is not None:
        return "{0}/feeds/{1}.{2}".format(ADAFRUIT_IO_USERNAME, group_id, feed_id)
    return "{0}/feeds/{1}".format(ADAFRUIT_IO_USERNAME, feed_id)


@RateLimiter(max_calls=30, period=60, callback=_limited)
def _publish_now(feed_id, value=None, group_id=None):
    global _state
    if not _state.aio_client:
        logger.warning("no client to publish mqtt feed %s %s %s", feed_id, value, group_id)
        return False
    if not _state.aio_client_connected:
        logger.warning("not connected client to publish feed %s %s %s", feed_id, value, group_id)
        return False
    try:
        with stopit.ThreadingTimeout(9.90, swallow_exc=False) as timeout_ctx:
            # Publish through paho itself: Adafruit_IO builds this same topic
            # and then drops the result code on the floor, so a value that only
            # made it as far as an out queue looks just like a delivered one.
            msg_info = _state.aio_client._client.publish(
                _aio_feed_topic(feed_id, group_id), payload=value)
    except Exception as e:
        logger.error("failed aio_client publish feed %s %s %s timeout_ctx %s %s",
                     feed_id, value, group_id, timeout_ctx, e)
        _state.publish_failures += 1
        return False
    if msg_info.rc != mqtt.MQTT_ERR_SUCCESS:
        _state.publish_failures += 1
        logger.error("aio_client would not send feed %s %s %s: %s (%d in a row)",
                     feed_id, value, group_id, mqtt.error_string(msg_info.rc),
                     _state.publish_failures)
        return False
    _state.publish_failures = 0
    logger.debug("published aio_client feed %s %s %s", feed_id, value, group_id)
    return True


# Adafruit IO creates a feed on the fly when a publish names a key it does not
# know. That auto-create is not atomic: two publishes for a brand new key racing
# in the same instant leave two feeds sharing one key. Create feeds explicitly
# over rest, so the very first publish always names a feed that already exists.
def _prime_known_feeds():
    global _state

    if _state.aio_rest_feeds_primed:
        return True
    if not _state.aio_rest_client:
        return False
    try:
        with stopit.ThreadingTimeout(30.30, swallow_exc=False) as timeout_ctx:
            feeds = _state.aio_rest_client.feeds()
    except Exception as e:
        logger.error("failed to list aio feeds timeout_ctx %s %s", timeout_ctx, e)
        return False
    keys = [feed.key for feed in feeds]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        logger.error("adafruit.io has feeds sharing a key: %s", ", ".join(duplicates))
    _state.aio_rest_feeds.update(keys)
    _state.aio_rest_feeds_primed = True
    logger.info("primed %d known aio feed keys via rest", len(keys))
    return True


def _ensure_group(group):
    global _state

    try:
        _state.aio_rest_client.groups(group)
        return
    except RestRequestError:
        pass
    logger.info("creating aio group %s via rest", group)
    _state.aio_rest_client.create_group(RestGroup(name=group))


def _ensure_feed(feed_id, group_id, key):
    global _state

    if not _prime_known_feeds() or key in _state.aio_rest_feeds:
        return
    group = group_id.replace("_", "-") if group_id else None
    # Add the key even when creating fails, so a feed we cannot create does not
    # turn every message for it into another rest call.
    _state.aio_rest_feeds.add(key)
    try:
        with stopit.ThreadingTimeout(30.30, swallow_exc=False) as timeout_ctx:
            if group:
                _ensure_group(group)
            _state.aio_rest_client.create_feed(RestFeed(name=feed_id), group_key=group)
    except Exception as e:
        logger.error("failed to create aio feed %s timeout_ctx %s %s", key, timeout_ctx, e)
        return
    logger.info("created aio feed %s via rest", key)


def _publish(feed_id, value=None, group_id=None):
    global _state
    key = feed_key(feed_id, group_id)
    if not _state.publish_filter.should_publish(key, value):
        _state.publish_filter.record_suppressed()
        logger.debug("suppressed unchanged aio_client feed %s %s counters %s",
                     key, value, _state.publish_filter.counters)
        return False
    # Best effort: publish even when this fails, as losing a value is worse.
    _ensure_feed(feed_id, group_id, key)
    if not _publish_now(feed_id, value, group_id):
        return False
    _state.publish_filter.record_published(key, value)
    return True


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
    key = feed_key(feed_id, group_id)
    if _state.publish_filter.is_denied(key):
        _state.publish_filter.record_denied()
        logger.debug("denied aio_client feed %s %s counters %s",
                     key, payload2, _state.publish_filter.counters)
        return False
    params = [feed_id, payload2, group_id]
    return _enqueue_cmd((_publish, params))


# =============================================================================


def _get_local_time():
    api_url = TIME_SERVICE % (
        ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY, ADAFRUIT_IO_TIMEZONE)
    api_url += TIME_SERVICE_STRFTIME
    try:
        response = requests.get(api_url, timeout=10)
    except Exception as e:
        logger.error(f"Failed get local time: {e}")
        return
    if response.status_code != 200:
        logger.error(f"Unable get local time: {response.status_code}")
        return
    logger.debug(f"Local time reply: {response.text}")
    times = response.text.split(" ")
    the_date = times[0]
    the_time = times[1]
    year_day = int(times[2])
    week_day = int(times[3])
    is_dst = None  # no way to know yet
    year, month, mday = [int(x) for x in the_date.split("-")]
    the_time = the_time.split(".")[0]
    hours, minutes, seconds = [int(x) for x in the_time.split(":")]
    now = time.struct_time(
        (year, month, mday, hours, minutes, seconds, week_day, year_day, is_dst)
    )
    _notifyEvent(events.LocalTimeEvent(response.text, now))
    response.close()


# external to this module
def get_local_time():
    return _enqueue_cmd((_get_local_time, []))


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
    if _state and _state.aio_client:
        _stop_network_loop(_state.aio_client._client)
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
