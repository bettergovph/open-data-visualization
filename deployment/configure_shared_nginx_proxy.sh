#!/usr/bin/env bash
set -euo pipefail

SHARED_CONFIG="${BETTERGOV_NGINX_CONFIG:-/etc/nginx/conf.d/bettergov-http.conf}"
REDUNDANT_CONFIG="${ODV_NGINX_CONFIG:-/etc/nginx/conf.d/visualizations_nginx.conf}"
shared_backup="$(mktemp /tmp/bettergov-http.conf.backup.XXXXXX)"
shared_candidate="$(mktemp /tmp/bettergov-http.conf.candidate.XXXXXX)"
redundant_backup="$(mktemp /tmp/visualizations-nginx.conf.backup.XXXXXX)"
redundant_existed=false
shared_changed=false

cleanup() {
  rm -f "$shared_candidate" "$shared_backup" "$redundant_backup"
}
trap cleanup EXIT

if ! sudo -n test -f "$SHARED_CONFIG"; then
  echo "Shared Nginx config not found: $SHARED_CONFIG" >&2
  exit 2
fi

sudo -n cp -p "$SHARED_CONFIG" "$shared_backup"
sudo -n cp -p "$SHARED_CONFIG" "$shared_candidate"
python3 - "$shared_candidate" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text()
rules = (
    (r"(?:8000|8001)", "127.0.0.1:8001", "FastAPI"),
    (r"8888", "127.0.0.1:8888", "Rust frontend"),
)
for port_pattern, destination, label in rules:
    pattern = re.compile(
        rf"(?m)^([ \t]*proxy_pass[ \t]+)http://[^;\s]+:{port_pattern}([ \t]*;)"
    )
    text, count = pattern.subn(rf"\g<1>http://{destination}\g<2>", text)
    if count != 1:
        raise SystemExit(f"Expected one {label} proxy_pass; found {count}.")
path.write_text(text)
PY

if ! sudo -n cmp -s "$shared_candidate" "$SHARED_CONFIG"; then
  sudo -n install -m 644 "$shared_candidate" "$SHARED_CONFIG"
  shared_changed=true
fi

if sudo -n test -f "$REDUNDANT_CONFIG"; then
  sudo -n cp -p "$REDUNDANT_CONFIG" "$redundant_backup"
  sudo -n rm -f "$REDUNDANT_CONFIG"
  redundant_existed=true
fi

restore_configs() {
  sudo -n cp -p "$shared_backup" "$SHARED_CONFIG"
  if [[ "$redundant_existed" == true ]]; then
    sudo -n cp -p "$redundant_backup" "$REDUNDANT_CONFIG"
  fi
}

if [[ "$shared_changed" == true || "$redundant_existed" == true ]]; then
  nginx_output="$(sudo -n nginx -t 2>&1)" || {
    printf '%s\n' "$nginx_output" >&2
    restore_configs
    exit 2
  }
  printf '%s\n' "$nginx_output"
  if grep -Fq 'conflicting server name "visualizations.bettergov.ph"' <<< "$nginx_output"; then
    echo "Conflicting visualizations.bettergov.ph vhosts remain; refusing Nginx reload." >&2
    restore_configs
    exit 2
  fi
  if ! sudo -n systemctl reload nginx.service; then
    restore_configs
    exit 2
  fi
  echo "Shared Nginx proxy now routes to loopback; duplicate ODV vhost removed and Nginx reloaded."
else
  echo "Shared Nginx proxy is already configured for loopback; no Nginx reload needed."
fi
