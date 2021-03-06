#!/usr/bin/env bash

if [ -z "$1" ]; then
    sudo journalctl -u adaio.service -u ring-mqtt.service --no-pager --since now --follow
else
    sudo tail -F /var/log/syslog | grep -e adaio -e ring-mqtt
fi
