#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---user}" # --user (default) or --system
REPO_DIR="/home/we4free/agent/repos/kucoin-lane"

if [[ "${MODE}" == "--system" ]]; then
  SYSTEMD_DIR="/etc/systemd/system"
  echo "[install] mode=system"
  echo "[install] copying system unit files..."
  sudo cp "${REPO_DIR}/ops/systemd/kucoin-monitoring-hourly.service" "${SYSTEMD_DIR}/"
  sudo cp "${REPO_DIR}/ops/systemd/kucoin-monitoring-hourly.timer" "${SYSTEMD_DIR}/"
  sudo cp "${REPO_DIR}/ops/systemd/kucoin-monitoring-daily-analysis.service" "${SYSTEMD_DIR}/"
  sudo cp "${REPO_DIR}/ops/systemd/kucoin-monitoring-daily-analysis.timer" "${SYSTEMD_DIR}/"
  sudo cp "${REPO_DIR}/ops/systemd/kucoin-monitoring-weekly-analysis.service" "${SYSTEMD_DIR}/"
  sudo cp "${REPO_DIR}/ops/systemd/kucoin-monitoring-weekly-analysis.timer" "${SYSTEMD_DIR}/"
  sudo cp "${REPO_DIR}/ops/systemd/kucoin-monitoring-monthly-analysis.service" "${SYSTEMD_DIR}/"
  sudo cp "${REPO_DIR}/ops/systemd/kucoin-monitoring-monthly-analysis.timer" "${SYSTEMD_DIR}/"

  echo "[install] reloading daemon..."
  sudo systemctl daemon-reload

  echo "[install] enabling timers..."
  sudo systemctl enable --now kucoin-monitoring-hourly.timer
  sudo systemctl enable --now kucoin-monitoring-daily-analysis.timer
  sudo systemctl enable --now kucoin-monitoring-weekly-analysis.timer
  sudo systemctl enable --now kucoin-monitoring-monthly-analysis.timer

  echo "[install] active timers:"
  systemctl list-timers --all | grep -E "kucoin-monitoring-(hourly|daily|weekly|monthly)" || true
else
  USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"
  mkdir -p "${USER_SYSTEMD_DIR}"
  echo "[install] mode=user"
  echo "[install] copying user unit files..."
  cp "${REPO_DIR}/ops/systemd/user/kucoin-monitoring-hourly.service" "${USER_SYSTEMD_DIR}/"
  cp "${REPO_DIR}/ops/systemd/user/kucoin-monitoring-hourly.timer" "${USER_SYSTEMD_DIR}/"
  cp "${REPO_DIR}/ops/systemd/user/kucoin-monitoring-daily-analysis.service" "${USER_SYSTEMD_DIR}/"
  cp "${REPO_DIR}/ops/systemd/user/kucoin-monitoring-daily-analysis.timer" "${USER_SYSTEMD_DIR}/"
  cp "${REPO_DIR}/ops/systemd/user/kucoin-monitoring-weekly-analysis.service" "${USER_SYSTEMD_DIR}/"
  cp "${REPO_DIR}/ops/systemd/user/kucoin-monitoring-weekly-analysis.timer" "${USER_SYSTEMD_DIR}/"
  cp "${REPO_DIR}/ops/systemd/user/kucoin-monitoring-monthly-analysis.service" "${USER_SYSTEMD_DIR}/"
  cp "${REPO_DIR}/ops/systemd/user/kucoin-monitoring-monthly-analysis.timer" "${USER_SYSTEMD_DIR}/"

  echo "[install] reloading user daemon..."
  systemctl --user daemon-reload

  echo "[install] enabling timers..."
  systemctl --user enable --now kucoin-monitoring-hourly.timer
  systemctl --user enable --now kucoin-monitoring-daily-analysis.timer
  systemctl --user enable --now kucoin-monitoring-weekly-analysis.timer
  systemctl --user enable --now kucoin-monitoring-monthly-analysis.timer

  echo "[install] active user timers:"
  systemctl --user list-timers --all | grep -E "kucoin-monitoring-(hourly|daily|weekly|monthly)" || true
fi

echo "[install] running initial snapshot and daily analysis..."
python3 "${REPO_DIR}/scripts/monitoring_automation.py" snapshot
python3 "${REPO_DIR}/scripts/monitoring_automation.py" analyze --period daily
