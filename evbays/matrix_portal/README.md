# evbays_matrix_portal

#### CircuitPython based project for Adafruit MatrixPortal

This directory contains the software used for controlling a
[Matrix Portal](https://www.adafruit.com/product/4745) to display
the availability of the EV chargers at my office.

There is a script that periodically [fetches the state](https://github.com/flavio-fernandes/adaio/blob/master/evbays/evbays.sh) of the chargers
and another component that takes that info and [populates the feeds](https://github.com/flavio-fernandes/adaio/commit/eefe6395bb445304c2b938f2978b69005df73226#r72635066)
to [Adafruit IO](https://io.adafruit.com/).
So, all the Matrix Portal needs to do is to read the feeds and display them.

To see a dashboard hosted by [Adafruit IO](https://io.adafruit.com/) with the state of this feed,
[see here](https://io.adafruit.com/flaviof/dashboards/ev-chargers?kiosk=true). 

Using the accelerometer of the Matrix Portal, the [position of the display is used](https://github.com/flavio-fernandes/adaio/blob/master/evbays/matrix_portal/code.py#L70-L83)
to force an update, start the flash probe animation,
or put the display in deep sleep ([heh, kinda](https://github.com/adafruit/Adafruit_CircuitPython_MatrixPortal/issues/84)).

The parts used as well as info on the 3d printed case are
[available here](https://www.thingiverse.com/thing:4680669):
[David Longley's Adafruit 64x32 RGB LED Matrix modular case](https://www.thingiverse.com/thing:4680669).
If you use this case, please make sure to thank David!

![EV Chargers Status](https://live.staticflickr.com/65535/52042553339_d18e117f20_c.jpg)

There are a few more 
[pictures of this project here]( https://www.flickr.com/gp/38447095@N00/361f58).

#### Adafruit Show and Tell

Adafruit offers guides along with products that make it easy to build the EVbays display.
JP and Liz hosted [Show and Tell](https://www.youtube.com/c/adafruit/videos) on May 4th, 2022 and
I had the honor of [showing the project](https://youtu.be/VTTvp8WajEI?t=1145) to them.

[![EVbays demo](https://img.youtube.com/vi/VTTvp8WajEI/3.jpg)](https://youtu.be/VTTvp8WajEI?t=1145)

### secrets.py

Make sure to create a file called secrets.py to include info on the wifi and Adafruit IO account.
Use [**secrets.py.sample**](https://github.com/flavio-fernandes/adaio/blob/master/evbays/matrix_portal/secrets.py.sample)
as reference.


### Removing _all_ files from CIRCUITPY drive

```
# NOTE: Do not do this before backing up all files!!!
>>> import storage ; storage.erase_filesystem()
```

### Copying files from cloned repo to CIRCUITPY drive
```
# First, get to the REPL prompt so the board will not auto-restart as
# you copy files into it. To do that, hit CONTROL+C from the Circuit Python serial console:

<CTRL-C>
Adafruit CircuitPython 7.2.5 on 2022-04-06; Adafruit Matrix Portal M4 with samd51j19
>>> 

# Then, from a shell terminal window, assuming that MatrixPortal
# is mounted under /Volumes/CIRCUITPY
$  cd ${THIS_REPO_DIR}/evbays/matrix_portal

$  [ -e ./code.py ] && \
   [ -d /Volumes/CIRCUITPY/ ] && \
   rm -rf /Volumes/CIRCUITPY/*.py && \
   (tar czf - *) | ( cd /Volumes/CIRCUITPY ; tar xzvf - ) && \
   echo ok || echo not_okay
```

### Libraries

Use [circup](https://learn.adafruit.com/keep-your-circuitpython-libraries-on-devices-up-to-date-with-circup)
to install these libraries into the Matrix Portal:

```text
$ python3 -m venv .env && source ./.env/bin/activate && \
  pip install --upgrade pip

$ pip3 install circup

$ for LIB in \
  adafruit_bitmap_font \
  adafruit_bus_device \
  adafruit_display_shapes \
  adafruit_display_text \
  adafruit_lis3dh \
  adafruit_progressbar \
  ; do circup install $LIB ; done
```

This is what it should look like:
```text
$ ls /Volumes/CIRCUITPY/
README.md		code.py			display_helpers.py	lib			secrets.py
boot_out.txt		consts.py		fonts			net_helpers.py		secrets.py.sample

$ ls /Volumes/CIRCUITPY/lib
adafruit_bitmap_font	adafruit_display_shapes	adafruit_lis3dh.mpy
adafruit_bus_device	adafruit_display_text	adafruit_progressbar

$ circup freeze
Found device at /Volumes/CIRCUITPY, running CircuitPython 7.2.5.
adafruit_lis3dh==5.1.13
adafruit_bitmap_font==1.5.6
adafruit_bus_device==5.1.8
adafruit_display_shapes==2.4.3
adafruit_display_text==2.22.3
adafruit_progressbar==2.3.3
```

At this point, all needed files should be in place, and all that
is needed is to let code.py run. From the Circuit Python serial console:

```text
>>  <CTRL-D>
soft reboot

Auto-reload is on. Simply save files over USB to run them or enter REPL to disable.
code.py output:
display init finished
...
```
