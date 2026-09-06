#!/usr/bin/env python
"""Minimal sd_notify(3) client, so systemd can watchdog this service.

None of this needs the systemd python bindings: the protocol is a datagram
carrying newline separated assignments. When NOTIFY_SOCKET is absent -- running
by hand, or under a unit that grants no notify access -- every call is a no-op,
so the same code runs either way.
"""
import socket
from os import environ as env

from ada import log

_sock = None
_address = None
_unavailable = False


def _get_socket():
    global _sock, _address, _unavailable

    if _unavailable:
        return None, None
    if _sock is None:
        address = env.get('NOTIFY_SOCKET')
        if not address:
            _unavailable = True
            return None, None
        # A leading '@' names a socket in the abstract namespace.
        if address.startswith('@'):
            address = '\0' + address[1:]
        try:
            _sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        except Exception as e:
            logger.warning("no socket to notify systemd with: %s", e)
            _unavailable = True
            return None, None
        _address = address
    return _sock, _address


def notify(state):
    sock, address = _get_socket()
    if not sock:
        return False
    try:
        sock.sendto(state.encode('utf-8'), address)
    except Exception as e:
        logger.warning("failed to notify systemd of %s: %s", state, e)
        return False
    return True


def ready():
    return notify("READY=1")


# Answering the WatchdogSec= timer. A main loop that stops going around stops
# sending these, and systemd restarts the service instead of leaving it up and
# doing nothing.
def watchdog():
    return notify("WATCHDOG=1")


def stopping():
    return notify("STOPPING=1")


# =============================================================================


logger = log.getLogger()
