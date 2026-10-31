#!/bin/sh
set -eu
if [ "$#" -lt 1 ]; then echo "Usage: $0 SSH_TARGET [--ui-only|--server-only]" >&2; exit 2; fi
ssh_run(){ if [ -n "${SSH_CONFIG:-}" ]; then ssh -F "$SSH_CONFIG" "$@"; else ssh "$@"; fi; }
scp_run(){ if [ -n "${SSH_CONFIG:-}" ]; then scp -F "$SSH_CONFIG" "$@"; else scp "$@"; fi; }
target=$1
mode=${2:-full}
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
case "$mode" in
 --ui-only) files=assets ;;
 --server-only) files='assets python' ;;
 full) files='app.yaml assets python sketch' ;;
 *) echo 'Unknown deploy mode' >&2; exit 2 ;;
esac
# files is a fixed list from the case above, not arbitrary user input.
tar -C "$root" --exclude='__pycache__' --exclude='demo-url.txt*' -czf "$build/hush.tgz" $files
ssh_run "$target" 'mkdir -p /home/arduino/ArduinoApps/phone-vu'
scp_run "$build/hush.tgz" "$target:/home/arduino/hush-upload.tgz"
ssh_run "$target" 'tar -xzf /home/arduino/hush-upload.tgz -C /home/arduino/ArduinoApps/phone-vu && rm /home/arduino/hush-upload.tgz'
case "$mode" in
 --ui-only) echo 'UI deployed. Refresh the secure dashboard.' ;;
 --server-only) ssh_run "$target" 'docker restart phone-vu-main-1' ;;
 full) ssh_run "$target" 'cd /home/arduino; export TMPDIR=/tmp; arduino-app-cli app restart /home/arduino/ArduinoApps/phone-vu && /opt/openocd/bin/arduino-reset.sh' ;;
esac
