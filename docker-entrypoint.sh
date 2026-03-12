#!/bin/sh
set -eu

mkdir -p \
  "${QSM_STORAGE_ROOT:-/app/storage}" \
  "${QSM_DATA_DIR:-/app/storage/db}" \
  "$(dirname "${QSM_RUNTIME_ENV_FILE:-/app/storage/config/settings.env}")" \
  "${LOG_DIR:-/app/storage/logs}" \
  /app/storage/uploads \
  /app/storage/backups

if [ ! -e /app/data ]; then
  ln -s "${QSM_DATA_DIR:-/app/storage/db}" /app/data
fi

if [ ! -e /app/logs ]; then
  ln -s "${LOG_DIR:-/app/storage/logs}" /app/logs
fi

chown -R appuser:appuser /app/storage

exec gosu appuser "$@"
