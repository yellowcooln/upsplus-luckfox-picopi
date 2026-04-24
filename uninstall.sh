#!/bin/sh
# LuckFox Pico Pi / Buildroot uninstaller for UPS Plus scripts.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV_DIR="${SCRIPT_DIR}/.venv"
INIT_TARGET="/etc/init.d/S80upsplusv5-prometheus-exporter"
PIDFILE="/var/run/upsplusv5-prometheus-exporter.pid"
LOGFILE="/var/log/upsplusv5-prometheus-exporter.log"

REMOVE_VENV=1

info() {
  printf '%s\n' "$*"
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: sh uninstall.sh [options]

Options:
  --keep-venv   Keep the repo-local virtual environment
  --help        Show this help
EOF
}

need_root() {
  [ "$(id -u)" -eq 0 ] || fail "Run as root on the LuckFox."
}

remove_cron_lines() {
  if ! command -v crontab >/dev/null 2>&1; then
    return 0
  fi

  current=$(crontab -l 2>/dev/null || true)
  updated=$(printf '%s\n' "$current" | grep -v 'upsplus' || true)
  printf '%s\n' "$updated" | crontab -
}

while [ $# -gt 0 ]; do
  case "$1" in
    --keep-venv)
      REMOVE_VENV=0
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
  shift
done

need_root

if [ -x "$INIT_TARGET" ]; then
  info "Stopping exporter service"
  "$INIT_TARGET" stop || true
  rm -f "$INIT_TARGET"
fi

remove_cron_lines

info "Removing wrapper commands"
rm -f \
  /usr/local/bin/upsplus \
  /usr/local/bin/upsplus-iot \
  /usr/local/bin/upsplusv5-prometheus-exporter \
  /usr/local/bin/upsplus-demo \
  /usr/local/bin/upsplus-ota

rm -f "$PIDFILE" "$LOGFILE"

if [ "$REMOVE_VENV" -eq 1 ]; then
  info "Removing ${VENV_DIR}"
  rm -rf "$VENV_DIR"
fi

info "Uninstall complete."
