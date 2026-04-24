#!/bin/sh
# LuckFox Pico Pi / Buildroot installer for UPS Plus scripts.

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV_DIR="${SCRIPT_DIR}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python3"
BIN_DIR="/usr/local/bin"
INIT_TEMPLATE="${SCRIPT_DIR}/upsplusv5-prometheus-exporter.initd"
INIT_TARGET="/etc/init.d/S80upsplusv5-prometheus-exporter"
PIDFILE="/var/run/upsplusv5-prometheus-exporter.pid"
LOGFILE="/var/log/upsplusv5-prometheus-exporter.log"
PORT="${UPSPLUS_EXPORTER_PORT:-9105}"

ENABLE_EXPORTER=1
ENABLE_MONITOR_CRON=0
ENABLE_IOT_CRON=0

info() {
  printf '%s\n' "$*"
}

fail() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: sh install.sh [options]

Options:
  --no-exporter-service   Do not install/start the Prometheus exporter init script
  --enable-monitor-cron   Add a cron entry to run upsplus.py every minute
  --enable-iot-cron       Add a cron entry to run upsplus_iot.py every minute
  --help                  Show this help
EOF
}

need_root() {
  [ "$(id -u)" -eq 0 ] || fail "Run as root on the LuckFox."
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

venv_uses_system_site_packages() {
  [ -f "${VENV_DIR}/pyvenv.cfg" ] || return 1
  grep -qi '^include-system-site-packages *= *true' "${VENV_DIR}/pyvenv.cfg"
}

ensure_venv() {
  if [ ! -x "$VENV_PYTHON" ]; then
    info "Creating virtual environment at ${VENV_DIR}"
    python3 -m venv --system-site-packages "$VENV_DIR"
    return
  fi

  if ! venv_uses_system_site_packages; then
    info "Recreating virtual environment with system site-packages"
    rm -rf "$VENV_DIR"
    python3 -m venv --system-site-packages "$VENV_DIR"
  fi
}

install_wrapper() {
  name="$1"
  target="$2"
  cat > "${BIN_DIR}/${name}" <<EOF
#!/bin/sh
exec "${VENV_PYTHON}" "${target}" "\$@"
EOF
  chmod 0755 "${BIN_DIR}/${name}"
}

append_cron_line() {
  line="$1"
  current=$(crontab -l 2>/dev/null || true)
  printf '%s\n' "$current" | grep -F -q "$line" && return 0
  (
    printf '%s\n' "$current"
    printf '%s\n' "$line"
  ) | crontab -
}

install_exporter_service() {
  [ -f "$INIT_TEMPLATE" ] || fail "Missing init script template: $INIT_TEMPLATE"

  sed \
    -e "s|^WORKDIR=.*|WORKDIR=\"${SCRIPT_DIR}\"|" \
    -e "s|^PYTHON=.*|PYTHON=\"${VENV_PYTHON}\"|" \
    -e "s|^PORT=.*|PORT=\"${PORT}\"|" \
    "$INIT_TEMPLATE" > "$INIT_TARGET"
  chmod 0755 "$INIT_TARGET"

  if "$INIT_TARGET" status >/dev/null 2>&1; then
    "$INIT_TARGET" restart
  else
    "$INIT_TARGET" start
  fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --no-exporter-service)
      ENABLE_EXPORTER=0
      ;;
    --enable-monitor-cron)
      ENABLE_MONITOR_CRON=1
      ;;
    --enable-iot-cron)
      ENABLE_IOT_CRON=1
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
need_cmd python3
need_cmd git
need_cmd i2cdetect

info "Installing UPS Plus support for LuckFox Pico Pi"
info "Repo: ${SCRIPT_DIR}"

ensure_venv

info "Installing Python dependencies into ${VENV_DIR}"
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install \
  pi-ina219 \
  smbus2 \
  requests \
  prometheus_client

info "Installing command wrappers into ${BIN_DIR}"
install_wrapper upsplus "${SCRIPT_DIR}/upsplus.py"
install_wrapper upsplus-iot "${SCRIPT_DIR}/upsplus_iot.py"
install_wrapper upsplusv5-prometheus-exporter "${SCRIPT_DIR}/upsplusv5-prometheus-exporter.py"
install_wrapper upsplus-demo "${SCRIPT_DIR}/Full-featured-demo-code.py"
install_wrapper upsplus-ota "${SCRIPT_DIR}/OTA_firmware_upgrade.py"

if [ "$ENABLE_MONITOR_CRON" -eq 1 ] || [ "$ENABLE_IOT_CRON" -eq 1 ]; then
  need_cmd crontab
fi

if [ "$ENABLE_MONITOR_CRON" -eq 1 ]; then
  info "Adding cron entry for upsplus.py"
  append_cron_line "* * * * * ${BIN_DIR}/upsplus >> /tmp/upsplus.log 2>&1"
fi

if [ "$ENABLE_IOT_CRON" -eq 1 ]; then
  info "Adding cron entry for upsplus_iot.py"
  append_cron_line "* * * * * ${BIN_DIR}/upsplus-iot >> /tmp/upsplus_iot.log 2>&1"
fi

info "Testing UPS script"
"$VENV_PYTHON" "${SCRIPT_DIR}/upsplus.py"

if [ "$ENABLE_EXPORTER" -eq 1 ]; then
  info "Installing Prometheus exporter service"
  install_exporter_service
fi

info "Install complete."
info "Commands:"
info "  ${BIN_DIR}/upsplus"
info "  ${BIN_DIR}/upsplus-iot"
info "  ${BIN_DIR}/upsplusv5-prometheus-exporter"
if [ "$ENABLE_EXPORTER" -eq 1 ]; then
  info "Exporter status:"
  "$INIT_TARGET" status || true
  info "Metrics: http://<luckfox-ip>:${PORT}/metrics"
fi
