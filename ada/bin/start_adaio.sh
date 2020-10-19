#!/usr/bin/env bash
set -o errexit
#set -o xtrace

cd "$(dirname $0)"

BIN_DIR="$(pwd -P)"
PROG_DIR="${BIN_DIR%/*}"
TOP_DIR="${PROG_DIR%/*}"

cd ${TOP_DIR}/env
source ./bin/activate
export PYTHONPATH=${PYTHONPATH:-$TOP_DIR}
[ -e "/vagrant/.secrets" ] && source /vagrant/.secrets
[ -e "/vagrant/.knobs" ] && source /vagrant/.knobs

cd ${PROG_DIR} && ./main.py $@

exit 0
