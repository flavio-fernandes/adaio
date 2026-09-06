#!/usr/bin/env python
import copy
import json
import multiprocessing
import subprocess
import time
import logging
import os
from datetime import datetime, timedelta
from os import environ as env

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from six.moves import queue

from ada import const
from ada import events
from ada import log
from ada import mqttadaio
from ada import mqttadaiothrottle
from ada import mqttclient
from ada import oweather
from ada import sdnotify
from ada import senseenergy

EVENTQ_SIZE = 1000
EVENTQ_GET_TIMEOUT = 15  # seconds


class ProcessBase(multiprocessing.Process):
    # Longest a single trip around this child's loop is expected to take. Its
    # command queue timeout dominates, so each child sets its own.
    max_iteration_secs = EVENTQ_GET_TIMEOUT

    def __init__(self, client_id_param, eventq_param):
        multiprocessing.Process.__init__(self)
        self.client_id = client_id_param
        self.eventq = eventq_param
        self.cmdq = None
        self.disconnect_ts = None
        # Written by the child, read by the parent. A child can stay alive with
        # a wedged loop -- a network thread that died holding nothing but its
        # flags, a queue nobody drains -- and looking alive is exactly what
        # made the last outage last for hours.
        self.heartbeat = multiprocessing.Value('d', time.time())

    def beat(self):
        self.heartbeat.value = time.time()

    @property
    def heartbeat_age_secs(self):
        return time.time() - self.heartbeat.value

    @property
    def heartbeat_timeout_secs(self):
        # Two full iterations of slack, so a child that merely runs long is
        # never mistaken for one that stopped.
        return (self.max_iteration_secs * 2) + 60

    def putEvent(self, event):
        try:
            self.eventq.put(event, False)
        except queue.Full:
            logger.error("Exiting: Queue is stuck, cannot add event: %s %s",
                         event.name, event.description)
            raise RuntimeError("Main process has a full event queue")

    def cmdq_is_full(self):
        return self.cmdq and self.cmdq.full()


class MqttclientProcess(ProcessBase):
    max_iteration_secs = mqttclient.CMDQ_GET_TIMEOUT

    def __init__(self, eventq_param):
        ProcessBase.__init__(self, const.MQTT_CLIENT_LOCAL, eventq_param)
        self.cmdq = mqttclient.do_init(self.putEvent)

    def run(self):
        logger.debug("mqttclient process started")
        while True:
            self.beat()
            mqttclient.do_iterate()


class MqttAdaIoProcess(ProcessBase):
    max_iteration_secs = mqttadaio.CMDQ_GET_TIMEOUT

    def __init__(self, eventq_param):
        ProcessBase.__init__(self, const.MQTT_CLIENT_AIO, eventq_param)
        self.cmdq = mqttadaio.do_init(self.putEvent)

    def run(self):
        logger.debug("mqtt ada io process started")
        while True:
            self.beat()
            mqttadaio.do_iterate()


class MqttAdaIoThrottleProcess(ProcessBase):
    max_iteration_secs = mqttadaiothrottle.CMDQ_GET_TIMEOUT

    def __init__(self, eventq_param):
        ProcessBase.__init__(self, const.MQTT_CLIENT_AIO_THROTTLE, eventq_param)
        self.cmdq = mqttadaiothrottle.do_init(self.putEvent)

    def run(self):
        logger.debug("mqtt ada io throttle process started")
        while True:
            self.beat()
            mqttadaiothrottle.do_iterate()


class OWeatherProcess(ProcessBase):
    def __init__(self, eventq_param):
        ProcessBase.__init__(self, None, eventq_param)
        self.cmdq = oweather.do_init(self.putEvent)
        # The fetch interval is configurable, so read it back rather than
        # assuming the default.
        self.max_iteration_secs = oweather.fetch_interval_secs()

    def run(self):
        logger.debug("openweather process started")
        while True:
            self.beat()
            oweather.do_iterate()


class SenseEnergyProcess(ProcessBase):
    max_iteration_secs = senseenergy.CMDQ_GET_TIMEOUT

    def __init__(self, eventq_param):
        ProcessBase.__init__(self, None, eventq_param)
        self.cmdq = senseenergy.do_init(self.putEvent)

    def run(self):
        logger.debug("sense energy process started")
        while True:
            self.beat()
            senseenergy.do_iterate()


def _handle_device_json(feed_id, payload, search_attributes):
    try:
        _payload_float = float(payload)
        return feed_id, payload
    except ValueError:
        pass

    try:
        payload_dict = json.loads(payload)
        payload2 = None
        for search_attribute in search_attributes:
            if search_attribute in payload_dict:
                payload2 = payload_dict[search_attribute]
                break
    except Exception as e:
        logger.warning(f"Failed to extract {search_attributes} from {feed_id} {payload} {e}")
        return None, None
    if payload2 is None:
        logger.warning(f"Failed to find any of {search_attributes} from {feed_id} in {payload}")
        return None, None
    return feed_id, payload2


def handle_device_memory(feed_id, payload):
    return _handle_device_json(feed_id, payload, ('mem_free', 'freeKb',))


def handle_device_uptime(feed_id, payload):
    return _handle_device_json(feed_id, payload, ('uptime_mins', 'up',))


def handle_aio_cmd(_feed_id, payload):
    if payload == const.AIO_LOCAL_CMD_GET_LOCAL_TIME_WEATHER:
        logger.debug("Got explicit request to get time and weather")
        _fetch_local_time()
        oweather.do_fetch()
    # Return none so there is not a publish to aio from this
    return None, None


def handle_home_motion(feed_id, payload):
    # Note: aio publish will also translate "on" and "off". See: mqttadaio.py publish
    translate_payload = {"true": 1, "false": 0}
    payload2 = translate_payload.get(payload, payload)
    # "zwave/shed/notification/endpoint_0/Home_Security/Motion_sensor_status"  value: "8"
    # "zwave/shed/notification/endpoint_0/Home_Security/Motion_sensor_status"  value: "0"
    translate_payload_shed = {"8": 1, "0": 0}
    payload3 = translate_payload_shed.get(payload2, payload2)
    return feed_id, payload3


def handle_home_zone(feed_id, payload):
    if feed_id in ("garage-east", "garage-west"):
        translate_payload = {"open": 1, "opening": 1}
        payload2 = translate_payload.get(payload, 0)
        return feed_id, payload2
    return feed_id, payload


def _fetch_local_time():
    mqttadaio.get_local_time()


def _set_should_check_children():
    global should_check_children
    should_check_children = True


def _start_periodic_jobs():
    global scheduler

    # Ref: https://python.hotexamples.com/examples/apscheduler.schedulers.background/BackgroundScheduler/add_job/python-backgroundscheduler-add_job-method-examples.html
    scheduler.add_job(_set_should_check_children, 'interval', seconds=66,
                      id='periodic_set_should_check_children',
                      max_instances=1)
    scheduler.add_job(_fetch_local_time, 'interval', minutes=55,
                      id='periodic_fetch_local_time',
                      max_instances=1, next_run_time=datetime.now() + timedelta(minutes=30))


def _get_process(client_id):
    global myProcesses

    for p in myProcesses:
        if p.client_id == client_id:
            return p


# TODO(flaviof): this needs to be more generic
def processMqttMsgEvent(client_id, topic, payload):
    global scheduler

    logger.debug("processMqttMsgEvent %s %s %s", client_id, topic, payload)
    if client_id == const.MQTT_CLIENT_LOCAL:
        payload_handlers = {
            const.AIO_LOCAL_CMD: handle_aio_cmd,
            const.AIO_HOME_MOTION: handle_home_motion,
            const.AIO_HOME_ZONE: handle_home_zone,
            const.AIO_UPTIME_MINUTES: handle_device_uptime,
            const.AIO_MEMORY: handle_device_memory,
        }
        topic_entry = const.MQTT_LOCAL_MAP.get(topic)
        if not topic_entry:
            # search for topic in wildcard entries (entries with local topic that ends with '#')
            topic_entry = next((entry for entry in const.LOCAL_ENTRIES
                                if entry.local[-1] == "#" and
                                topic.startswith(entry.local[:-1])), None)
        if topic_entry:
            # extract feed_id from topic if topic_entry.feed_id is ""
            feed_id = (topic.split("/")[-1].replace("_", "-")
                       if not topic_entry.feed_id
                       else topic_entry.feed_id)
            payload_copy = copy.copy(payload)
            group_ids = topic_entry.group_id if isinstance(topic_entry.group_id, list) else [
                topic_entry.group_id]
            for group_id in group_ids:
                if group_id in payload_handlers:
                    feed_id, payload = payload_handlers[group_id](feed_id, payload)
                if feed_id and payload is not None:
                    mqttadaio.publish(feed_id, payload, group_id)
                payload = copy.copy(payload_copy)
    elif client_id == const.MQTT_CLIENT_AIO_THROTTLE:
        logger.warning("getting hot: %s %s", topic, payload)
        time.sleep(10)
    elif client_id == const.MQTT_CLIENT_AIO:
        # rename variables to (try to) make it less confusing
        feed_id, topic = topic, None
        topic_entry = const.MQTT_REMOTE_MAP.get(feed_id)
        if not topic_entry:
            return
        translate_payload = {"1": "on", "0": "off"}
        payload2 = translate_payload.get(str(payload), payload)
        mqttclient.do_mqtt_publish(topic_entry.local, payload2)


def processMqttConnEvent(client_id, event, rc):
    logger.debug("processMqttConnEvent client_id: %s event: %s rc: %s", client_id, event, rc)
    if client_id == const.MQTT_CLIENT_AIO:
        mqttclient.do_mqtt_publish(const.AIO_TOPIC_CONNECTION,
                                   {const.MQTT_CONNECTED: "true"}.get(event, "false"))
        if event == const.MQTT_CONNECTED:
            _fetch_local_time()
    elif client_id == const.MQTT_CLIENT_LOCAL:
        oweather.do_fetch()
        senseenergy.do_fetch()

    p = _get_process(client_id)
    if p:
        # Set process disconnect timestamp if that is None, or clear it if we are connected
        if event == const.MQTT_CONNECTED:
            p.disconnect_ts = None
        elif p.disconnect_ts is None:
            p.disconnect_ts = datetime.now()


def processEventMqttClient(event):
    syncFunHandlers = {"MqttMsgEvent": processMqttMsgEvent,
                       "MqttConnectEvent": processMqttConnEvent, }
    cmdFun = syncFunHandlers.get(event.name)
    if not cmdFun:
        logger.warning("Don't know how to process event %s: %s", event.name, event.description)
        return
    if event.params:
        cmdFun(*event.params)
    else:
        cmdFun()


def processEventLocalTime(event):
    if event.name != "LocalTimeEvent":
        logger.warning("Don't know how to process event %s: %s", event.name, event.description)
        return
    time_text, _struct_time = event.params
    logger.info(f"processEventLocalTime: {time_text}")
    mqttclient.do_mqtt_publish(const.AIO_TOPIC_LOCAL_TIME, time_text)


def processOWeatherEvent(event):
    if event.name != "OpenWeatherEvent":
        logger.warning("Don't know how to process event %s: %s", event.name, event.description)
        return
    payload = event.params[0]
    logger.info("processOWeatherEvent: {}".format(payload))
    oweather_topics = {'raw': json.dumps(payload)}

    # {'coord': {'lon': -tiki.2278, 'lat': -tiki.5311},
    # 'weather': [{'id': 502, 'main': 'Rain', 'description': 'heavy intensity rain', 'icon': '10n'}],
    # 'base': 'stations',
    # 'main': {'temp': 44.78, 'feels_like': 43.77, 'temp_min': 42.01, 'temp_max': 47.17,
    # 'pressure': 1017, 'humidity': 91},
    # 'visibility': 6437,
    # 'wind': {'speed': 3, 'deg': 69, 'gust': 11.01},
    # 'rain': {'1h': 4.6}, 'clouds': {'all': 90}, 'dt': 1622261201,
    # 'sys': {'type': 2, 'country': 'US',
    # 'sunrise': 1622279546, 'sunset': 1622333659},
    # 'timezone': -14400}

    data_sys = payload.get('sys', {})
    sunrise_raw = data_sys.get('sunrise')
    # ref: https://stackoverflow.com/questions/12400256/converting-epoch-time-into-the-datetime
    #      https://strftime.org/
    # time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(sunrise_raw))
    if sunrise_raw:
        oweather_topics['sunrise'] = time.strftime('%-H:%M', time.localtime(sunrise_raw))
    sunset_raw = data_sys.get('sunset')
    if sunset_raw:
        oweather_topics['sunset'] = time.strftime('%-H:%M', time.localtime(sunset_raw))

    # 'main': {'temp': 44.78, 'feels_like': 43.77, 'temp_min': 42.01, 'temp_max': 47.17,
    #          'pressure': 1017, 'humidity': 91},
    data_main = payload.get('main', {})
    for k, v in data_main.items():
        oweather_topics[k] = v

    for topic, mqtt_payload in oweather_topics.items():
        mqttclient.do_mqtt_publish('/openweather/{}'.format(topic), mqtt_payload)

    logger.debug("translating oweather into aio weather")
    try:
        aioweather_payload = oweather_to_aioweather(payload)
        mqttclient.do_mqtt_publish(const.AIO_TOPIC_WEATHER_CURRENT, json.dumps(aioweather_payload))
    except ValueError as e:
        logger.warning("unable to translate oweather to aio weather %s", e)

def oweather_to_aioweather(ow):
    aiow = {}
    aiow['summary'] = ow.get('weather',[{}])[0].get('description', '')
    aiow['windSpeed'] = int(ow.get('wind',{}).get('speed', 0))
    aiow['precipProbabilityPercent'] = ''
    aiow['pressure'] = ow.get('main',{}).get('pressure', '?')
    aiow['nearestStormDistance'] = ''
    aiow['visibility'] = ow.get('visibility', '?')
    aiow['dewPoint'] = ow.get('main',{}).get('feels_like', '?')
    aiow['cloudCover'] = ow.get('clouds',{}).get('all', '?')
    aiow['windGust'] = int(ow.get('wind',{}).get('gust', 0))
    aiow['windDeg'] = ow.get('wind',{}).get('deg', '?')
    aiow['precipIntensity'] = ''
    aiow['temperature'] = ow.get('main',{}).get('temp', '?')
    aiow['apparentTemperature'] = ''
    aiow['humidity'] = ow.get('main',{}).get('humidity', '?')
    aiow['uvIndex'] = ''
    aiow['ozone'] = ''
    return aiow

def processSenseEnergyEvent(event):
    if event.name != "SenseEnergyEvent":
        logger.warning("Don't know how to process event %s: %s", event.name, event.description)
        return
    key = event.params[0]
    value = event.params[1]
    logger.info(f"processSenseEnergyEvent: {key} = {value}")
    mqttclient.do_mqtt_publish(key, value)


def processEvent(event):
    # Based on the event, call a lambda to make mqtt and smartswitch in sync
    syncFunHandlers = {"mqtt": processEventMqttClient,
                       "local_time": processEventLocalTime,
                       "open_weather": processOWeatherEvent,
                       "sense_energy": processSenseEnergyEvent,
                       }
    cmdFun = syncFunHandlers.get(event.group)
    if not cmdFun:
        logger.warning("Don't know how to process event %s: %s", event.name, event.description)
        return
    cmdFun(event)


def check_child_processes():
    def time_to_quit(msg):
        logger.error(msg)
        logger.error("exiting so systemd can restart")
        raise RuntimeError("Child process is not well")

    for p in myProcesses:
        if not p.is_alive():
            time_to_quit("{} child died".format(p.__class__.__name__))
        if p.cmdq_is_full():
            time_to_quit("{} child has full queue".format(p.__class__.__name__))
        heartbeat_age = int(p.heartbeat_age_secs)
        if heartbeat_age > p.heartbeat_timeout_secs:
            time_to_quit("{} child stopped making progress {} seconds ago".format(
                p.__class__.__name__, heartbeat_age))
        if p.disconnect_ts:
            disconnect_interval = datetime.now() - p.disconnect_ts
            disconnect_minutes = int(disconnect_interval.total_seconds() / 60)
            if disconnect_minutes > 20:
                time_to_quit("{} child disconnected for too long".format(p.__class__.__name__))
            logger.warning("%s child has been disconnected for %d minutes",
                           p.__class__.__name__, disconnect_minutes)
        logger.debug("%s child is ok", p.__class__.__name__)


def processEvents(timeout):
    global stop_gracefully
    try:
        event = eventq.get(True, timeout)
        if isinstance(event, events.Base):
            # logger.debug("Process event for %s", type(event))
            processEvent(event)
        else:
            logger.warning("Ignoring unexpected event: %s", event)
    except (KeyboardInterrupt, SystemExit):
        logger.info("got KeyboardInterrupt")
        stop_gracefully = True
    except queue.Empty:
        pass

def stop_child_processes(timeout=5):
    for process in myProcesses:
        if process.pid is not None and process.is_alive():
            logger.info(
                "Terminating child process %s, pid=%s",
                process.__class__.__name__,
                process.pid,
            )
            process.terminate()

    for process in myProcesses:
        if process.pid is None:
            continue

        process.join(timeout)

        if process.is_alive():
            logger.error(
                "Child process %s, pid=%s did not terminate; killing it",
                process.__class__.__name__,
                process.pid,
            )

            if hasattr(process, "kill"):
                process.kill()
                process.join(timeout)

def main():
    global scheduler, should_check_children

    exit_status = 0

    job_defaults = {
        "coalesce": True,
        "max_instances": 1,
    }

    scheduler = BackgroundScheduler(job_defaults=job_defaults)

    try:
        scheduler.start()

        for process in myProcesses:
            process.start()

        logger.debug("Starting main event processing loop")
        _start_periodic_jobs()
        sdnotify.ready()

        while not stop_gracefully:
            processEvents(EVENTQ_GET_TIMEOUT)
            # Answering WatchdogSec=. This loop is the last thing that can
            # wedge without anyone noticing; systemd notices for us.
            sdnotify.watchdog()

            if should_check_children:
                check_child_processes()
                should_check_children = False

    except Exception:
        exit_status = 1
        logger.exception("Unexpected failure in main process")

    finally:
        sdnotify.stopping()

        if scheduler is not None:
            try:
                scheduler.shutdown(wait=False)
            except Exception:
                logger.exception("Failed to shut down scheduler")
                exit_status = 1

        stop_child_processes()

        if eventq is not None:
            try:
                eventq.close()
                eventq.cancel_join_thread()
            except Exception:
                logger.exception("Failed to close event queue")
                exit_status = 1

    return exit_status


# cfg_globals
stop_gracefully = False
logger = None
eventq = None
myProcesses = []
scheduler = None
should_check_children = False

if __name__ == "__main__":
    logger = log.getLogger()
    log.initLogger()

    if env.get('DEBUG_log_to_console') == "yes":
        log.log_to_console()
    if env.get('DEBUG_log_level_debug') == "yes":
        log.set_log_level_debug()

    logger.debug("adaio process started")
    eventq = multiprocessing.Queue(EVENTQ_SIZE)
    myProcesses.append(MqttclientProcess(eventq))
    myProcesses.append(MqttAdaIoProcess(eventq))
    myProcesses.append(MqttAdaIoThrottleProcess(eventq))
    myProcesses.append(OWeatherProcess(eventq))
    if senseenergy.use_sense_energy():
        myProcesses.append(SenseEnergyProcess(eventq))
    else:
        logger.info("Sense Energy process not needed")
    exit_status = main()

    if exit_status != 0:
        logger.error("main is exiting with status %d", exit_status)

    logging.shutdown()

    # Avoid multiprocessing finalizers preventing process termination.
    os._exit(exit_status)
