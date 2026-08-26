#!/bin/bash

WORKER_URL="https://busybar-status.matsagerstam.workers.dev/update"
TOKEN="81464ea31125cec489cd8bfa473a92df9096a680316de05e62bce4d1993a6ff8"

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

UPDATED=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo
echo "Simulating work calendar:"
echo "  status  = $STATUS"
echo "  until   = ${UNTIL:-none}"
echo "  updated = $UPDATED"
echo

curl -sS \
  -X POST \
  "$WORKER_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"status\": \"$STATUS\",
    \"until\": \"$UNTIL\",
    \"updated\": \"$UPDATED\"
  }"

echo