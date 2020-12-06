#!/usr/bin/env python
import multiprocessing
import signal
import sys

from datetime import datetime, timedelta
import dill
from six.moves import queue
import stopit
import requests

from ada import events
from ada import log
from os import environ as env


CMDQ_SIZE = 100
CMDQ_GET_TIMEOUT = 3606  # seconds.
_state = None


class State(object):
    def __init__(self, queueEventFun):
        self.queueEventFun = queueEventFun  # queue for output events
        self.cmdq = multiprocessing.Queue(CMDQ_SIZE)  # queue for input commands
        self.openweather_api = env.get('OPENWEATHER_API')
        self.openweather_city_id = env.get('OPENWEATHER_CITY_ID')
        self.openweather_fetch_interval = int(env.get('OPENWEATHER_INTERVAL', CMDQ_GET_TIMEOUT))
        self.last_fetch_ts = datetime.now()


# =============================================================================


# external to this module, once
def do_init(queueEventFun=None):
    global _state

    _state = State(queueEventFun)
    logger.debug("init called. State: %s", _state.__dict__)
    return _state.cmdq


# =============================================================================

def _notifyOpenweatherEvent(payload):
    global _state
    logger.info("got openweather message %s", payload)
    if _state.queueEventFun:
        _state.queueEventFun(events.OpenWeatherEvent(payload))


# =============================================================================


# external to this module
def do_iterate():
    global _state

    try:
        cmdDill = _state.cmdq.get(True, _state.openweather_fetch_interval)
        cmdFun, params = dill.loads(cmdDill)
        cmdFun(*params)
        logger.debug("executed a lambda command with params %s", params)
    except queue.Empty:
        # logger.debug("iterate noop")
        pass
    except (KeyboardInterrupt, SystemExit):
        pass

    if datetime.now() - _state.last_fetch_ts >= timedelta(
            seconds=_state.openweather_fetch_interval):
        _fetch()


# =============================================================================


def _fetch():
    global _state

    data = {'api': _state.openweather_api,
            'city_id': _state.openweather_city_id}
    if not all(data.values()):
        logger.info("not enough data for openweather api %s", data)
        return
    url = 'http://api.openweathermap.org/data/2.5/weather?id={}&appid={}&units=imperial'.format(
        data['city_id'], data['api'])
    payload = ''
    try:
        with stopit.ThreadingTimeout(18.90, swallow_exc=False) as timeout_ctx:
            res = requests.get(url, timeout=15)
            payload = res.json()
    except Exception as e:
        logger.error("failed to get url %s %s timeout_ctx %s %s", url, payload,
                     timeout_ctx, e)
        return
    _notifyOpenweatherEvent(payload)
    _state.last_fetch_ts = datetime.now()


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
def do_fetch():
    params = []
    return _enqueue_cmd((_fetch, params))

# =============================================================================


def _signal_handler(_signal, _frame):
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
