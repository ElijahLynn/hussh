---
name: porkbun-domain-ops
description: >-
  Manage DNS records, URL forwarding, nameservers, and dynamic tunnel routing
  for hussh.tech via the Porkbun API v3 (`scripts/porkbun-dns.py`). Use when
  configuring or inspecting hussh.tech domain settings, Cloudflare tunnels, or
  Porkbun DNS records.
---

# Porkbun Domain Operations (`hussh.tech`)

## 1. Safe Credentials Verification
Porkbun API v3 requires two keys in `~/.env` (or project `.env`):
- `PORKBUN_API_KEY` (starts with `pk1_...`)
- `PORKBUN_SECRET_KEY` (starts with `sk1_...`)

Also ensure **API Access** is toggled ON for `hussh.tech` in the Porkbun Domain Management dashboard (Domain Management → `hussh.tech` → Details → API Access).

Always verify presence safely without echoing keys into context:
```powershell
pwsh -NoProfile -Command "exit ([int]!(Test-Path ~/.env -and (Select-String -Path ~/.env -Pattern '^PORKBUN_API_KEY=' -Quiet) -and (Select-String -Path ~/.env -Pattern '^PORKBUN_SECRET_KEY=' -Quiet)))"
```

---

## 2. CLI Commands (`scripts/porkbun-dns.py`)
Run `python scripts/porkbun-dns.py` with the following subcommands:

| Action | Command | Description |
| :--- | :--- | :--- |
| **Ping & Auth Check** | `python scripts/porkbun-dns.py ping` | Verifies API keys and returns your public IP. |
| **List DNS Records** | `python scripts/porkbun-dns.py list` | Displays all current `A`, `CNAME`, `ALIAS`, `TXT`, and `NS` records on `hussh.tech`. |
| **Sync Quick Tunnel** | `python scripts/porkbun-dns.py sync-board --host hush-board` | Reads `demo-url.txt` from the UNO Q board over SSH and configures `hussh.tech` / `demo.hussh.tech` redirect or CNAME. |
| **Set URL Forward** | `python scripts/porkbun-dns.py set-forward --subdomain "" --target "https://example.trycloudflare.com"` | Sets Porkbun HTTPS URL forwarding from `hussh.tech` (or a subdomain) to any target URL. |
| **Upsert DNS Record** | `python scripts/porkbun-dns.py upsert --type CNAME --name demo --content "<target>"` | Creates or updates a DNS record (`A`, `AAAA`, `CNAME`, `ALIAS`, `TXT`) idempotently. |

---

## 3. Recommended `hussh.tech` Architecture Options
1. **Option A — Porkbun Native DNS + Dynamic Quick-Tunnel Forwarding (Fastest Hackathon Setup)**:
   - Keep Porkbun nameservers (`curitiba.ns.porkbun.com`, `fortaleza.ns.porkbun.com`, `maceio.ns.porkbun.com`, `salvador.ns.porkbun.com`).
   - Run `python scripts/porkbun-dns.py set-forward --target <trycloudflare-url>` (or automate it on the UNO Q board inside `run-phone-vu-tunnel.sh`) so `https://hussh.tech` automatically redirects phones to the active `https://*.trycloudflare.com` link—eliminating the need for phones to visit the local IP `reconnect.html` first!
2. **Option B — Permanent Named Cloudflare Tunnel (`hussh.tech` Direct HTTPS)**:
   - Delegate `hussh.tech` nameservers in Porkbun to Cloudflare (`python scripts/porkbun-dns.py set-ns <ns1> <ns2>`) and bind a permanent Named Tunnel token (`cloudflared tunnel run --token ...`) on the UNO Q so `https://hussh.tech` serves the UNO Q dashboard directly without URL changes.

