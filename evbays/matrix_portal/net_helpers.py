import time
import board
import busio
from digitalio import DigitalInOut
from adafruit_esp32spi.adafruit_esp32spi import ESP_SPIcontrol
from adafruit_esp32spi.adafruit_esp32spi_wifimanager import ESPSPI_WiFiManager
import gc
import microcontroller
from secrets import secrets

wifi = None
last_values = {}


class IO_HTTP:
    __version__ = "0.0.0-auto.0"
    CLIENT_HEADERS = {
        "User-Agent": f"AIO-CircuitPython/{__version__}",
        "X-AIO-KEY": secrets["aio_key"],
    }

    @staticmethod
    def _handle_error(response):
        if response.status_code // 100 != 2:
            print(f"error {response.status_code}: {response.content}")
            raise RuntimeError

    @staticmethod
    def _compose_path(path):
        return "https://io.adafruit.com/api/v2/{0}/{1}".format(
            secrets["aio_username"], path
        )

    @staticmethod
    def _get(path):
        response = wifi.get(path, headers=IO_HTTP.CLIENT_HEADERS, timeout=60)
        IO_HTTP._handle_error(response)
        json_data = response.json()
        response.close()
        return json_data

    @staticmethod
    def receive_data(feed_key):
        path = IO_HTTP._compose_path("feeds/{0}/data/last".format(feed_key))
        return IO_HTTP._get(path)


def connect_wifi():
    global wifi

    if not wifi:
        esp32_cs = DigitalInOut(board.ESP_CS)
        esp32_ready = DigitalInOut(board.ESP_BUSY)
        esp32_reset = DigitalInOut(board.ESP_RESET)
        spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
        esp = ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
        wifi = ESPSPI_WiFiManager(esp, secrets, debug=False)

    try:
        wifi.connect()
    except Exception as e:
        print(f"FATAL! Unable to connect to WIFI: {e}")
        time.sleep(180)
        microcontroller.reset()

    print("IP ", wifi.esp.pretty_ip(wifi.esp.ip_address))
    print("Signal ", wifi.signal_strength())
    return wifi


def fetch():
    global last_values
    global wifi

    connect_wifi()

    last_update = f"{last_values.get('last-update')}"
    failed = False
    try:
        print("Collecting...")
        del last_values
        last_values = {}
        gc.collect()

        for name in (
            "text",
            "bays",
            "last-update",
        ):
            data = IO_HTTP.receive_data("ev." + name)
            last_values[name] = data.get("value", "")
            print(f"got:{name} mem_free:{gc.mem_free()}")
            del data
            time.sleep(1)
    except RuntimeError as e1:
        print(f"Retriable error {e1}")
        failed = True
    except Exception as e2:
        print(f"FATAL! Unable to get data: {e2}")
        time.sleep(120)
        microcontroller.reset()

    if failed:
        try:
            wifi.esp.reset()
            return {}, False
        except Exception as e3:
            print(f"FATAL! Unable to get data: {e3}")
            time.sleep(60)
            microcontroller.reset()

    values_changed = last_update != last_values.get("last-update")
    print(f"last_values: {last_values}")
    return last_values, values_changed
