#!/usr/bin/env bash
#

[ $EUID -eq 0 ] && { echo 'must NOT be root' >&2; exit 1; } ||:

[ -e "/vagrant/.secrets" ] && source /vagrant/.secrets
[ -z "$SEMA_LOGIN" ] && { echo 'noop: SEMA_LOGIN not set' >&2; exit 0; }

set -o xtrace
set -o errexit

cd
sudo apt-get install -y curl jq

sudo cp -v /vagrant/evbays/evbays.timer.vagrant /lib/systemd/system/evbays.timer
sudo cp -v /vagrant/evbays/evbays.service.vagrant /lib/systemd/system/evbays.service
sudo systemctl daemon-reload
sudo systemctl enable evbays.service
sudo systemctl enable --now evbays.timer
sudo systemctl status --full --no-pager evbays ||:
sudo systemctl status --full --no-pager evbays.timer ||:
sudo systemctl list-timers --all --no-pager ||:

echo ok
