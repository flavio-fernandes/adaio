#!/usr/bin/env bash
#

[ $EUID -ne 0 ] && { echo 'must be root' >&2; exit 1; } ||:

[ -e "/vagrant/.secrets" ] && source /vagrant/.secrets

[ -n "$MQTT_LOCAL_BROKER_IP" ] &&
  [ "$MQTT_LOCAL_BROKER_IP" != "localhost" ] &&
  [ "$MQTT_LOCAL_BROKER_IP" != "127.0.0.1" ] &&
 { echo 'noop: using non-local $MQTT_LOCAL_BROKER_IP' >&2; exit 0; }

set -o xtrace
set -o errexit

sudo apt-get install -y mosquitto

cat <<EOT > /etc/mosquitto/conf.d/localbroker.conf
allow_anonymous true
bind_address 127.0.0.1
EOT

sudo systemctl enable --now mosquitto
sudo systemctl status --full --no-pager mosquitto

echo ok
