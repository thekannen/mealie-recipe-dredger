#!/usr/bin/env bash
set -euo pipefail

TASK="${TASK:-dredger}"
RUN_MODE="${RUN_MODE:-once}"
RUN_INTERVAL_SECONDS="${RUN_INTERVAL_SECONDS:-21600}"
RUN_SCHEDULE_DAY="${RUN_SCHEDULE_DAY:-7}"
RUN_SCHEDULE_TIME="${RUN_SCHEDULE_TIME:-03:00}"
RUNTIME_SITES_FILE="${RUNTIME_SITES_FILE:-/app/data/sites.json}"
ALIGN_SITES_APPLY="${ALIGN_SITES_APPLY:-false}"
ALIGN_SITES_BASELINE_FILE="${ALIGN_SITES_BASELINE_FILE:-}"
ALIGN_SITES_PRUNE_OUTSIDE_CURRENT="${ALIGN_SITES_PRUNE_OUTSIDE_CURRENT:-false}"
ALIGN_SITES_BACKUP_BEFORE_APPLY="${ALIGN_SITES_BACKUP_BEFORE_APPLY:-false}"

run_align_sites_task() {
  local baseline_file="$ALIGN_SITES_BASELINE_FILE"
  if [ -z "$baseline_file" ] && [ -f /app/data/sites.baseline.json ]; then
    baseline_file="/app/data/sites.baseline.json"
  fi

  if [ "$ALIGN_SITES_PRUNE_OUTSIDE_CURRENT" != "true" ] && [ -z "$baseline_file" ]; then
    echo "[error] Missing baseline for diff mode."
    echo "        Set ALIGN_SITES_BASELINE_FILE (recommended), or set ALIGN_SITES_PRUNE_OUTSIDE_CURRENT=true (unsafe)."
    exit 1
  fi

  local cmd=()
  cmd+=(mealie-align-sites)

  if [ -n "${SITES:-}" ]; then
    cmd+=(--sites-file "$SITES")
  fi

  if [ -n "$baseline_file" ]; then
    cmd+=(--baseline-sites-file "$baseline_file")
  fi

  if [ -n "${ALIGN_SITES_TIMEOUT:-}" ]; then
    cmd+=(--timeout "$ALIGN_SITES_TIMEOUT")
  fi

  if [ -n "${ALIGN_SITES_PREVIEW_LIMIT:-}" ]; then
    cmd+=(--preview-limit "$ALIGN_SITES_PREVIEW_LIMIT")
  fi

  if [ -n "${ALIGN_SITES_AUDIT_FILE:-}" ]; then
    cmd+=(--audit-file "$ALIGN_SITES_AUDIT_FILE")
  fi

  if [ "${ALIGN_SITES_INCLUDE_MISSING_SOURCE:-false}" = "true" ]; then
    cmd+=(--include-missing-source)
  fi

  if [ "$ALIGN_SITES_PRUNE_OUTSIDE_CURRENT" = "true" ]; then
    cmd+=(--prune-outside-current)
  fi

  if [ "$ALIGN_SITES_APPLY" = "true" ]; then
    cmd+=(--apply)
  fi

  if [ "$ALIGN_SITES_BACKUP_BEFORE_APPLY" = "true" ]; then
    cmd+=(--backup-before-apply)
  fi

  if [ "${ALIGN_SITES_ASSUME_YES:-false}" = "true" ]; then
    cmd+=(--yes)
  fi

  "${cmd[@]}"
}

initialize_runtime_sites() {
  mkdir -p "$(dirname "$RUNTIME_SITES_FILE")"

  if [ -z "${SITES:-}" ]; then
    if [ -f "$RUNTIME_SITES_FILE" ]; then
      export SITES="$RUNTIME_SITES_FILE"
      echo "[init] SITES not set; using runtime sites file: $SITES"
    elif [ -f /app/sites.json ]; then
      cp /app/sites.json "$RUNTIME_SITES_FILE"
      export SITES="$RUNTIME_SITES_FILE"
      echo "[init] Seeded runtime sites file: $RUNTIME_SITES_FILE"
      echo "[init] SITES not set; defaulting to $SITES"
    else
      echo "[warn] No runtime or bundled sites file found; using built-in defaults."
    fi
    return
  fi

  if [ "$SITES" = "$RUNTIME_SITES_FILE" ] && [ ! -f "$RUNTIME_SITES_FILE" ] && [ -f /app/sites.json ]; then
    cp /app/sites.json "$RUNTIME_SITES_FILE"
    echo "[init] Seeded runtime sites file: $RUNTIME_SITES_FILE"
  fi
}

run_task() {
  case "$TASK" in
    dredger)
      mealie-dredger
      ;;
    cleaner)
      mealie-cleaner
      ;;
    align-sites)
      run_align_sites_task
      ;;
    *)
      echo "[error] Unknown TASK '$TASK'. Use dredger, cleaner, or align-sites."
      exit 1
      ;;
  esac
}

seconds_until_next_schedule() {
  if ! [[ "$RUN_SCHEDULE_DAY" =~ ^[1-7]$ ]]; then
    echo "[error] RUN_SCHEDULE_DAY must be 1-7 (1=Mon, 7=Sun)."
    exit 1
  fi

  if ! [[ "$RUN_SCHEDULE_TIME" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
    echo "[error] RUN_SCHEDULE_TIME must be HH:MM in 24-hour format."
    exit 1
  fi

  local now_epoch current_day today_date target_today_epoch days_ahead next_epoch
  now_epoch="$(date +%s)"
  current_day="$(date +%u)"
  today_date="$(date +%F)"
  target_today_epoch="$(date -d "${today_date} ${RUN_SCHEDULE_TIME}:00" +%s)"
  days_ahead=$((RUN_SCHEDULE_DAY - current_day))

  if [ "$days_ahead" -lt 0 ]; then
    days_ahead=$((days_ahead + 7))
  fi

  if [ "$days_ahead" -eq 0 ] && [ "$now_epoch" -ge "$target_today_epoch" ]; then
    days_ahead=7
  fi

  next_epoch=$((target_today_epoch + days_ahead * 86400))
  echo $((next_epoch - now_epoch))
}

if [ "$RUN_MODE" = "loop" ]; then
  initialize_runtime_sites

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

if [ "$RUN_MODE" = "schedule" ]; then
  initialize_runtime_sites

  echo "[start] Schedule mode enabled (task=$TASK, day=$RUN_SCHEDULE_DAY, time=$RUN_SCHEDULE_TIME)"
  while true; do
    sleep_seconds="$(seconds_until_next_schedule)"
    next_run_human="$(date -d "@$(( $(date +%s) + sleep_seconds ))" "+%Y-%m-%d %H:%M:%S %Z")"
    echo "[sleep] Waiting ${sleep_seconds}s until ${next_run_human}"
    sleep "$sleep_seconds"
    run_task
  done
fi

if [ "$RUN_MODE" = "once" ]; then
  initialize_runtime_sites

  run_task
  exit 0
fi

echo "[error] RUN_MODE must be one of: once, loop, schedule."
exit 1
