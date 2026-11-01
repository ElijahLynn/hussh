# AGENTS.md — Hush (`hussh.tech`) Antigravity Governance & Project Rules

## 1. Project Overview & Architecture
- **Product**: **Hush** (`hussh.tech`) — A distributed sound-awareness dashboard and microphone array built for the **Arduino UNO Q** (STM32 + Linux/Docker RouterBridge).
- **Privacy Invariant**: Audio never leaves the phones. Only relative loudness levels (`0–100` at 10 Hz) are transmitted over HTTPS/Socket.IO.
- **Stack**:
  - `assets/`: Vanilla ES6 frontend (`app.js`, `hush.css`, `index.html`, `reconnect.html`) + vendored Socket.IO `4.8.1`.
  - `python/`: `array_state.py` (120 ms smoothing, loudest-active arbitration, 2s expiry) + `main.py` (`arduino:web_ui` brick & 10 Hz MCU control loop).
  - `sketch/`: STM32 firmware (`sketch.ino`, `sketch.yaml`) driving the 13-segment blue LED matrix and dual RGB status LEDs.
  - `startup/`: Systemd services (`phone-vu-app.service`, `phone-vu-tunnel.service`, `run-phone-vu-tunnel.sh`) for autonomous power-bank boot and HTTPS tunneling.
  - `scripts/`: Verification (`check.sh`), wireless SSH deployment (`deploy.sh`), and Porkbun DNS automation (`porkbun-dns.py`).

---

## 2. Security & Mozilla HTTP Observatory 125+ Baseline
- **Zero `'unsafe-inline'` in `script-src`**: All client scripts in `assets/` must live in external `.js` files (`app.js`, `reconnect.js`) or carry SHA-256 integrity hashes.
- **Mandatory Security Headers**: Any public-facing proxy, Cloudflare tunnel / edge worker, or static landing page on `hussh.tech` must enforce:
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  - `Cross-Origin-Opener-Policy: same-origin`
  - `Cross-Origin-Resource-Policy: same-origin`
  - `Cross-Origin-Embedder-Policy: credentialless`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `X-Frame-Options: SAMEORIGIN`
  - `X-Content-Type-Options: nosniff`
- **Secret Hygiene**: Never commit `.env`, SSH private keys, Cloudflare tunnel credentials, or Porkbun API keys (`PORKBUN_API_KEY`, `PORKBUN_SECRET_KEY`). Store credentials exclusively in `~/.env` or gitignored `.env`.

---

## 3. Sandboxing & Verification Gate
- **Pre-Deploy Verification**: Always run the full verification suite (`./scripts/check.sh` or `pwsh ./scripts/check.ps1`) before deploying to `hush-board` or committing changes:
  1. Python unit tests (`unittest discover -s tests -v`)
  2. JavaScript syntax check (`node --check assets/app.js`)
  3. Shell syntax check (`sh -n scripts/*.sh startup/*.sh`)
  4. C++17 host-side firmware simulation (`tests/test_firmware.cpp`)
- **Legacy Path Preservation**: The UNO Q board deployment path `/home/arduino/ArduinoApps/phone-vu` and systemd service names (`phone-vu-app`, `phone-vu-tunnel`) are retained intentionally for hardware compatibility unless updated atomically across all scripts.
