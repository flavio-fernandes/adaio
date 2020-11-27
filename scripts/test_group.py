#!/usr/bin/env python3

# ref: https://github.com/adafruit/Adafruit_IO_Python/blob/master/examples/mqtt/mqtt_groups_pubsub.py

import random
import sys
import time
# Import standard python modules.
from os import environ as env

# Import Adafruit IO MQTT client.
from Adafruit_IO import MQTTClient

# Set to your Adafruit IO key.
# Remember, your key is a secret,
# so make sure not to publish it when you publish this code!
ADAFRUIT_IO_KEY = env['IO_KEY']

# Set to your Adafruit IO username.
# (go to https://accounts.adafruit.com to find your username)
ADAFRUIT_IO_USERNAME = env['IO_USERNAME']

# Group Name
group_name = 'grouptest'

# Feeds within the group
group_feeds = ['one', 'two', 'three', 'four', 'five']

# Define callback functions which will be called when certain events happen.
def connected(client):
    # Connected function will be called when the client is connected to Adafruit IO.
    # This is a good place to subscribe to topic changes.  The client parameter
    # passed to this function is the Adafruit IO MQTT client so you can make
    # calls against it easily.
    print('Listening for changes on ', group_name)
    # Subscribe to changes on a group, `group_name`
    client.subscribe_group(group_name)

def disconnected(_client):
    # Disconnected function will be called when the client disconnects.
    print('Disconnected from Adafruit IO!')
    sys.exit(1)

def message(_client, topic_id, payload):
    # Message function will be called when a subscribed topic has a new value.
    # The topic_id parameter identifies the topic, and the payload parameter has
    # the new value.
    print('Topic {0} received new value: {1}'.format(topic_id, payload))

# Create an MQTT client instance.
client = MQTTClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY, secure=True)

# Setup the callback functions defined above.
client.on_connect    = connected
client.on_disconnect = disconnected
client.on_message    = message

# Connect to the Adafruit IO server.
client.connect()

client.loop_background()

print('Publishing new messages (press Ctrl-C to quit)...')
while True:
    for group_feed in group_feeds:
        value = random.randint(0, 100)
        print('Publishing {0} to {1}.{2}.'.format(value, group_name, group_feed))
        client.publish(group_feed, value, group_name)
        time.sleep(0.5)
    time.sleep(3)
