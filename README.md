# adaio

Vagrant based VM to interact with Adafruit.io.

This repo offers an opinionated implementation of the bridging functionality
I use at home for interacting between [Adafruit.io](https://adafruit.io) and my internal MQTT broker.
With that, I can easily control what and how values from my local IoT devices populate the feeds at
Adafruit.io and vice-versa.
The auto-provisioning of the virtual machine used to run this code is also kept here.

## Adafruit.io secrets

Look at [secrets.txt.example](https://github.com/flavio-fernandes/adaio/blob/master/provision/secrets.txt.example).
Also, refer to [aio](https://io.adafruit.com/api/docs/) for details.
These are the attributes you will need after renaming this file to _secrets.txt_:

```bash
# Note: Commented out lines are optional
export ADAFRUIT_IO='https://io.adafruit.com'
export IO_USERNAME='username'
export IO_KEY='aio_xxxxxx'
#export IO_RANDOM_ID='4321'
#export OPENWEATHER_API='api_goes_here'
#export OPENWEATHER_CITY_ID='city_id_goes_here'
#export OPENWEATHER_INTERVAL='595'
```

## const.py

The [const.py](https://github.com/flavio-fernandes/adaio/blob/master/ada/const.py)
file is customized for my use. However, that is the main place where
tweaks will be needed for leveraging this repo for others.

Also check the _processMqttMsgEvent_ function in [main.py](https://github.com/flavio-fernandes/adaio/blob/a5f9f46d5ee3ebcf5fb4b6cde4eabcddb65eb7fa/ada/main.py#L110)
for additional changes you may [not] want in your deployment.

## Vagrant

The [Vagrantfile](https://github.com/flavio-fernandes/adaio/blob/master/Vagrantfile)
is complete enough to provision a virtual machine with the
systemd unit that automatically starts the [service](https://github.com/flavio-fernandes/adaio/blob/master/ada/bin/adaio.service.vagrant)
upon boot.

## TODO

- Expand this readme file.
- Make it less customized for flaviof's home.
