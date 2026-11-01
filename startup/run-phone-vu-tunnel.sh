#!/bin/sh
set -u
APP=/home/arduino/ArduinoApps/phone-vu
LOG=/home/arduino/phone-vu-tunnel-current.log
ENV_FILE=/home/arduino/.env

load_env_var() {
  key=$1
  [ -f "$ENV_FILE" ] || return 0
  val=$(sed -n "s/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}${key}[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" | tail -n 1)
  cr=$(printf '\r')
  val=${val%"$cr"}
  case "$val" in
    \"*\") val=${val#\"}; val=${val%\"} ;;
    \'*\') val=${val#\'}; val=${val%\'} ;;
  esac
  printf '%s' "$val"
}

if [ -z "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
  CLOUDFLARE_TUNNEL_TOKEN=$(load_env_var CLOUDFLARE_TUNNEL_TOKEN)
fi
if [ -z "${HUSSH_PUBLIC_URL:-}" ]; then
  HUSSH_PUBLIC_URL=$(load_env_var HUSSH_PUBLIC_URL)
fi
if [ -z "${PORKBUN_API_KEY:-}" ]; then
  PORKBUN_API_KEY=$(load_env_var PORKBUN_API_KEY)
fi

rm -f "$APP/assets/demo-url.txt"
install -m 600 /dev/null "$LOG"

if [ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]; then
  TUNNEL_TOKEN="$CLOUDFLARE_TUNNEL_TOKEN" /home/arduino/cloudflared tunnel --no-autoupdate \
    --protocol http2 run >> "$LOG" 2>&1 &
  tunnel_pid=$!
  candidate_url=${HUSSH_PUBLIC_URL:-https://hussh.tech}
  if printf '%s\n' "$candidate_url" | grep -Eq '^https://([a-zA-Z0-9-]+\.trycloudflare\.com|([a-zA-Z0-9-]+\.)?hussh\.tech)(/.*)?$'; then
    FIXED_URL=$candidate_url
  else
    echo "Invalid HUSSH_PUBLIC_URL rejected; falling back to https://hussh.tech" >> "$LOG"
    FIXED_URL="https://hussh.tech"
  fi
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
  if [ -n "$link" ] && curl --fail --silent --max-time 5 -- "$link/" -o /dev/null; then
    failures=0
    ready=1
    printf '%s\n' "$link" > "$APP/assets/demo-url.txt.tmp"
    chmod 644 "$APP/assets/demo-url.txt.tmp"
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
