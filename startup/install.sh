#!/bin/sh
set -eu
if [ "$(id -u)" != 0 ]; then echo 'Run with sudo on the UNO Q.' >&2; exit 1; fi
root=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
test -f /home/arduino/ArduinoApps/phone-vu/app.yaml
test -x /home/arduino/cloudflared
backup=/root/hush-startup-backups/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup"
chmod 700 "$backup"
for name in phone-vu-app.service phone-vu-tunnel.service; do
 if [ -e "/etc/systemd/system/$name" ]; then cp -a "/etc/systemd/system/$name" "$backup/"; fi
 install -m 644 "$root/$name" "/etc/systemd/system/$name"
done
if [ -e /home/arduino/run-phone-vu-tunnel.sh ]; then cp -a /home/arduino/run-phone-vu-tunnel.sh "$backup/"; fi
install -o arduino -g arduino -m 755 "$root/run-phone-vu-tunnel.sh" /home/arduino/run-phone-vu-tunnel.sh
systemctl daemon-reload
systemctl enable --now phone-vu-app.service phone-vu-tunnel.service
echo "Startup installed. Previous files: $backup"
