#!/usr/bin/env bash
#

[ $EUID -eq 0 ] && { echo 'must NOT be root' >&2; exit 1; } ||:

#set -o xtrace
set -o errexit

# Create a file called provision/secrets.txt Use "secrets.txt.example" as a reference.
[ -e /vagrant/.secrets ] || cp -v /vagrant/provision/secrets.txt /vagrant/.secrets
grep --quiet '/vagrant/.secrets' ~/.bashrc || {
  echo '[ -e "/vagrant/.secrets" ] && source /vagrant/.secrets' >> ${HOME}/.bashrc
}

cp -v /vagrant/provision/dot.knobs /vagrant/.knobs
cp -v /vagrant/provision/dot.gitconfig ~/.gitconfig
cp -v /vagrant/provision/dot.emacs ~/.emacs

# TODO(flaviof): this needs to be more generic
wget --quiet -O - https://github.com/flavio-fernandes.keys >> ~/.ssh/authorized_keys
