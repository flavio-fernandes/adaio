import time

import vectorio
import rgbmatrix
from adafruit_progressbar.verticalprogressbar import VerticalProgressBar
from adafruit_progressbar.verticalprogressbar import VerticalFillDirection
import consts
from adafruit_display_text import bitmap_label as label
import displayio
from framebufferio import FramebufferDisplay
from adafruit_bitmap_font.bitmap_font import load_font
from adafruit_display_shapes.circle import Circle

# globals
font = load_font("fonts/6x10.bdf")
display = None
display_items = {}
main_group = displayio.Group()
update_bar_bitmap = None
update_bar_palette = displayio.Palette(2)
bg_color_palette = displayio.Palette(1)
active_items = set()
bay_in_use_ts = {}
bay_available_ts = None

AVAIL = "a"
IN_USE = "u"


def _init_main_group():
    global display_items
    global active_items
    global main_group

    for i in range(6):
        item_key = f"bay_{i + 1}"
        active_items.add(item_key)
        for elem in display_items[item_key]:
            main_group.append(elem)

    for elem in display_items["top_text"]:
        active_items.add("top_text")
        main_group.append(elem)

    elem = display_items["update_bar"][0]
    active_items.add("update_bar")
    main_group.append(elem)

    elem = display_items["bg"][0]
    active_items.add("bg")
    main_group.append(elem)


def _init_display_items():
    global font
    global display
    global display_items
    global update_bar_bitmap
    global update_bar_palette
    global bg_color_palette

    # update bar
    update_bar_bitmap = displayio.Bitmap(display.width, 1, 2)
    update_bar_bitmap.fill(0)
    update_bar_palette.make_transparent(0)
    update_bar_palette.make_opaque(1)
    update_bar_palette[1] = 0x171717
    update_bar_sprite = displayio.TileGrid(
        update_bar_bitmap, pixel_shader=update_bar_palette, x=0, y=0
    )
    display_items["update_bar"] = (update_bar_sprite,)

    # bg
    bg_color_bitmap = displayio.Bitmap(display.width, display.height, 1)
    bg_color_palette[0] = 0
    bg_color_palette.make_transparent(0)
    bg_sprite = displayio.TileGrid(
        bg_color_bitmap, pixel_shader=bg_color_palette, x=0, y=0
    )
    display_items["bg"] = (bg_sprite,)

    # top text
    top_text = label.Label(
        font,
        text=".x.x.x.x.",
        color=0xFF00FF,
        base_alignment=True,
        padding_top=0,
        padding_bottom=0,
        anchor_point=(0.5, 0.0),
        anchored_position=(display.width // 2, 0),
    )
    display_items["top_text"] = (top_text,)

    # bay numbers
    next_x = 2
    for i in range(6):
        bay_label = label.Label(
            font=font,
            text=f"{i + 1}",
            x=next_x,
            y=22,
            color=0xFFFFFF,
            base_alignment=True,
        )
        next_x += 11
        display_items[f"bay_{i + 1}"] = (bay_label,)

    # bay is available
    next_x = 4
    radius = 5
    for i in range(6):
        bay_free = Circle(next_x, 27, radius, fill=0x00FF00, outline=0)
        next_x += radius * 2 + 1
        display_items[f"bay_{i + 1}_{AVAIL}"] = (bay_free,)

    # bay in use
    battery_knob_palette = displayio.Palette(1)
    battery_knob_palette[0] = 0x0000FF
    battery_knob_points = [(0, 0), (5, 0), (5, 2), (0, 2)]
    width = 9
    height = 20
    y = 12
    next_x = 0
    for i in range(6):
        progress_bar = VerticalProgressBar(
            (next_x, y),
            (width, height),
            direction=VerticalFillDirection.BOTTOM_TO_TOP,
            bar_color=0x770000,
            outline_color=battery_knob_palette[0],
            fill_color=0,
            min_value=0,
            max_value=100,
        )
        battery_knob = vectorio.Polygon(
            pixel_shader=battery_knob_palette,
            points=battery_knob_points,
            x=next_x + 2,
            y=y - 2,
        )
        next_x += width + 2
        display_items[f"bay_{i + 1}_{IN_USE}"] = (progress_bar, battery_knob)


def init(matrix):
    global display

    display = FramebufferDisplay(matrix, auto_refresh=True)
    _init_display_items()
    _init_main_group()
    display.show(main_group)
    print("display init finished")


def draw_update_bar(curr_secs, max_secs):
    global update_bar_bitmap

    if curr_secs and max_secs:
        if curr_secs == max_secs:
            update_bar_bitmap.fill(1)
        else:
            x = min((curr_secs * display.width) // max_secs, display.width - 1)
            update_bar_bitmap[x, 0] = 1
    else:
        update_bar_bitmap.fill(0)


def set_top_text(msg):
    if msg and display_items["top_text"][0].text != msg:
        display_items["top_text"][0].text = msg


def bay_in_use_set_level(bay_number, value):
    item_key = f"bay_{bay_number}_{IN_USE}"
    # value only increases
    if display_items[item_key][0].value >= value:
        return
    # make it less chatty
    if display_items[item_key][0].value // 20 < value // 20:
        print(f"bay {bay_number} at {value}")
    display_items[item_key][0].value = int(value)


def refresh_bay_available_animation():
    global bay_available_ts
    global bg_color_palette

    if not bay_available_ts:
        return
    if time.monotonic() - bay_available_ts > consts.BAY_ANIM_TIMEOUT:
        bg_color_palette.make_transparent(0)
        del bay_available_ts
        bay_available_ts = None
        return
    if bg_color_palette.is_transparent(0):
        bg_color_palette.make_opaque(0)
    else:
        bg_color_palette.make_transparent(0)


def draw_a_blank():
    bg_color_palette[0] = 0
    bg_color_palette.make_opaque(0)


def refresh_battery_levels():
    for bay_number in bay_in_use_ts:
        secs_in_use = time.monotonic() - bay_in_use_ts[bay_number]
        batt_level = (secs_in_use * 100) // consts.SECS_TO_FULL
        batt_level = min(100, max(0, batt_level))
        bay_in_use_set_level(bay_number, int(batt_level))


def group_add_in_use(bay_number):
    global display_items
    global active_items
    global bay_in_use_ts
    global main_group

    item_key = f"bay_{bay_number}_{IN_USE}"
    if item_key in active_items:
        return False
    group_remove_available(bay_number)
    active_items.add(item_key)
    display_items[item_key][0].value = 0
    bay_in_use_ts[bay_number] = time.monotonic()
    for elem in display_items[item_key]:
        main_group.insert(0, elem)
    return True


def group_remove_in_use(bay_number):
    global display_items
    global active_items
    global main_group

    item_key = f"bay_{bay_number}_{IN_USE}"
    if item_key not in active_items:
        return False
    active_items.remove(item_key)
    del bay_in_use_ts[bay_number]
    for elem in display_items[item_key]:
        main_group.remove(elem)
    return True


def check_bay_notification(is_add):
    global bay_available_ts
    global bg_color_palette

    avail_bays = 0
    for item_key in active_items:
        if not item_key.startswith("bay_"):
            continue
        if item_key.endswith(f"_{AVAIL}"):
            avail_bays += 1

    # skip it if we just got started
    if not bg_color_palette[0]:
        bg_color_palette[0] = 0xFFFFFF
        return

    now = time.monotonic()
    if is_add and avail_bays == 1:
        bay_available_ts = now
        bg_color_palette[0] = 0x00FF00  # Bright Green
        print(f"{now} One bay became available")
    elif avail_bays == 0 and not is_add:
        bay_available_ts = now
        bg_color_palette[0] = 0xFF0000  # Bright Red
        print(f"{now} No bays available")


def group_add_available(bay_number):
    global display_items
    global active_items
    global main_group

    item_key = f"bay_{bay_number}_{AVAIL}"
    if item_key in active_items:
        return False
    group_remove_in_use(bay_number)
    active_items.add(item_key)
    for elem in display_items[item_key]:
        main_group.insert(0, elem)
    check_bay_notification(is_add=True)
    return True


def group_remove_available(bay_number):
    global display_items
    global active_items
    global main_group

    item_key = f"bay_{bay_number}_{AVAIL}"
    if item_key not in active_items:
        return False
    active_items.remove(item_key)
    for elem in display_items[item_key]:
        main_group.remove(elem)
    check_bay_notification(is_add=False)
    return True


def group_set_offline(bay_number):
    group_remove_in_use(bay_number)
    group_remove_available(bay_number)
