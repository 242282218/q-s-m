#!/bin/sh
set -eu

mkdir -p /app/data /app/logs
chown -R appuser:appuser /app/data /app/logs

exec gosu appuser "$@"
