#!/usr/bin/env python
import json
import multiprocessing
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

EVENTQ_SIZE = 1000
EVENTQ_GET_TIMEOUT = 15  # seconds


class ProcessBase(multiprocessing.Process):
    def __init__(self, eventq_param):
        multiprocessing.Process.__init__(self)
        self.eventq = eventq_param

    def putEvent(self, event):
        try:
            self.eventq.put(event, False)
        except queue.Full:
            logger.error("Exiting: Queue is stuck, cannot add event: %s %s",
                         event.name, event.description)
            raise RuntimeError("Main process has a full event queue")


class MqttclientProcess(ProcessBase):
    def __init__(self, eventq_param):
        ProcessBase.__init__(self, eventq_param)
        mqttclient.do_init(self.putEvent)

    def run(self):
        logger.debug("mqttclient process started")
        while True:
            mqttclient.do_iterate()


class MqttAdaIoProcess(ProcessBase):
    def __init__(self, eventq_param):
        ProcessBase.__init__(self, eventq_param)
        mqttadaio.do_init(self.putEvent)

    def run(self):
        logger.debug("mqtt ada io process started")
        while True:
            mqttadaio.do_iterate()


class MqttAdaIoThrottleProcess(ProcessBase):
    def __init__(self, eventq_param):
        ProcessBase.__init__(self, eventq_param)
        mqttadaiothrottle.do_init(self.putEvent)

    def run(self):
        logger.debug("mqtt ada io throttle process started")
        while True:
            mqttadaiothrottle.do_iterate()


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


def _clear_aio_mqtt_attic():
    logger.debug("disabling aio attic event trigger now")
    mqttadaio.publish(const.AIO_HOME_MOTION_ATTIC.split('.')[-1], '0', const.AIO_HOME_MOTION)


def _fetch_attic_motion_value():
    mqttadaio.receive_feed_value(const.AIO_HOME_MOTION_ATTIC)


def _start_periodic_jobs():
    global scheduler

    # Ref: https://python.hotexamples.com/examples/apscheduler.schedulers.background/BackgroundScheduler/add_job/python-backgroundscheduler-add_job-method-examples.html
    # Add job to make it alive when there is no motion for a long time
    scheduler.add_job(_clear_aio_mqtt_attic, 'cron', day_of_week="wed,sun",
                      hour='13', minute=23, second=45,
                      id='periodic_clear_aio_mqtt_attic',
                      replace_existing=True)
    # Add catch all clearing motion. Just in case... :)
    scheduler.add_job(_fetch_attic_motion_value, 'interval', minutes=33,
                      id='periodic_fetch_attic_motion_value',
                      max_instances=1, next_run_time=datetime.now() + timedelta(minutes=22))


# TODO(flaviof): this needs to be more generic
def processMqttMsgEvent(client_id, topic, payload):
    global scheduler

    logger.debug("processMqttMsgEvent %s %s %s", client_id, topic, payload)
    if client_id == const.MQTT_CLIENT_LOCAL:
        payload_handlers = {
            const.AIO_HOME_SOLAR_RATE: handle_solar_rate,
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
        translate_payload = {"1": "on", "0": "off"}
        payload2 = translate_payload.get(str(payload), payload)
        mqttclient.do_mqtt_publish(topic_entry.local, payload2)


def processMqttConnEvent(client_id, event, rc):
    logger.debug("processMqttConnEvent client_id: %s event: %s rc: %s", client_id, event, rc)


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


def processEvent(event):
    # Based on the event, call a lambda to make mqtt and smartswitch in sync
    syncFunHandlers = {"mqtt": processEventMqttClient, }
    cmdFun = syncFunHandlers.get(event.group)
    if not cmdFun:
        logger.warning("Don't know how to process event %s: %s", event.name, event.description)
        return
    cmdFun(event)


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
        # make sure children are still running
        for p in myProcesses:
            if p.is_alive():
                continue
            logger.error("%s child died", p.__class__.__name__)
            logger.info("exiting so systemd can restart")
            raise RuntimeError("Child process terminated unexpectedly")


def main():
    global scheduler
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
    main()
    if not stop_gracefully:
        raise RuntimeError("main is exiting")
