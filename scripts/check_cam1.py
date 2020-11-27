#!/usr/bin/env python3

# ref: https://raw.githubusercontent.com/flavio-fernandes/Adafruit_IO_Python/master/examples/mqtt/mqtt_client_class.py

# Example of using the MQTT client class to subscribe to and publish feed values.
# Author: Tony DiCola

# Import standard python modules.
from datetime import datetime
import random
import sys
import time
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

CAM='cam1'


# Define callback functions which will be called when certain events happen.
def connected(client):
    # Connected function will be called when the client is connected to Adafruit IO.
    # This is a good place to subscribe to feed changes.  The client parameter
    # passed to this function is the Adafruit IO MQTT client so you can make
    # calls against it easily.
    print('Connected to Adafruit IO!  Listening for {} changes...'.format(CAM))
    # Subscribe to changes on a feed named DemoFeed.
    client.subscribe(CAM)


def disconnected(client):
    # Disconnected function will be called when the client disconnects.
    print('Disconnected from Adafruit IO!')
    sys.exit(1)


def message(client, feed_id, payload):
    # Message function will be called when a subscribed feed has a new value.
    # The feed_id parameter identifies the feed, and the payload parameter has
    # the new value.
    print('Feed {0} received new value: {1}'.format(feed_id, payload))


# Create an MQTT client instance.
client = MQTTClient(ADAFRUIT_IO_USERNAME, ADAFRUIT_IO_KEY, secure=True)

# Setup the callback functions defined above.
client.on_connect    = connected
client.on_disconnect = disconnected
client.on_message    = message

# The last option is to just call loop_blocking.  This will run a message loop
# forever, so your program will not get past the loop_blocking call.  This is
# good for simple programs which only listen to events.  For more complex programs
# you probably need to have a background thread loop or explicit message loop like
# the two previous examples above.
#client.loop_blocking()

def main():
    # Connect to the Adafruit IO server.
    client.connect()

    last = 0
    print('Publishing a new message every 3600 seconds (press Ctrl-C to quit)...')
    while True:
       # Explicitly pump the message loop.
       client.loop()
       time.sleep(10)
       # Send a new message every 1 hour.
       if (time.time() - last) >= 3600.0:
           value = random.randint(0, 100)
           dateTime_obj = datetime.now()
           print('{} Publishing {} to cam1 feed.'.format(dateTime_obj, value))
           client.publish(CAM, value)
           last = time.time()

    
if __name__ == "__main__":
    main()
