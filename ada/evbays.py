#!/usr/bin/env python
import json
import multiprocessing
import signal
import sys

from datetime import datetime, timedelta
import dill
from six.moves import queue

from ada import events
from ada import log
from os import environ as env
from os import path


EVBAYS_FILE = "/vagrant/evbays/sema.json"
CMDQ_SIZE = 100
CMDQ_GET_TIMEOUT = 10  # seconds.
_state = None


def use_evbays():
    return env.get("SEMA_LOGIN")


class State(object):
    def __init__(self, queueEventFun):
        self.queueEventFun = queueEventFun  # queue for output events
        self.cmdq = multiprocessing.Queue(CMDQ_SIZE)  # queue for input commands
        self.evbays_fetch_interval = int(env.get("EVBAYS_INTERVAL", CMDQ_GET_TIMEOUT))
        self.evbays_filename = env.get("EVBAYS_FILE", EVBAYS_FILE)
        self.last_fetch_mtime = None
        self.last_fetch_ts = datetime.now()
        self.last_fetch_payload = None


# =============================================================================


# external to this module, once
def do_init(queueEventFun=None):
    global _state

    _state = State(queueEventFun)
    logger.debug("init called. State: %s", _state.__dict__)
    return _state.cmdq


# =============================================================================


def _notifyEVBaysEvent(payload):
    global _state
    logger.info("got evbays message %s", payload)
    if _state.queueEventFun:
        _state.queueEventFun(events.EVBaysEvent(payload))


# =============================================================================


# external to this module
def do_iterate():
    global _state

    try:
        cmdDill = _state.cmdq.get(True, _state.evbays_fetch_interval)
        cmdFun, params = dill.loads(cmdDill)
        cmdFun(*params)
        logger.debug("executed a lambda command with params %s", params)
    except queue.Empty:
        # logger.debug("iterate noop")
        pass
    except (KeyboardInterrupt, SystemExit):
        pass

    if datetime.now() - _state.last_fetch_ts >= timedelta(
        seconds=_state.evbays_fetch_interval
    ):
        _fetch()


# =============================================================================


def _is_mtime_changed(state_mtime, new_mtime):
    if not state_mtime:
        return True
    return new_mtime - state_mtime > 60


# =============================================================================


def _fetch(force=False):
    global _state

    try:
        mtime = path.getmtime(_state.evbays_filename)
        with open(_state.evbays_filename, "r", encoding="utf-8") as sema_file:
            payload = sema_file.read()
            data = json.loads(payload)
            _state.last_fetch_ts = datetime.now()
            if (
                force
                or payload != _state.last_fetch_payload
                or _is_mtime_changed(_state.last_fetch_mtime, mtime)
            ):
                logger.debug("Parsed %s: %s", EVBAYS_FILE, data)
                _state.last_fetch_payload = payload
                _state.last_fetch_mtime = mtime
                _notifyEVBaysEvent(payload)
    except Exception as e:
        logger.error("Unable to load and parse %s: %s", EVBAYS_FILE, e)


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
def do_fetch(force=False):
    params = [force]
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


# =============================================================================
