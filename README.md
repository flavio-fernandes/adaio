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

### Adafruit IO publish filtering

`const.py` also holds the publish-volume controls for values sent to Adafruit IO.
`AIO_FEED_DENYLIST` is a `frozenset` of feed keys that are never published.
Use dotted feed keys: `<group>.<feed>` for grouped feeds, or just `<feed>` when
there is no group. Group underscores are normalized to dashes, matching the
Adafruit IO feed naming used elsewhere in this repo.

`AIO_PUBLISH_DEDUP_MAX_AGE_SECS` controls unchanged-value suppression. When a
feed has already been published with the same value, another identical value is
skipped until this age is reached. The state is in-memory and per process, so a
restart forgets prior publishes and sends fresh values again. The default 3600
seconds gives a one-hour heartbeat guarantee: a live feed with an unchanged
value is still republished at least once an hour. Feeds listed in
`AIO_FEED_DEDUP_EXEMPT` bypass unchanged-value suppression and publish every
value.

### Feed creation

Adafruit IO creates a feed on the fly when a publish names a key it does not know,
and that auto-create is not atomic: two publishes for a brand new key arriving in
the same instant leave two feeds sharing one key, splitting the history in half.
That is easy to hit, since the publish rate limiter batches values while it sleeps.

To avoid it, the first publish for a feed key creates the feed (and its group, when
needed) over the rest api first. The set of existing keys is fetched once per
process, and a key that already exists costs nothing. A publish still goes out even
when the rest call fails, since losing a value is worse than the rare race.

Use [bin/aio-feeds](https://github.com/flavio-fernandes/adaio/blob/master/bin/aio-feeds)
to audit this: `--duplicates` lists feed keys that ended up with more than one feed,
`--missing` lists feed keys in `const.py` that do not exist on Adafruit IO yet, and
`--delete-id <id> --yes` removes one feed by id, which is the only way to act on a
duplicated key.

## Vagrant

The [Vagrantfile](https://github.com/flavio-fernandes/adaio/blob/master/Vagrantfile)
is complete enough to provision a virtual machine with the
systemd unit that automatically starts the [service](https://github.com/flavio-fernandes/adaio/blob/master/ada/bin/adaio.service.vagrant)
upon boot.

## TODO

- Expand this readme file.
- Make it less customized for flaviof's home.
