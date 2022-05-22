from alarm import time as alarm_time
from alarm import exit_and_deep_sleep_until_alarms
import board
import displayio
import rgbmatrix
import time
import gc
from collections import namedtuple
import display_helpers
from net_helpers import fetch
from consts import FETCH_INTERVAL, DEEP_SLEEP_SECS
import adafruit_lis3dh

no_change = 0
secs_since_fetch = 0
lis3dh = adafruit_lis3dh.LIS3DH_I2C(board.I2C(), address=0x19)
flat_coord = None


def run_once():
    global lis3dh

    displayio.release_displays()
    matrix = rgbmatrix.RGBMatrix(
        width=64,
        bit_depth=4,
        rgb_pins=[
            board.MTX_R1,
            board.MTX_G1,
            board.MTX_B1,
            board.MTX_R2,
            board.MTX_G2,
            board.MTX_B2,
        ],
        addr_pins=[board.MTX_ADDRA, board.MTX_ADDRB, board.MTX_ADDRC, board.MTX_ADDRD],
        clock_pin=board.MTX_CLK,
        latch_pin=board.MTX_LAT,
        output_enable_pin=board.MTX_OE,
    )
    display_helpers.init(matrix)
    lis3dh.range = adafruit_lis3dh.RANGE_2_G
    gc.collect()


def fast_tick():
    display_helpers.refresh_bay_available_animation()


def one_sec_tick():
    global secs_since_fetch
    global lis3dh
    global flat_coord

    display_helpers.draw_update_bar(secs_since_fetch, FETCH_INTERVAL)
    display_helpers.refresh_battery_levels()
    secs_since_fetch += 1

    x, y, z = [
        value / adafruit_lis3dh.STANDARD_GRAVITY for value in lis3dh.acceleration
    ]
    if not flat_coord:
        flat_coord = (x, y, z)
        print(f"Flat calibration: {x} {y} {z}")
        return

    x = int((x - flat_coord[0]) * 100)
    y = int((y - flat_coord[1]) * 100)
    z = int((z - flat_coord[2]) * 100)
    # print(f"ACC {x} {y} {z}")

    if x > 90 and y < -40 and z < -10:
        print(f"Sideways: grab values {x} {y} {z}")
        grab_values()
    if x < -40 and y < -90 and z < -10:
        print(f"Sideways: bay_available_ts {x} {y} {z}")
        display_helpers.bay_available_ts = time.monotonic()
    if x > 20 and y < -90 and z > 40:
        print(f"Sideways: sleep {x} {y} {z}")
        go_to_sleep()


def go_to_sleep():
    display_helpers.draw_a_blank()
    print("zzz")
    # https://github.com/adafruit/Adafruit_CircuitPython_MatrixPortal/issues/84
    time.sleep(DEEP_SLEEP_SECS)
    time_alarm = alarm_time.TimeAlarm(monotonic_time=time.monotonic() + 3)
    exit_and_deep_sleep_until_alarms(time_alarm)


def grab_values():
    global no_change
    global secs_since_fetch

    display_helpers.draw_update_bar(1, 1)
    last_values, values_changed = fetch()
    secs_since_fetch = 0

    display_helpers.set_top_text(last_values.get("text"))
    if (not values_changed) or (not last_values):
        no_change += 1
        print(f"No changes {no_change}. last_values: {last_values}")
        if no_change > 3:
            go_to_sleep()
        return

    no_change = 0
    for bay_number, value in enumerate(last_values.get("bays", []), start=1):
        if value == "0":
            display_helpers.group_add_available(bay_number)
        elif value == "1":
            display_helpers.group_add_in_use(bay_number)
        else:
            display_helpers.group_set_offline(bay_number)


run_once()

TS = namedtuple("TS", "interval fun")
TS_INTERVALS = {
    "fast_tick": TS(0.1, fast_tick),
    "1sec": TS(1, one_sec_tick),
    "grab_values": TS(FETCH_INTERVAL, grab_values),
}
tss = {interval: None for interval in TS_INTERVALS}
while True:
    now = time.monotonic()
    for ts_interval in TS_INTERVALS:
        if (
            not tss[ts_interval]
            or now > tss[ts_interval] + TS_INTERVALS[ts_interval].interval
        ):
            try:
                if TS_INTERVALS[ts_interval].interval >= 60:
                    lt = time.localtime()
                    print(
                        f"{lt.tm_hour}:{lt.tm_min}:{lt.tm_sec} Interval {ts_interval} triggered"
                    )
                else:
                    # print(".", end="")
                    pass
                TS_INTERVALS[ts_interval].fun()
            except (ValueError, RuntimeError) as e:
                print(f"Error in {ts_interval}, retrying in 22s: {e}")
                tss[ts_interval] = (
                    time.monotonic() - TS_INTERVALS[ts_interval].interval
                ) + 22
                continue
            except Exception as e:
                print(f"Failed {ts_interval}: {e}")
            tss[ts_interval] = time.monotonic()
