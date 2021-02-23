#!/usr/bin/env python

from collections import namedtuple

TOPIC_ENTRY = namedtuple("TOPIC_ENTRY", "local group_id feed_id")

AIO_HOME_TEMP = 'home-temperature'
AIO_HOME_HUMIDITY = 'home-humidity'
AIO_HOME_LIGHT = 'home-lux'
AIO_HOME_MOTION = 'home-motion'
AIO_HOME_ZONE = 'home-zone'
AIO_HOME_CONTACT = AIO_HOME_ZONE
AIO_HOME_MOTION_ATTIC = '{}.attic'.format(AIO_HOME_MOTION)
AIO_HOME_MOTION_ATTIC_CAM = '{}.attic-camera'.format(AIO_HOME_MOTION)
AIO_HOME_ELECTRIC = 'electric-meters'
AIO_HOME_ELECTRIC_BASELINE = 'baseline-electric'
AIO_HOME_ELECTRIC_DEVICE = 'home-device'
AIO_HOME_SOLAR_RATE = 'solar-rate'

AIO_CMD = "/aio/ring/cmd"
AIO_CMD_RESTART = "restart"

AIO_GROUPS = [AIO_HOME_TEMP, AIO_HOME_HUMIDITY, AIO_HOME_MOTION, AIO_HOME_ELECTRIC,
              AIO_HOME_ELECTRIC_BASELINE, AIO_HOME_ELECTRIC_DEVICE]

# topics triggered locally
LOCAL_ENTRIES = [
    TOPIC_ENTRY(AIO_CMD, AIO_CMD, "ring-mqtt-cmd"),

    TOPIC_ENTRY("/sensor/temperature_outside", AIO_HOME_TEMP, "outside"),
    TOPIC_ENTRY("/sensor/temperature_house", AIO_HOME_TEMP, "living-room"),
    TOPIC_ENTRY("/attic/temperature", AIO_HOME_TEMP, "attic"),
    TOPIC_ENTRY("/basement_window/temperature", AIO_HOME_TEMP, "basement"),
    TOPIC_ENTRY("/master_bedroom/temperature", AIO_HOME_TEMP, "master-bedroom"),
    TOPIC_ENTRY("/garage/temperature", AIO_HOME_TEMP, "garage"),
    TOPIC_ENTRY("/pyportalhallway/temperature", AIO_HOME_TEMP, "pyportal-hallway"),
    TOPIC_ENTRY("/pyportalkitchen/temperature", AIO_HOME_TEMP, "pyportal-kitchen"),

    TOPIC_ENTRY("/attic/humidity", AIO_HOME_HUMIDITY, "attic"),
    TOPIC_ENTRY("/basement_window/humidity", AIO_HOME_HUMIDITY, "basement"),
    TOPIC_ENTRY("/master_bedroom/humidity", AIO_HOME_HUMIDITY, "master-bedroom"),
    TOPIC_ENTRY("/garage/humidity", AIO_HOME_HUMIDITY, "garage"),

    TOPIC_ENTRY("/attic/light", AIO_HOME_LIGHT, "attic"),
    TOPIC_ENTRY("/garage/light", AIO_HOME_LIGHT, "garage"),
    TOPIC_ENTRY("/officeClock/light", AIO_HOME_LIGHT, "office"),
    TOPIC_ENTRY("/basement_window/light", AIO_HOME_LIGHT, "basement"),
    TOPIC_ENTRY("/pyportalhallway/light", AIO_HOME_LIGHT, "pyportal-hallway"),
    TOPIC_ENTRY("/pyportalkitchen/light", AIO_HOME_LIGHT, "pyportal-kitchen"),

    # Note: attic motions are local, but treated as remote entries
    #       so they are not to be part of this block
    TOPIC_ENTRY("/garage/oper_flag/motion", AIO_HOME_MOTION, "garage"),
    TOPIC_ENTRY("/garage_steps/oper_flag/motion", AIO_HOME_MOTION, "garage"),
    TOPIC_ENTRY("/kitchen_steps/oper_flag/motion", AIO_HOME_MOTION, "garage"),
    TOPIC_ENTRY("/motionbox1/oper_flag/motion", AIO_HOME_MOTION, "basement"),
    TOPIC_ENTRY("/officeClock/motion", AIO_HOME_MOTION, "office"),

    TOPIC_ENTRY("/ring/motion/#", AIO_HOME_MOTION, ""),
    TOPIC_ENTRY("/ring/zone/#", AIO_HOME_ZONE, ""),
    TOPIC_ENTRY("/ring/contact/#", AIO_HOME_CONTACT, ""),
    TOPIC_ENTRY("/electric_meter/#", AIO_HOME_ELECTRIC, ""),
    TOPIC_ENTRY("/electric_meter_baseline/#", AIO_HOME_ELECTRIC_BASELINE, ""),
    TOPIC_ENTRY("/sense/data/#", AIO_HOME_ELECTRIC, ""),
    TOPIC_ENTRY("/sense/device/#", AIO_HOME_ELECTRIC_DEVICE, ""),

    TOPIC_ENTRY("/solar_rate/#", AIO_HOME_SOLAR_RATE, ""),
]

MQTT_LOCAL_TOPICS = [entry.local for entry in LOCAL_ENTRIES]
MQTT_LOCAL_MAP = {entry.local: entry for entry in LOCAL_ENTRIES}

AIO_TOPIC_PREFIX = "/aio"
AIO_TOPIC_CONNECTION = "{}/connected".format(AIO_TOPIC_PREFIX)
AIO_TOPIC_RANDOMIZER = "{}/words".format(AIO_TOPIC_PREFIX)
AIO_TOPIC_WEATHER_CURRENT = "{}/weather/current".format(AIO_TOPIC_PREFIX)
AIO_TOPIC_LOCAL_TIME = "{}/local_time".format(AIO_TOPIC_PREFIX)

# topics triggered from adafruit.io
REMOTE_ENTRIES = [
    # not really an aio triggered event, but goes to aio and comes back to be handled
    TOPIC_ENTRY("/attic/motion", AIO_HOME_MOTION, AIO_HOME_MOTION_ATTIC),

    TOPIC_ENTRY(AIO_TOPIC_RANDOMIZER, "randomizer", "words"),
    TOPIC_ENTRY(AIO_TOPIC_WEATHER_CURRENT, "weather", "current"),
]

AIO_FEED_IDS = [entry.feed_id for entry in REMOTE_ENTRIES]
MQTT_REMOTE_MAP = {entry.feed_id: entry for entry in REMOTE_ENTRIES}

MQTT_CONNECTED = "connected"
MQTT_DISCONNECTED = "disconnected"

MQTT_CLIENT_AIO = "Adafruit_IO"
MQTT_CLIENT_AIO_THROTTLE = "Adafruit_IO_Throttle"
MQTT_CLIENT_LOCAL = "adaio_local"
