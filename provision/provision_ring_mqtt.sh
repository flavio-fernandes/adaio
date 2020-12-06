#!/usr/bin/env bash
#

[ $EUID -eq 0 ] && { echo 'must NOT be root' >&2; exit 1; } ||:

[ -e "/vagrant/.secrets" ] && source /vagrant/.secrets
[ -z "$RING_TOKEN" ] && { echo 'noop: ring_token not set' >&2; exit 0; }

set -o xtrace
set -o errexit

cd
sudo apt-get install -y git curl jq moreutils
curl -sL https://deb.nodesource.com/setup_14.x -o /tmp/nodesource_setup.sh
sudo bash -x /tmp/nodesource_setup.sh
sudo apt-get install -y nodejs
nodejs -v

RING_MQTT_REPO='flavio-fernandes'  ; # forked from tsightler
git clone https://github.com/${RING_MQTT_REPO}/ring-mqtt.git && cd ring-mqtt
chmod +x ring-mqtt.js
npm install
npm audit fix || npm audit || echo "BE AWARE OF NPM AUDIT"

# ref:  https://github.com/flavio-fernandes/ring-mqtt#authentication
# At this point, you must have a RING_TOKEN. If that is not the case, do
# npx -p ring-client-api ring-auth-cli

# ref: https://stackoverflow.com/questions/48878003/jq-edit-file-in-place-after-using-jq-select
cp -v ./config.json{,.orig}
[ -n "${MQTT_LOCAL_BROKER_IP}" ] && \
  jq ".host = \"${MQTT_LOCAL_BROKER_IP}\"" config.json | sponge config.json
# TODO (flaviof): there are more attributes one would likely want to set here
# https://github.com/flavio-fernandes/ring-mqtt/blob/1c825f02e86425cb5c4401c36ebdc78f63410690/config.json#L1-L14
jq ".ring_token = \"${RING_TOKEN}\"" config.json | sponge config.json

sudo cp -v /vagrant/ada/bin/ring-mqtt.service.vagrant /lib/systemd/system/ring-mqtt.service
sudo systemctl enable --now ring-mqtt.service
sudo systemctl status --full --no-pager ring-mqtt

echo ok
