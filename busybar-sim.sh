#!/bin/bash

WORKER_URL="https://busybar-status.matsagerstam.workers.dev/update"

STATUS="$1"
MINUTES="${2:-30}"

if [ -z "$STATUS" ]; then
  echo "Usage:"
  echo "  $0 <free|busy|tentative|ooo> [duration_minutes]"
  echo
  echo "Examples:"
  echo "  $0 busy 5"
  echo "  $0 tentative 2"
  echo "  $0 ooo 10"
  echo "  $0 free"
  exit 1
fi

case "$STATUS" in
  busy|tentative|ooo)
    if ! [[ "$MINUTES" =~ ^[0-9]+$ ]]; then
      echo "Duration must be an integer number of minutes."
      exit 1
    fi

    UNTIL=$(date -u -v+"${MINUTES}"M +"%Y-%m-%dT%H:%M:%SZ")
    ;;

  free)
    UNTIL=""
    ;;

  *)
    echo "Invalid status: $STATUS"
    echo "Valid values: free busy tentative ooo"
    exit 1
    ;;
esac

if [ -z "${BUSYBAR_WORKER_TOKEN:-}" ]; then
  echo "Set BUSYBAR_WORKER_TOKEN before running this script." >&2
  exit 1
fi

UPDATED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo
echo "Simulating work calendar:"
echo "  status  = $STATUS"
echo "  until   = ${UNTIL:-none}"
echo "  updated = $UPDATED"
echo

curl -sS --fail \
  -X POST \
  "$WORKER_URL" \
  -H "Authorization: Bearer $BUSYBAR_WORKER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"status\": \"$STATUS\",
    \"until\": \"$UNTIL\",
    \"updated\": \"$UPDATED\"
  }"

echo
