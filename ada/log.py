#!/usr/bin/env python
import logging
from logging.handlers import SysLogHandler
from os import path


def getLogger():
    return logging.getLogger('adaio')


def _log_handler_address(files=tuple()):
    try:
        return next(f for f in files if path.exists(f))
    except StopIteration:
        pass
    raise Exception("Invalid files: %s" % ", ".join(files))


def initLogger(testing=False):
    logger = getLogger()
    logger.setLevel(logging.INFO)
    log_format = '%(asctime)s [adaio] %(module)12s:%(lineno)-d %(levelname)-8s %(message)s'
    formatter = logging.Formatter(log_format)

    # Logs are normally configured here: /etc/rsyslog.d/*
    logHandlerAddress = _log_handler_address(
        ("/run/systemd/journal/syslog", "/var/run/syslog", "/dev/log"))
    syslog = SysLogHandler(address=logHandlerAddress,
                           facility=SysLogHandler.LOG_DAEMON)
    syslog.setFormatter(formatter)
    logger.addHandler(syslog)
    if testing:
        log_to_console()
        set_log_level_debug()


def log_to_console():
    consoleHandler = logging.StreamHandler()
    log_format = '%(asctime)s %(module)12s:%(lineno)-d %(levelname)-8s %(message)s'
    formatter = logging.Formatter(log_format)
    consoleHandler.setFormatter(formatter)
    getLogger().addHandler(consoleHandler)


def set_log_level_debug():
    getLogger().setLevel(logging.DEBUG)
