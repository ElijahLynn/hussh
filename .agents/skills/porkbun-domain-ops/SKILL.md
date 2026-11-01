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
Porkbun API v3 requires two keys in workstation `~/.env` (or project `.env`, gitignored):
- `PORKBUN_API_KEY` (starts with `pk1_...`)
- `PORKBUN_SECRET_KEY` (starts with `sk1_...`)

> **Security Boundary**: Porkbun API keys are account-wide across all API-enabled domains and cannot be scoped to single-record writes. Keep `PORKBUN_API_KEY` / `PORKBUN_SECRET_KEY` on your operator workstation rather than on portable hackathon hardware whenever possible.

Also ensure **API Access** is toggled ON for `hussh.tech` in the Porkbun Domain Management dashboard (Domain Management → `hussh.tech` → Details → API Access).

Always verify presence safely without echoing keys into context:
```powershell
pwsh -NoProfile -Command "exit ([int]!((Test-Path ~/.env) -and (Select-String -Path ~/.env -Pattern '^PORKBUN_API_KEY=' -Quiet) -and (Select-String -Path ~/.env -Pattern '^PORKBUN_SECRET_KEY=' -Quiet)))"
```

---

## 2. CLI Commands (`scripts/porkbun-dns.py`)
`scripts/porkbun-dns.py` enforces domain locking (`hussh.tech` only), DNS label validation, SSH `--` option guards, and an HTTPS target allowlist (`*.trycloudflare.com` and `hussh.tech` by default; pass `--allow-external-target` only for intentional external redirects).

| Action | Command | Description |
| :--- | :--- | :--- |
| **Ping & Auth Check** | `python scripts/porkbun-dns.py ping` | Verifies API keys and returns your public IP. |
| **List DNS Records** | `python scripts/porkbun-dns.py list` | Displays all current `A`, `CNAME`, `ALIAS`, `TXT`, and `NS` records on `hussh.tech`. |
| **Sync Quick Tunnel** | `python scripts/porkbun-dns.py sync-board --host hush-board` | Reads `demo-url.txt` from the UNO Q board over SSH and forwards `hussh.tech` to the validated `*.trycloudflare.com` tunnel. |
| **Set URL Forward** | `python scripts/porkbun-dns.py set-forward --subdomain "" --target "https://example.trycloudflare.com"` | Sets Porkbun HTTPS URL forwarding from `hussh.tech` (or a subdomain) to an allowlisted target URL. |
| **Upsert DNS Record** | `python scripts/porkbun-dns.py upsert --type CNAME --name demo --content "<target>"` | Creates or updates a DNS record (`A`, `AAAA`, `CNAME`, `ALIAS`, `TXT`) idempotently. |

---

## 3. Recommended `hussh.tech` Architecture Options
1. **Option A — Operator-Synced Porkbun Native DNS + Quick Tunnel (Fastest Demo Setup)**:
   - Keep Porkbun nameservers (`curitiba.ns.porkbun.com`, `fortaleza.ns.porkbun.com`, `maceio.ns.porkbun.com`, `salvador.ns.porkbun.com`).
   - Run `python scripts/porkbun-dns.py sync-board --host hush-board` from your workstation so registrar keys never reside on the portable UNO Q board, while `https://hussh.tech` redirects phones to the active `https://*.trycloudflare.com` link.
2. **Option B — Permanent Named Cloudflare Tunnel (`hussh.tech` Direct HTTPS + Observatory 125+ Headers — Recommended Production)**:
   - Delegate `hussh.tech` nameservers in Porkbun to Cloudflare (`python scripts/porkbun-dns.py set-ns <ns1> <ns2>`) and place only a scoped `CLOUDFLARE_TUNNEL_TOKEN` in `/home/arduino/.env` on the UNO Q (`run-phone-vu-tunnel.sh` passes it via `TUNNEL_TOKEN` env var so it never appears in `ps` argv).
   - Attach a Cloudflare Response Header Transform Rule on `hussh.tech` enforcing the Mozilla HTTP Observatory 125+ baseline:
     - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
     - `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' wss: https:; img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'self'`
     - `Cross-Origin-Opener-Policy: same-origin`
     - `Cross-Origin-Resource-Policy: same-origin`
     - `Cross-Origin-Embedder-Policy: credentialless`
     - `Referrer-Policy: strict-origin-when-cross-origin`
     - `X-Frame-Options: SAMEORIGIN`
     - `X-Content-Type-Options: nosniff`
     - `Permissions-Policy: microphone=(self)`
