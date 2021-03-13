#!/usr/bin/env python
import multiprocessing
import signal
import sys
import time
from datetime import datetime, timedelta
from os import environ as env

import dill
import stopit
from six.moves import queue

from ada import events
from ada import log
from .sense_api import SenseApi
from .sense_api import VALID_SCALES as sense_scales

CMDQ_SIZE = 100
CMDQ_GET_TIMEOUT = 601  # seconds.
_state = None


def use_sense_energy():
    return env.get('SENSE_USERNAME') and env.get('SENSE_PASSWORD')


class State(object):
    def __init__(self, queueEventFun):
        self.queueEventFun = queueEventFun  # queue for output events
        self.cmdq = multiprocessing.Queue(CMDQ_SIZE)  # queue for input commands
        self.last_fetch_ts = datetime.now()
        self.sense_api = None
        self.all_devices = None
        self.sense_api_fails = 0
        self.cached_yearly_production = 0
        self.cached_yearly_consumption = 0


# =============================================================================


# external to this module, once
def do_init(queueEventFun=None):
    global _state

    _state = State(queueEventFun)
    logger.debug("init called. State: %s", _state.__dict__)
    return _state.cmdq


# =============================================================================

def _notifySenseEnergyEvent(collected_values):
    global _state
    logger.info("got sense energy values %s", collected_values)
    if not _state.queueEventFun:
        return

    # Deal with devices separately
    all_devices = sorted(collected_values.pop('all_devices'))
    active_devices = collected_values.pop('active_devices')

    for key, value in collected_values.items():
        _state.queueEventFun(events.SenseEnergyEvent(f"/sense/data/{key}", value))
        time.sleep(0.5)

    for device in all_devices:
        value = 'on' if device in active_devices else 'off'
        _state.queueEventFun(events.SenseEnergyEvent(f"/sense/device/{device}", value))
        time.sleep(0.5)


# =============================================================================


# external to this module
def do_iterate():
    global _state

    try:
        cmdDill = _state.cmdq.get(True, CMDQ_GET_TIMEOUT)
        cmdFun, params = dill.loads(cmdDill)
        cmdFun(*params)
        logger.debug("executed a lambda command with params %s", params)
    except queue.Empty:
        # logger.debug("iterate noop")
        pass
    except (KeyboardInterrupt, SystemExit):
        pass

    if datetime.now() - _state.last_fetch_ts >= timedelta(seconds=CMDQ_GET_TIMEOUT):
        _fetch()


# =============================================================================


def _fetch():
    global _state

    collected_values = {}
    try:
        with stopit.ThreadingTimeout(28.90, swallow_exc=False) as timeout_ctx:
            if not _state.sense_api:
                _state.sense_api = SenseApi(
                    username=env.get('SENSE_USERNAME'),
                    password=env.get('SENSE_PASSWORD'))
            _state.sense_api.update_realtime()
            _state.sense_api.update_trend_data()

            ignore_devices = {'other', 'always on'}
            # Load up all devices, once
            if not _state.all_devices:
                monitor_info = _state.sense_api.get_monitor_info()
                logger.info(f"sense monitor info {monitor_info}")
                _state.all_devices = {
                    device
                    for device in _state.sense_api.get_discovered_device_names()
                    if device.lower() not in ignore_devices}
                logger.info(f"sense known devices are {_state.all_devices}")

            collected_values['active_power'] = _state.sense_api.active_power
            # Include solar only if it is making meaningful power (more than 2 watts)
            active_solar_power = _state.sense_api.active_solar_power
            collected_values['active_solar_power'] = active_solar_power if (
                    active_solar_power > 2) else 0
            collected_values['grid_power'] = (collected_values['active_power'] -
                    collected_values['active_solar_power'])
            collected_values['all_devices'] = [
                device.lower().replace(' ', '_')
                for device in _state.all_devices]
            collected_values['active_devices'] = {
                device.lower().replace(' ', '_')
                for device in _state.sense_api.active_devices
                if device in _state.all_devices and (
                    device.lower() != 'solar' or collected_values['active_solar_power'])}

            # Hack: work around issue where value goes backwards at midnight
            new_yearly_production = _state.sense_api.yearly_production
            if _state.cached_yearly_production > new_yearly_production:
                logger.warning(f"Skipping backwards yearly_production "
                               f"new:{new_yearly_production} "
                               f"old:{_state.cached_yearly_production}")
            else:
                collected_values['yearly_production'] = new_yearly_production
                _state.cached_yearly_production = new_yearly_production

            new_yearly_consumption = _state.sense_api.yearly_consumption
            if _state.cached_yearly_consumption > new_yearly_consumption:
                logger.warning(f"Skipping backwards yearly_consumption "
                               f"new:{new_yearly_consumption} "
                               f"old:{_state.cached_yearly_consumption}")
            else:
                collected_values['yearly_consumption'] = new_yearly_consumption
                _state.cached_yearly_consumption = new_yearly_consumption

            for sense_scale in sense_scales:
                scale_key = 'consumption_{}'.format(sense_scale.lower())
                collected_values[scale_key] = _state.sense_api.get_consumption_trend(sense_scale)
        _state.sense_api_fails = 0
    except Exception as e:
        _state.sense_api_fails += 1
        logger.error("failed to fetch sense_api %s %s fails %d timeout_ctx %s",
                     collected_values, timeout_ctx, _state.sense_api_fails, e)
        # Try to clear fails by starting api session over
        if _state.sense_api_fails > 2:
            _state.sense_api = None
            _state.sense_api_fails = 0
        return
    _notifySenseEnergyEvent(collected_values)
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
