#!/usr/bin/env bash
set -euo pipefail

TASK="${TASK:-dredger}"
RUN_MODE="${RUN_MODE:-once}"
RUN_INTERVAL_SECONDS="${RUN_INTERVAL_SECONDS:-21600}"

run_task() {
  case "$TASK" in
    dredger)
      mealie-dredger
      ;;
    cleaner)
      mealie-cleaner
      ;;
    *)
      echo "[error] Unknown TASK '$TASK'. Use dredger or cleaner."
      exit 1
      ;;
  esac
}

if [ "$RUN_MODE" = "loop" ]; then
  if ! [[ "$RUN_INTERVAL_SECONDS" =~ ^[0-9]+$ ]]; then
    echo "[error] RUN_INTERVAL_SECONDS must be an integer."
    exit 1
  fi

  echo "[start] Loop mode enabled (task=$TASK, interval=${RUN_INTERVAL_SECONDS}s)"
  while true; do
    run_task
    echo "[sleep] Waiting ${RUN_INTERVAL_SECONDS}s"
    sleep "$RUN_INTERVAL_SECONDS"
  done
fi

if [ "$RUN_MODE" != "once" ]; then
  echo "[error] RUN_MODE must be either 'once' or 'loop'."
  exit 1
fi

run_task
