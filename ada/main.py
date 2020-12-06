#!/usr/bin/env python
import json
import multiprocessing
import subprocess
import time
from datetime import datetime, timedelta
from os import environ as env

from apscheduler.schedulers.background import BackgroundScheduler
from six.moves import queue

from ada import const
from ada import events
from ada import log
from ada import mqttclient
from ada import mqttadaio
from ada import mqttadaiothrottle
from ada import oweather

EVENTQ_SIZE = 1000
EVENTQ_GET_TIMEOUT = 15  # seconds


class ProcessBase(multiprocessing.Process):
    def __init__(self, client_id_param, eventq_param):
        multiprocessing.Process.__init__(self)
        self.client_id = client_id_param
        self.eventq = eventq_param
        self.cmdq = None
        self.disconnect_ts = None

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
    def __init__(self, eventq_param):
        ProcessBase.__init__(self, const.MQTT_CLIENT_LOCAL, eventq_param)
        self.cmdq = mqttclient.do_init(self.putEvent)

    def run(self):
        logger.debug("mqttclient process started")
        while True:
            mqttclient.do_iterate()


class MqttAdaIoProcess(ProcessBase):
    def __init__(self, eventq_param):
        ProcessBase.__init__(self, const.MQTT_CLIENT_AIO, eventq_param)
        self.cmdq = mqttadaio.do_init(self.putEvent)

    def run(self):
        logger.debug("mqtt ada io process started")
        while True:
            mqttadaio.do_iterate()


class MqttAdaIoThrottleProcess(ProcessBase):
    def __init__(self, eventq_param):
        ProcessBase.__init__(self, const.MQTT_CLIENT_AIO_THROTTLE, eventq_param)
        self.cmdq = mqttadaiothrottle.do_init(self.putEvent)

    def run(self):
        logger.debug("mqtt ada io throttle process started")
        while True:
            mqttadaiothrottle.do_iterate()


class OWeatherProcess(ProcessBase):
    def __init__(self, eventq_param):
        ProcessBase.__init__(self, None, eventq_param)
        self.cmdq = oweather.do_init(self.putEvent)

    def run(self):
        logger.debug("openweather process started")
        while True:
            oweather.do_iterate()


def handle_solar_rate(feed_id, payload):
    rate_scale = 10000
    trim_prefix = "home-"
    rate_dict = None
    if feed_id.startswith(trim_prefix):
        feed_id = feed_id[len(trim_prefix):]
    try:
        rate_dict = json.loads(payload)
        payload2 = (rate_dict['delta_decawatt_hour'] * rate_scale) / rate_dict['delta_seconds']
    except Exception as e:
        logger.warning("solar_rate calculation failed %s %s %s : %s",
                       feed_id, payload, rate_dict, e)
        return feed_id, 0
    return feed_id, payload2


def handle_aio_cmd(_feed_id, payload):
    if payload == const.AIO_CMD_RESTART:
        logger.debug("Got request to restart ring-mqtt process")
        try:
            subprocess.call(['/vagrant/ada/bin/svc_restart_ring-mqtt.sh'], shell=True, timeout=10)
        except Exception as e:
            logger.error("svc_restart_ring-mqtt.sh failed: %s", e)
    # Return none so there is not a publish to aio from this
    return None, None


def _attic_cam_keep_alive():
    logger.debug("aio attic-camera keep alive")
    mqttadaio.publish(const.AIO_HOME_MOTION_ATTIC_CAM.split('.')[-1],
                      'ka', const.AIO_HOME_MOTION)


def _clear_aio_mqtt_attic():
    logger.debug("disabling aio attic event trigger now")
    mqttadaio.publish(const.AIO_HOME_MOTION_ATTIC.split('.')[-1], '0', const.AIO_HOME_MOTION)


def _fetch_attic_motion_value():
    mqttadaio.receive_feed_value(const.AIO_HOME_MOTION_ATTIC)


def _set_should_check_children():
    global should_check_children
    should_check_children = True


def _start_periodic_jobs():
    global scheduler

    # Ref: https://python.hotexamples.com/examples/apscheduler.schedulers.background/BackgroundScheduler/add_job/python-backgroundscheduler-add_job-method-examples.html
    # Add jobs to make it alive when there is no motion for a long time
    scheduler.add_job(_clear_aio_mqtt_attic, 'cron', day_of_week="wed,sun",
                      hour='13', minute=23, second=45,
                      id='periodic_clear_aio_mqtt_attic',
                      replace_existing=True)
    scheduler.add_job(_attic_cam_keep_alive, 'cron', day_of_week="mon,thu",
                      hour='13', minute=23, second=45,
                      id='periodic_attic_cam_keep_alive',
                      replace_existing=True)
    # Add catch all clearing motion. Just in case... :)
    scheduler.add_job(_fetch_attic_motion_value, 'interval', minutes=33,
                      id='periodic_fetch_attic_motion_value',
                      max_instances=1, next_run_time=datetime.now() + timedelta(minutes=22))
    scheduler.add_job(_set_should_check_children, 'interval', seconds=66,
                      id='periodic_set_should_check_children',
                      max_instances=1)


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
            const.AIO_HOME_SOLAR_RATE: handle_solar_rate,
            const.AIO_CMD: handle_aio_cmd,
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
            if topic_entry.group_id in payload_handlers:
                feed_id, payload = payload_handlers[topic_entry.group_id](feed_id, payload)
            if feed_id and payload:
                mqttadaio.publish(feed_id, payload, topic_entry.group_id)
    elif client_id == const.MQTT_CLIENT_AIO_THROTTLE:
        logger.warning("getting hot: %s %s", topic, payload)
        time.sleep(5)
    elif client_id == const.MQTT_CLIENT_AIO:
        # rename variables to (try to) make it less confusing
        feed_id, topic = topic, None
        if feed_id == const.AIO_HOME_MOTION_ATTIC:
            logger.debug("got attic event trigger: %s %s", feed_id, payload)
            # Adafruit.io does not trigger a '0', so we will make it happen here, after 10 seconds
            if payload == '1':
                scheduler.add_job(_clear_aio_mqtt_attic, 'date',
                                  run_date=datetime.now() + timedelta(seconds=10),
                                  id='clear_aio_mqtt_attic',
                                  replace_existing=True)
                # After clearing, do another check up to ensure that the motion did get
                # cleared. This is needed to handle cases where multiple motions happen
                # back to back.
                scheduler.add_job(_fetch_attic_motion_value, 'date',
                                  run_date=datetime.now() + timedelta(seconds=15),
                                  id='verify_attic_motion_value',
                                  replace_existing=True)
        topic_entry = const.MQTT_REMOTE_MAP.get(feed_id)
        if not topic_entry:
            return
        if topic_entry.local == const.AIO_TOPIC_WEATHER_CURRENT:
            logger.debug("got aio weather: %s", payload)
            try:
                payload_dict = json.loads(payload)
                precipProbability = payload_dict.get('precipProbability', 0)
                # https://stackoverflow.com/questions/10772066/escaping-special-character-in-a-url
                # https://www.url-encode-decode.com/
                payload_dict['precipProbabilityPercent'] = "{}+%25".format(
                    int(precipProbability * 100))
                payload2 = json.dumps(payload_dict)
            except ValueError as e:
                logger.warning("unable to parse json aio weather %s", e)
                payload2 = payload
        else:
            translate_payload = {"1": "on", "0": "off"}
            payload2 = translate_payload.get(str(payload), payload)
        mqttclient.do_mqtt_publish(topic_entry.local, payload2)


def processMqttConnEvent(client_id, event, rc):
    logger.debug("processMqttConnEvent client_id: %s event: %s rc: %s", client_id, event, rc)
    if client_id == const.MQTT_CLIENT_AIO:
        mqttclient.do_mqtt_publish(const.AIO_TOPIC_CONNECTION,
                                   {const.MQTT_CONNECTED: "true"}.get(event, "false"))
        if event == const.MQTT_CONNECTED:
            _attic_cam_keep_alive()
    elif client_id == const.MQTT_CLIENT_LOCAL:
        oweather.do_fetch()

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


def processOWeatherEvent(event):
    if event.name != "OpenWeatherEvent":
        logger.warning("Don't know how to process event %s: %s", event.name, event.description)
        return
    payload = event.params[0]
    logger.info("processOWeatherEvent: {}".format(payload))
    data_sys = payload.get('sys', {})
    oweather_topics = {}
    sunrise_raw = data_sys.get('sunrise')
    # ref: https://stackoverflow.com/questions/12400256/converting-epoch-time-into-the-datetime
    #      https://strftime.org/
    # time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(sunrise_raw))
    if sunrise_raw:
        oweather_topics['sunrise'] = time.strftime('%-H:%M', time.localtime(sunrise_raw))
    sunset_raw = data_sys.get('sunset')
    if sunset_raw:
        oweather_topics['sunset'] = time.strftime('%-H:%M', time.localtime(sunset_raw))
    for topic, mqtt_payload in oweather_topics.items():
        mqttclient.do_mqtt_publish('/openweather/{}'.format(topic), mqtt_payload)


def processEvent(event):
    # Based on the event, call a lambda to make mqtt and smartswitch in sync
    syncFunHandlers = {"mqtt": processEventMqttClient,
                       "open_weather": processOWeatherEvent}
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


def main():
    global scheduler, should_check_children
    # ref: https://python.hotexamples.com/examples/apscheduler.schedulers.background/BackgroundScheduler/add_job/python-backgroundscheduler-add_job-method-examples.html
    job_defaults = {
        'coalesce': True,
        'max_instances': 1
    }
    scheduler = BackgroundScheduler(job_defaults=job_defaults)
    scheduler.start()
    try:
        # Start our processes
        [p.start() for p in myProcesses]
        logger.debug("Starting main event processing loop")
        _start_periodic_jobs()
        while not stop_gracefully:
            processEvents(EVENTQ_GET_TIMEOUT)
            if should_check_children:
                check_child_processes()
                should_check_children = False
    except Exception as e:
        logger.error("Unexpected event: %s", e)
    scheduler.shutdown(wait=False)
    # make sure all children are terminated
    [p.terminate() for p in myProcesses]


# cfg_globals
stop_gracefully = False
logger = None
eventq = None
myProcesses = []
scheduler = None
should_check_children = False

if __name__ == "__main__":
    # global logger, eventq, myProcesses

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
    main()
    if not stop_gracefully:
        raise RuntimeError("main is exiting")
