#!/usr/bin/env bash
# Run on a fresh Ubuntu 24.04 ARM64/x86_64 host from the checked-out repository.
set -euo pipefail
PT_SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PT_INSTALL_DIR=/opt/papertrade
if [[ "$(uname -s)" != Linux ]]; then
  echo "This installer targets Ubuntu Linux. Use README.md for local setup." >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-dev build-essential libgomp1 rsync ca-certificates
python3 -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ required; use Ubuntu 24.04"'
if ! id papertrade >/dev/null 2>&1; then
  sudo useradd --system --create-home --home-dir "$PT_INSTALL_DIR" --shell /usr/sbin/nologin papertrade
fi
sudo install -d -m 0750 -o papertrade -g papertrade "$PT_INSTALL_DIR" "$PT_INSTALL_DIR/var"
if [[ "$PT_SOURCE_DIR" != "$PT_INSTALL_DIR" ]]; then
  sudo rsync -a --exclude=.git --exclude=.venv --exclude=.env --exclude=var --exclude=__pycache__ \
    --exclude=.pytest_cache --exclude=.ruff_cache "$PT_SOURCE_DIR/" "$PT_INSTALL_DIR/"
fi
sudo chown -R papertrade:papertrade "$PT_INSTALL_DIR"
sudo -u papertrade python3 -m venv "$PT_INSTALL_DIR/.venv"
sudo -u papertrade "$PT_INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo -u papertrade "$PT_INSTALL_DIR/.venv/bin/python" -m pip install -r "$PT_INSTALL_DIR/requirements.lock.txt"
sudo -u papertrade "$PT_INSTALL_DIR/.venv/bin/python" -m pip install --no-deps -e "$PT_INSTALL_DIR"
cd "$PT_INSTALL_DIR"
sudo -u papertrade "$PT_INSTALL_DIR/.venv/bin/python" scripts/configure_env.py
sudo -u papertrade "$PT_INSTALL_DIR/.venv/bin/papertrade" init-db
sudo install -m 0644 deploy/papertrade-*.service deploy/papertrade-*.timer /etc/systemd/system/
sudo install -m 0644 deploy/papertrade-logrotate /etc/logrotate.d/papertrade
sudo systemctl daemon-reload
echo "Installed in $PT_INSTALL_DIR. AI and strategy execution default OFF. Configure .env, models and validated strategies, then follow DEPLOYMENT.md to start services."
