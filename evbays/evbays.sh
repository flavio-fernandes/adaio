#!/usr/bin/env bash
set -o errexit
set -o xtrace

[ $EUID -eq 0 ] && { echo 'must NOT be root' >&2; exit 1; } ||:

cd "$(dirname $0)"
[ -e "/vagrant/.secrets" ] && source /vagrant/.secrets ||:
[ -e "/vagrant/.knobs" ] && source /vagrant/.knobs ||:

# SEMA_LOGIN should look like this
# uname=foo@example.com&upass=superSecretHashGoesHere&type=WEB
[ -n "${SEMA_LOGIN}" ] || { echo 'bad SEMA_LOGIN' >&2; exit 2; }

# SEMA_LOCATION should look like this
# action=mapLocationDetails&div_id=999
[ -n "${SEMA_LOCATION}" ] || { echo 'bad SEMA_LOCATION' >&2; exit 3; }

remove_sema_cookie_jar="yes"
TMPFILE=$(mktemp -p /tmp -t sema.json.XXXXXXX)
function finish {
  rm -f "${TMPFILE}"
  [ "yes_CJAR" == "${remove_sema_cookie_jar}_CJAR" ] && { echo 'NOTE: removing login cookie file' >&2; rm -rf /vagrant/evbays/sema_cookie_jar; } ||:
}
trap finish EXIT

[ -e /vagrant/evbays/sema_cookie_jar ] || {
    echo trying to obtain login cookie from network.semaconnect.com
    # Note: there may be issues with the log in. To keep things simple, lets just deal with that when sanity checking the data later on
    curl --max-time 60 --silent --show-error -c /vagrant/evbays/sema_cookie_jar -d "${SEMA_LOGIN}" https://network.semaconnect.com/validate_login.php
}

curl --max-time 60 --silent --show-error -b /vagrant/evbays/sema_cookie_jar -d "${SEMA_LOCATION}" -o "${TMPFILE}" https://network.semaconnect.com/get_data.php

# sanity check the data obtained
cat "${TMPFILE}"
sane=$(jq '.aaData.stations[].name' "${TMPFILE}" | grep -v null | wc -l)
[ "${sane}" -gt 0 ] || { echo "unexpected data from sema location: ${sane}" >&2; exit 4; }

# life is good, from this point on consider the cookie jar a valid and reusable
remove_sema_cookie_jar="no"
mv --verbose -f "${TMPFILE}" /vagrant/evbays/sema.json
exit 0
