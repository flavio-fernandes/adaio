import json
import ssl
from datetime import datetime
from time import time

import requests
from requests.exceptions import ReadTimeout
from websocket import create_connection
from websocket._exceptions import WebSocketTimeoutException

API_URL = 'https://api.sense.com/apiservice/api/v1/'
WS_URL = "wss://clientrt.sense.com/monitors/%s/realtimefeed?access_token=%s"
API_TIMEOUT = 10
WSS_TIMEOUT = 10
RATE_LIMIT = 180

# for the last hour, day, week, month, or year
VALID_SCALES = ['HOUR', 'DAY', 'WEEK', 'MONTH', 'YEAR']


class SenseAPITimeoutException(Exception):
    pass


class SenseAuthenticationException(Exception):
    pass


class SenseApi(object):

    def __init__(self, username=None, password=None,
                 api_timeout=API_TIMEOUT, wss_timeout=WSS_TIMEOUT):

        # Timeout instance variables
        self.api_timeout = api_timeout
        self.wss_timeout = wss_timeout
        self.rate_limit = RATE_LIMIT

        self._realtime = {}
        self._devices = []
        self._trend_data = {}
        for scale in VALID_SCALES: self._trend_data[scale] = {}

        if username and password:
            self.authenticate(username, password)

    def set_auth_data(self, data):
        self.sense_access_token = data['access_token']
        self.sense_user_id = data['user_id']
        self.sense_monitor_id = data['monitors'][0]['id']

        # create the auth header
        self.headers = {'Authorization': 'bearer {}'.format(
            self.sense_access_token)}

    def _set_realtime(self, data):
        self._realtime = data
        self.last_realtime_call = time()

    def get_realtime(self):
        return self._realtime

    @property
    def active_devices(self):
        return [d['name'] for d in self._realtime.get('devices', {})]

    @property
    def devices(self):
        """Return devices."""
        return self._devices

    @property
    def active_power(self):
        return self._realtime.get('w', 0)

    @property
    def active_solar_power(self):
        return self._realtime.get('solar_w', 0)

    @property
    def active_voltage(self):
        return self._realtime.get('voltage', [])

    @property
    def active_frequency(self):
        return self._realtime.get('hz', 0)

    @property
    def daily_production(self):
        return self.get_trend('DAY', False)

    @property
    def daily_production(self):
        return self.get_trend('DAY', True)

    @property
    def weekly_production(self):
        return self.get_trend('WEEK', False)

    @property
    def weekly_production(self):
        return self.get_trend('WEEK', True)

    @property
    def monthly_production(self):
        return self.get_trend('MONTH', False)

    @property
    def monthly_production(self):
        return self.get_trend('MONTH', True)

    @property
    def yearly_consumption(self):
        return self.get_trend('YEAR', False)

    @property
    def yearly_production(self):
        return self.get_trend('YEAR', True)

    def _get_x_trend(self, key, scale):
        try:
            return self._trend_data[scale][key]["total"]
        except KeyError:
            pass
        return 0

    def get_consumption_trend(self, scale):
        return self._get_x_trend("consumption", scale)

    def get_production_trend(self, scale):
        return self._get_x_trend("production", scale)

    def get_trend(self, scale, is_production):
        key = "production" if is_production else "consumption"
        if key not in self._trend_data[scale]: return 0
        total = self._trend_data[scale][key].get('total', 0)
        if scale == 'WEEK' or scale == 'MONTH':
            return total + self.get_trend('DAY', is_production)
        if scale == 'YEAR':
            return total + self.get_trend('MONTH', is_production)
        return total

    def authenticate(self, username, password):
        auth_data = {
            "email": username,
            "password": password
        }

        # Create session
        self.s = requests.session()

        # Get auth token
        try:
            response = self.s.post(API_URL + 'authenticate',
                                   auth_data, timeout=self.api_timeout)
        except Exception as e:
            raise Exception('Connection failure: %s' % e)

        # check for 200 return
        if response.status_code != 200:
            raise SenseAuthenticationException(
                "Please check username and password. API Return Code: %s" %
                response.status_code)

        self.set_auth_data(response.json())

    # Update the realtime data
    def update_realtime(self):
        # rate limit API calls
        if self._realtime and self.rate_limit and \
                self.last_realtime_call + self.rate_limit > time():
            return self._realtime
        next(self.get_realtime_stream())

    def get_realtime_stream(self):
        """ Reads realtime data from websocket
            Continues until loop broken"""
        ws = None
        url = WS_URL % (self.sense_monitor_id, self.sense_access_token)
        try:
            ws = create_connection(url, timeout=self.wss_timeout,
                                   sslopt={"cert_reqs": ssl.CERT_NONE})
            while True:  # hello, features, [updates,] data
                result = json.loads(ws.recv())
                if result.get('type') == 'realtime_update':
                    data = result['payload']
                    self._set_realtime(data)
                    yield data
        except WebSocketTimeoutException:
            raise SenseAPITimeoutException("API websocket timed out")
        finally:
            if ws:
                ws.close()

    def get_trend_data(self, scale):
        if scale.upper() not in VALID_SCALES:
            raise Exception("%s not a valid scale" % scale)
        # epochtime = 30256871
        # t = datetime.fromtimestamp(epochtime)
        t = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        self._trend_data[scale] = self.api_call(
            'app/history/trends?monitor_id=%s&scale=%s&start=%s' %
            (self.sense_monitor_id, scale, t.isoformat()))

    def update_trend_data(self):
        for scale in VALID_SCALES:
            self.get_trend_data(scale)

    def api_call(self, url, payload={}):
        try:
            return self.s.get(API_URL + url,
                              headers=self.headers,
                              timeout=self.api_timeout,
                              data=payload).json()
        except ReadTimeout:
            raise SenseAPITimeoutException("API call timed out")

    def get_discovered_device_names(self):
        # lots more info in here to be parsed out
        json = self.api_call('app/monitors/%s/devices' %
                             self.sense_monitor_id)
        self._devices = [entry['name'] for entry in json]
        return self._devices

    def get_discovered_device_data(self):
        return self.api_call('monitors/%s/devices' %
                             self.sense_monitor_id)

    def always_on_info(self):
        # Always on info - pretty generic similar to the web page
        return self.api_call('app/monitors/%s/devices/always_on' %
                             self.sense_monitor_id)

    def get_monitor_info(self):
        # View info on your monitor & device detection status
        return self.api_call('app/monitors/%s/status' %
                             self.sense_monitor_id)

    def get_device_info(self, device_id):
        # Get specific informaton about a device
        return self.api_call('app/monitors/%s/devices/%s' %
                             (self.sense_monitor_id, device_id))

    def get_all_usage_data(self):
        payload = {'n_items': 30}
        # lots of info in here to be parsed out
        return self.api_call('users/%s/timeline' %
                             (self.sense_user_id), payload)
