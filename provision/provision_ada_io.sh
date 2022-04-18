#!/usr/bin/env bash
#

[ $EUID -eq 0 ] && { echo 'must NOT be root' >&2; exit 1; } ||:

set -o xtrace
set -o errexit

deactivate ||:
rm -rf /vagrant/env
/vagrant/ada/bin/create-env.sh
echo '[ -e /vagrant/env/bin/activate ] && source /vagrant/env/bin/activate' >> ~/.bashrc

cd
ln -s /vagrant/scripts
ln -s /vagrant/ada/bin
ln -s /vagrant/ada/bin/tail_log.sh ~/
ln -s /vagrant/ada/bin/svc_ctl.sh ~/
ln -s /vagrant/evbays

sudo cp -v /vagrant/ada/bin/adaio.service.vagrant /lib/systemd/system/adaio.service
sudo systemctl enable --now adaio.service
sudo systemctl status --full --no-pager adaio

echo ok
