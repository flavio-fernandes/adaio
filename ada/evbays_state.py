#!/usr/bin/env python

import re
from datetime import datetime
from collections import namedtuple

CHANGED_BAY = namedtuple("CHANGED_BAY", "name status statuscode ts simpletime")


class Bay(object):
    def __init__(self, name, status=None):
        self.name = name.replace(" ", "-")
        self.status = status
        self.last_status_change = datetime.now()

    @property
    def status_code(self):
        CODES = {
            "Available": 0,
            "In use": 1,
            "Offline": 2,
            "Other": 3,
        }
        return CODES.get(self.status, 3)


class BayState(object):
    def __init__(self, evbays_process=None):
        self.evbays_process = evbays_process
        self.cache = {}

    def process(self, payload_dict):
        bays_tmp = {}
        changed_bays = []
        available_bays = 0
        aaData = payload_dict.get("aaData", {})
        stations = aaData.get("stations", [])

        for station in stations:
            name = station.get("name")
            status = station.get("status")
            if not name:
                continue
            if not status:
                continue

            bay = Bay(name, status)
            if bay.status_code == 0:
                available_bays += 1

            # Get a number out of the name. We do not care about number 0
            bay_index_str = ''.join(re.findall("[0-9]", name))
            if bay_index_str:
                bays_tmp[int(bay_index_str)] = str(bay.status_code)

            if bay.name in self.cache and self.cache[bay.name].status == status:
                continue

            self.cache[bay.name] = bay
            simple_time = bay.last_status_change.strftime("%I:%M %p").lower()
            is_expected_code = bay.status_code <= 1
            cb = CHANGED_BAY(
                bay.name,
                bay.status,
                bay.status_code,
                bay.last_status_change.isoformat(),
                simple_time if is_expected_code else bay.status,
            )
            changed_bays.append(cb)

        # Assemble a string with bays 1 to 6. "3" filled as pad.
        bays_str = ""
        for bay_index in range(1, 7):
            bays_str += bays_tmp.get(bay_index, "3")

        return bays_str, changed_bays, available_bays

    def clear_cache(self):
        self.cache = {}
        if self.evbays_process:
            self.evbays_process.do_fetch_now()
