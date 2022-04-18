#!/usr/bin/env python

from datetime import datetime
from collections import namedtuple

CHANGED_BAY = namedtuple("CHANGED_BAY", "name status ts simpletime")


def init(evbays_process):
    return BayState(evbays_process)


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
        changed_bays = []
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
            if bay.name in self.cache and self.cache[bay.name].status == status:
                continue

            self.cache[bay.name] = bay
            simple_time = bay.last_status_change.strftime("%I:%M %p").lower()
            is_expected_code = bay.status_code <= 1
            cb = CHANGED_BAY(
                bay.name,
                bay.status_code,
                bay.last_status_change.isoformat(),
                simple_time if is_expected_code else bay.status,
            )
            changed_bays.append(cb)

        return changed_bays

    def clear_cache(self):
        self.cache = {}
        if self.evbays_process:
            self.evbays_process.do_fetch_now()
