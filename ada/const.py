#!/usr/bin/env python

from collections import namedtuple

TOPIC_ENTRY = namedtuple("TOPIC_ENTRY", "local group_id feed_id")

AIO_HOME_TEMP = 'home-temperature'
AIO_HOME_HUMIDITY = 'home-humidity'
AIO_HOME_LIGHT = 'home-lux'
AIO_HOME_MOTION = 'home-motion'
AIO_HOME_ZONE = 'home-zone'
AIO_HOME_CONTACT = AIO_HOME_ZONE
AIO_HOME_ELECTRIC = 'electric-meters'
AIO_HOME_ELECTRIC_WATTS = 'electric-watts'
AIO_HOME_ELECTRIC_DEVICE = 'home-device'
AIO_HOME_EV_CHARGER = 'home-ev-charger'
AIO_MEMORY = 'device-free-memory'
AIO_UPTIME_MINUTES = 'device-uptime'
AIO_CPU = 'cpu-load'

# Dotted '<group>.<feed>' keys that must never be published to Adafruit IO.
AIO_FEED_DENYLIST = frozenset([
    'electric-watts.sensor-mystery-motor-1-power-watts',
])
# Maximum seconds to suppress an unchanged publish before sending a heartbeat.
AIO_PUBLISH_DEDUP_MAX_AGE_SECS = 1800
# Dotted '<group>.<feed>' keys that must publish every value even when unchanged.
AIO_FEED_DEDUP_EXEMPT = frozenset()

AIO_LOCAL_CMD = "/aio/local/cmd"
AIO_LOCAL_CMD_GET_LOCAL_TIME_WEATHER = "get_local_time_and_weather"

AIO_GROUPS = [AIO_HOME_TEMP, AIO_HOME_HUMIDITY, AIO_HOME_MOTION, AIO_HOME_ELECTRIC,
              AIO_HOME_ELECTRIC_DEVICE]

# topics triggered locally
LOCAL_ENTRIES = [
    TOPIC_ENTRY(AIO_LOCAL_CMD, AIO_LOCAL_CMD, "local-cmd"),

    TOPIC_ENTRY("/openweather/temp_min", AIO_HOME_TEMP, "minimum"),
    TOPIC_ENTRY("/openweather/temp_max", AIO_HOME_TEMP, "maximum"),

    TOPIC_ENTRY("/sensor/temperature_outside", AIO_HOME_TEMP, "outside"),
    TOPIC_ENTRY("/sensor/temperature_house", AIO_HOME_TEMP, "living-room"),
    TOPIC_ENTRY("/attic/temperature", AIO_HOME_TEMP, "attic"),
    TOPIC_ENTRY("/basement_window/temperature", AIO_HOME_TEMP, "basement"),
    TOPIC_ENTRY("/dining_room/temperature", AIO_HOME_TEMP, "dining-room"),
    TOPIC_ENTRY("/master_bedroom/temperature", AIO_HOME_TEMP, "master-bedroom"),
    TOPIC_ENTRY("/garage/temperature", AIO_HOME_TEMP, "garage"),
    TOPIC_ENTRY("/pyportalhallway/temperature", AIO_HOME_TEMP, "pyportal-hallway"),
    TOPIC_ENTRY("/pyportalkitchen/temperature", AIO_HOME_TEMP, "pyportal-kitchen"),
    TOPIC_ENTRY("zwave/shed/sensor_multilevel/endpoint_0/Air_temperature", AIO_HOME_TEMP, "shed"),

    TOPIC_ENTRY("/attic/humidity", AIO_HOME_HUMIDITY, "attic"),
    TOPIC_ENTRY("/basement_window/humidity", AIO_HOME_HUMIDITY, "basement"),
    TOPIC_ENTRY("/dining_room/humidity", AIO_HOME_HUMIDITY, "dining-room"),
    TOPIC_ENTRY("/master_bedroom/humidity", AIO_HOME_HUMIDITY, "master-bedroom"),
    TOPIC_ENTRY("/garage/humidity", AIO_HOME_HUMIDITY, "garage"),
    TOPIC_ENTRY("zwave/shed/sensor_multilevel/endpoint_0/Humidity", AIO_HOME_HUMIDITY, "shed"),

    TOPIC_ENTRY("/attic/light", AIO_HOME_LIGHT, "attic"),
    TOPIC_ENTRY("/garage/light", AIO_HOME_LIGHT, "garage"),
    ## duplicate of /officeclock/oper_state/light_sensor TOPIC_ENTRY("/officeClock/light", AIO_HOME_LIGHT, "office"),
    TOPIC_ENTRY("/officeclock/oper_state/light_sensor", AIO_HOME_LIGHT, "office"),
    TOPIC_ENTRY("/basement_window/light", AIO_HOME_LIGHT, "basement"),
    TOPIC_ENTRY("/pyportalhallway/light", AIO_HOME_LIGHT, "pyportal-hallway"),
    TOPIC_ENTRY("/pyportalkitchen/light", AIO_HOME_LIGHT, "pyportal-kitchen"),
    TOPIC_ENTRY("zwave/shed/sensor_multilevel/endpoint_0/Illuminance", AIO_HOME_LIGHT, "shed"),
    TOPIC_ENTRY("/bedclock/light", AIO_HOME_LIGHT, "bedclock"),

    TOPIC_ENTRY("/pyportalhallway/status", [AIO_UPTIME_MINUTES, AIO_MEMORY], "pyportal-hallway"),
    TOPIC_ENTRY("/pyportalkitchen/status", [AIO_UPTIME_MINUTES, AIO_MEMORY], "pyportal-kitchen"),
    TOPIC_ENTRY("/kitchen_clock/status", [AIO_UPTIME_MINUTES, AIO_MEMORY], "kitchen-clock"),
    TOPIC_ENTRY("/dining_room/oper_uptime_minutes", AIO_UPTIME_MINUTES, "dining-room"),
    TOPIC_ENTRY("/basement_window/oper_uptime_minutes", AIO_UPTIME_MINUTES, "basement"),
    TOPIC_ENTRY("/master_bedroom/oper_uptime_minutes", AIO_UPTIME_MINUTES, "master-bedroom"),
    TOPIC_ENTRY("/attic/oper_uptime_minutes", AIO_UPTIME_MINUTES, "attic"),
    TOPIC_ENTRY("/onoffpins/status", [AIO_UPTIME_MINUTES, AIO_MEMORY], "onoffpins-ring"),
    TOPIC_ENTRY("/bedclock/oper_uptime_minutes", AIO_UPTIME_MINUTES, "bedclock"),

    TOPIC_ENTRY("/buttonbox2/uptime", AIO_UPTIME_MINUTES, "trellis-office"),
    TOPIC_ENTRY("/buttonbox2/memory", AIO_MEMORY, "trellis-office"),
    TOPIC_ENTRY("/officeclock/oper_state/mem_available_kb", AIO_MEMORY, "oclock-available-kb"),
    TOPIC_ENTRY("/officeclock/oper_state/mem_free_kb", AIO_MEMORY, "oclock-free-kb"),
    TOPIC_ENTRY("/bedclock/oper_state/mem_available_kb", AIO_MEMORY, "bedclock-available-kb"),

    TOPIC_ENTRY("/officeclock/oper_state/cpu_load_1min", AIO_CPU, "oclock-load-1min"),
    TOPIC_ENTRY("/officeclock/oper_state/cpu_load_5min", AIO_CPU, "oclock-load-5min"),
    TOPIC_ENTRY("/officeclock/oper_state/cpu_load_15min", AIO_CPU, "oclock-load-15min"),

    TOPIC_ENTRY("/attic/motion", AIO_HOME_MOTION, "attic"),
    TOPIC_ENTRY("/garage/oper_flag/motion", AIO_HOME_MOTION, "garage"),
    TOPIC_ENTRY("/garage_steps/oper_flag/motion", AIO_HOME_MOTION, "garage"),
    TOPIC_ENTRY("/kitchen_steps/oper_flag/motion", AIO_HOME_MOTION, "garage"),
    TOPIC_ENTRY("/motionbox1/oper_flag/motion", AIO_HOME_MOTION, "basement"),
    TOPIC_ENTRY("/officeClock/motion", AIO_HOME_MOTION, "office"),
    TOPIC_ENTRY("/upstairs_office/motion", AIO_HOME_MOTION, "upstairs-office"),
    TOPIC_ENTRY("zwave/shed/notification/endpoint_0/Home_Security/Motion_sensor_status", AIO_HOME_MOTION, "shed"),

    TOPIC_ENTRY("/garage_door/zelda", AIO_HOME_ZONE, "garage-east"),
    TOPIC_ENTRY("/garage_door/zen", AIO_HOME_ZONE, "garage-west"),
    TOPIC_ENTRY("/ring/zone/#", AIO_HOME_ZONE, ""),
    TOPIC_ENTRY("/ring/motion/#", AIO_HOME_MOTION, ""),
    TOPIC_ENTRY("/ring/contact/#", AIO_HOME_CONTACT, ""),
    TOPIC_ENTRY("/zwave/waterpump/watts", AIO_HOME_ELECTRIC, "water-pump-power"),
    ## use /electric_meter/ TOPIC_ENTRY("/zwave/waterpump/kwh", AIO_HOME_ELECTRIC, "water-pump"),
    TOPIC_ENTRY("/zwave/minisplit/watts", AIO_HOME_ELECTRIC, "mini-split-power"),
    ## use /electric_meter/ TOPIC_ENTRY("/zwave/minisplit/kwh", AIO_HOME_ELECTRIC, "mini-split"),
    TOPIC_ENTRY("/zwave/dishwasher/watts", AIO_HOME_ELECTRIC, "dish-washer-power"),
    ## use /electric_meter/ TOPIC_ENTRY("/zwave/dishwasher/kwh", AIO_HOME_ELECTRIC, "dish-washer"),
    TOPIC_ENTRY("/zwave/furnace/watts", AIO_HOME_ELECTRIC, "furnace-power"),
    ## use /electric_meter/ TOPIC_ENTRY("/zwave/furnace/kwh", AIO_HOME_ELECTRIC, "furnace"),
    TOPIC_ENTRY("/powerwall/#", AIO_HOME_ELECTRIC, ""),
    TOPIC_ENTRY("/electric_meter/#", AIO_HOME_ELECTRIC, ""),
    TOPIC_ENTRY("/electric_watts/#", AIO_HOME_ELECTRIC_WATTS, ""),
    TOPIC_ENTRY("/sense/data/#", AIO_HOME_ELECTRIC, ""),
    TOPIC_ENTRY("/sense/device/#", AIO_HOME_ELECTRIC_DEVICE, ""),
    # Note: electric-meters.ev-charger == final session kwh is created 'for free' via /electric_meter/# above!
    TOPIC_ENTRY("/ev_charger/kwh", AIO_HOME_EV_CHARGER, "session-kwh"),
    TOPIC_ENTRY("/ev_charger/kw", AIO_HOME_EV_CHARGER, "session-kw"),
    TOPIC_ENTRY("/ev_charger/oper_flag/#", AIO_HOME_EV_CHARGER, ""),
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
    TOPIC_ENTRY(AIO_TOPIC_RANDOMIZER, "randomizer", "words"),
]

AIO_FEED_IDS = [entry.feed_id for entry in REMOTE_ENTRIES]
MQTT_REMOTE_MAP = {entry.feed_id: entry for entry in REMOTE_ENTRIES}

MQTT_CONNECTED = "connected"
MQTT_DISCONNECTED = "disconnected"

MQTT_CLIENT_AIO = "Adafruit_IO"
MQTT_CLIENT_AIO_THROTTLE = "Adafruit_IO_Throttle"
MQTT_CLIENT_LOCAL = "adaio_local"
