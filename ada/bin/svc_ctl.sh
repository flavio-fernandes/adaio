#!/usr/bin/env bash
set -o errexit
set -o xtrace

if [ -n "$1" ]; then
  sudo systemctl restart adaio
else
  sudo systemctl stop adaio
fi
sudo systemctl status --full --no-pager adaio
