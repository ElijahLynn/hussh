#!/bin/sh
set -u
APP=/home/arduino/ArduinoApps/phone-vu
LOG=/home/arduino/phone-vu-tunnel-current.log
ENV_FILE=/home/arduino/.env
if [ -f "$ENV_FILE" ]; then
  . "$ENV_FILE"
fi
rm -f "$APP/assets/demo-url.txt"
: > "$LOG"
if [ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
  /home/arduino/cloudflared tunnel --no-autoupdate --protocol http2 run --token "$CLOUDFLARE_TUNNEL_TOKEN" >> "$LOG" 2>&1 &
  tunnel_pid=$!
  FIXED_URL=${HUSSH_PUBLIC_URL:-https://hussh.tech}
else
  /home/arduino/cloudflared tunnel --no-autoupdate \
    --url http://127.0.0.1:7000 --protocol http2 >> "$LOG" 2>&1 &
  tunnel_pid=$!
  FIXED_URL=""
fi
trap 'kill "$tunnel_pid" 2>/dev/null; rm -f "$APP/assets/demo-url.txt"' EXIT
trap 'exit 0' TERM INT
sleep 10
ready=0
failures=0
attempts=0
published_porkbun=""
while kill -0 "$tunnel_pid" 2>/dev/null; do
  attempts=$((attempts + 1))
  if [ -n "$FIXED_URL" ]; then
    link=$FIXED_URL
  else
    link=$(sed -n 's/.*\(https:\/\/[a-z0-9-]*\.trycloudflare\.com\).*/\1/p' "$LOG" | head -1)
  fi
  # Avoid rotating a healthy tunnel during a deliberate Python/app restart.
  if ! curl --fail --silent --max-time 3 http://127.0.0.1:7000/ -o /dev/null; then
    sleep 5
    continue
  fi
  if [ -n "$link" ] && curl --fail --silent --max-time 5 "$link/" -o /dev/null; then
    failures=0
    ready=1
    printf '%s\n' "$link" > "$APP/assets/demo-url.txt.tmp"
    mv "$APP/assets/demo-url.txt.tmp" "$APP/assets/demo-url.txt"
    if [ -z "$FIXED_URL" ] && [ "$published_porkbun" != "$link" ] && [ -n "${PORKBUN_API_KEY:-}" ] && [ -f "$APP/scripts/porkbun-dns.py" ]; then
      if python3 "$APP/scripts/porkbun-dns.py" set-forward --target "$link" >> "$LOG" 2>&1; then
        published_porkbun=$link
      fi
    fi
  else
    failures=$((failures + 1))
    if { [ "$ready" -eq 1 ] && [ "$failures" -ge 3 ]; } || \
       { [ "$ready" -eq 0 ] && [ "$attempts" -ge 45 ]; }; then
      echo 'Public tunnel health check failed; requesting automatic restart.' >> "$LOG"
      exit 1
    fi
  fi
  sleep 10
done
wait "$tunnel_pid"
exit 1
