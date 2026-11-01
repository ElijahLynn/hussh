---
name: hussh-board-ops
description: >-
  Run local verification tests (Python array arbitration, JS syntax, C++17 STM32
  firmware stub) and manage wireless SSH deployments and diagnostics for the
  Hush Arduino UNO Q board. Use when testing, deploying, or debugging Hush.
---

# Hush Board Operations & Verification Skill

## 1. Local Pre-Flight Check (No Hardware Required)
Before any commit or deployment, run the cross-platform verification suite:

- **Windows PowerShell**:
  ```powershell
  pwsh ./scripts/check.ps1
  ```
- **POSIX / WSL / Git Bash**:
  ```sh
  ./scripts/check.sh
  ```

This validates:
1. `tests/test_array_state.py` (smoothing, loudest-source arbitration, 2s expiry).
2. `assets/app.js` syntax via `node --check`.
3. `scripts/*.sh` and `startup/*.sh` POSIX shell syntax.
4. `tests/test_firmware.cpp` against `tests/firmware_stub/` (HUSH warning duration and cooldown state machine).

---

## 2. Wireless Deployment Modes (`hush-board`)
Use `./scripts/deploy.sh <target> [mode]` to push updates over Wi-Fi SSH without interrupting unnecessary subsystems:

| Mode | Command | Impact |
| :--- | :--- | :--- |
| **UI Only** | `./scripts/deploy.sh hush-board --ui-only` | Zero downtime; updates `assets/` in place. Refresh browser. |
| **Server + UI** | `./scripts/deploy.sh hush-board --server-only` | Restarts `phone-vu-main-1` container; preserves active HTTPS tunnel. |
| **Full (MCU + App)** | `./scripts/deploy.sh hush-board` | Uploads `app.yaml`, `assets`, `python`, `sketch`; recompiles & resets STM32 MCU. |

---

## 3. Live Board Diagnostics
```sh
ssh hush-board 'systemctl status ssh phone-vu-app phone-vu-tunnel --no-pager'
ssh hush-board 'docker logs --tail 50 phone-vu-main-1'
ssh hush-board 'cat /home/arduino/ArduinoApps/phone-vu/assets/demo-url.txt'
```
If the LED matrix freezes on `set_level` timeouts, reset the STM32 MCU:
```sh
ssh hush-board '/opt/openocd/bin/arduino-reset.sh'
```

