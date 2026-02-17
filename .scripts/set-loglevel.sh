#!/bin/sh
set -eu

LEVEL="${1:-INFO}"
LEVEL="$(echo "$LEVEL" | tr '[:lower:]' '[:upper:]')"

ENVFILE="/app/.env"

mkdir -p "$(dirname "$ENVFILE")"
touch "$ENVFILE"
grep -v '^LOGGER_LEVEL=' "$ENVFILE" > "${ENVFILE}.tmp" || true
printf "LOGGER_LEVEL=%s\n" "$LEVEL" >> "${ENVFILE}.tmp"
mv "${ENVFILE}.tmp" "$ENVFILE"

echo "Set LOGGER_LEVEL=$LEVEL in $ENVFILE"
