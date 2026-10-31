#!/bin/sh
set -u
APP=/home/arduino/ArduinoApps/phone-vu
LOG=/home/arduino/phone-vu-tunnel-current.log
rm -f "$APP/assets/demo-url.txt"
: > "$LOG"
/home/arduino/cloudflared tunnel --no-autoupdate --url http://localhost:7000 --protocol http2 >> "$LOG" 2>&1 &
tunnel_pid=$!
trap 'kill "$tunnel_pid" 2>/dev/null; rm -f "$APP/assets/demo-url.txt"' EXIT
trap 'exit 0' TERM INT
sleep 10
while kill -0 "$tunnel_pid" 2>/dev/null; do
  link=$(sed -n 's/.*\(https:\/\/[a-z0-9-]*\.trycloudflare\.com\).*/\1/p' "$LOG" | head -1)
  if [ -n "$link" ] && curl --fail --silent --max-time 5 "$link/" -o /dev/null; then
    printf '%s\n' "$link" > "$APP/assets/demo-url.txt.tmp"
    mv "$APP/assets/demo-url.txt.tmp" "$APP/assets/demo-url.txt"
    wait "$tunnel_pid"
    exit 1
  fi
  sleep 2
done
wait "$tunnel_pid"
exit 1
