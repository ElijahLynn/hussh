#!/usr/bin/env python3
"""
Porkbun API v3 manager for hussh.tech.
Zero third-party dependencies (uses Python standard library urllib + json).
Loads PORKBUN_API_KEY and PORKBUN_SECRET_KEY from ~/.env or ./.env automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = "https://api.porkbun.com/api/json/v3"
ALLOWED_DOMAINS = {"hussh.tech"}


def assert_domain_allowed(domain: str) -> None:
    if domain.lower().strip() not in ALLOWED_DOMAINS:
        sys.stderr.write(
            f"SECURITY GUARD: Refusing to operate on '{domain}'. "
            f"Only {sorted(ALLOWED_DOMAINS)} is permitted by this project.\n"
        )
        sys.exit(3)


def load_dotenv() -> None:
    """Load key=value pairs from ~/.env and ./.env without external packages."""
    candidates = [Path.home() / ".env", Path.cwd() / ".env"]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


def get_credentials() -> dict[str, str]:
    load_dotenv()
    api_key = os.environ.get("PORKBUN_API_KEY", "").strip()
    secret_key = os.environ.get("PORKBUN_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        sys.stderr.write(
            "ERROR: Missing PORKBUN_API_KEY or PORKBUN_SECRET_KEY in ~/.env or ./.env.\n"
        )
        sys.exit(2)
    return {"apikey": api_key, "secretapikey": secret_key}


def api_post(endpoint: str, payload: dict | None = None) -> dict:
    body = get_credentials()
    if payload:
        body.update(payload)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/{endpoint.lstrip('/')}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "hussh-porkbun-cli/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_Text = exc.read().decode("utf-8", errors="replace")
        sys.stderr.write(f"HTTP {exc.code} from Porkbun ({endpoint}): {err_Text}\n")
        sys.exit(1)
    except urllib.error.URLError as exc:
        sys.stderr.write(f"Network error contacting Porkbun ({endpoint}): {exc}\n")
        sys.exit(1)


def cmd_ping(_args: argparse.Namespace) -> None:
    res = api_post("ping")
    print(f"Status: {res.get('status')} | Your IP: {res.get('yourIp')}")


def cmd_list(args: argparse.Namespace) -> None:
    res = api_post(f"dns/retrieve/{args.domain}")
    records = res.get("records", [])
    print(f"DNS Records for {args.domain} ({len(records)} total):")
    for rec in records:
        print(
            f"  [{rec.get('id')}] {rec.get('type'):6s} "
            f"{rec.get('name'):25s} -> {rec.get('content')} (TTL {rec.get('ttl')})"
        )


def cmd_upsert(args: argparse.Namespace) -> None:
    sub = args.name.strip()
    fqdn = f"{sub}.{args.domain}" if sub and sub != "@" else args.domain
    existing = api_post(f"dns/retrieveByNameType/{args.domain}/{args.type}/{sub if sub and sub != '@' else ''}")
    records = existing.get("records", [])
    payload = {
        "name": "" if sub in ("", "@") else sub,
        "type": args.type.upper(),
        "content": args.content,
        "ttl": str(args.ttl),
    }
    if records:
        rec_id = records[0]["id"]
        api_post(f"dns/edit/{args.domain}/{rec_id}", payload)
        print(f"Updated {args.type} record [{rec_id}] for {fqdn} -> {args.content}")
    else:
        res = api_post(f"dns/create/{args.domain}", payload)
        print(f"Created {args.type} record [{res.get('id')}] for {fqdn} -> {args.content}")


def cmd_set_forward(args: argparse.Namespace) -> None:
    sub = "" if args.subdomain in ("", "@") else args.subdomain.strip()
    existing = api_post(f"domain/getUrlForwarding/{args.domain}")
    for fwd in existing.get("forwards", []):
        if fwd.get("subdomain", "") == sub:
            api_post(f"domain/deleteUrlForward/{args.domain}/{fwd['id']}")
            print(f"Removed previous URL forward [{fwd['id']}] for '{sub or '@'}'")

    payload = {
        "subdomain": sub,
        "location": args.target,
        "type": args.type,
        "includePath": "yes" if args.include_path else "no",
        "wildcard": "yes" if args.wildcard else "no",
    }
    api_post(f"domain/addUrlForward/{args.domain}", payload)
    host = f"{sub}.{args.domain}" if sub else args.domain
    print(f"Configured URL forward: https://{host} -> {args.target} ({args.type})")


def cmd_list_forwards(args: argparse.Namespace) -> None:
    res = api_post(f"domain/getUrlForwarding/{args.domain}")
    forwards = res.get("forwards", [])
    print(f"URL Forwards for {args.domain} ({len(forwards)} total):")
    for fwd in forwards:
        sub = fwd.get("subdomain") or "@"
        print(f"  [{fwd.get('id')}] {sub} -> {fwd.get('location')} ({fwd.get('type')})")


def cmd_sync_board(args: argparse.Namespace) -> None:
    cmd = ["ssh", args.host, "cat /home/arduino/ArduinoApps/phone-vu/assets/demo-url.txt"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write(f"Failed to read demo-url.txt from {args.host}: {proc.stderr}\n")
        sys.exit(1)
    url = proc.stdout.strip()
    if not url.startswith("https://"):
        sys.stderr.write(f"Invalid tunnel URL on board: {url!r}\n")
        sys.exit(1)
    ns = argparse.Namespace(
        domain=args.domain,
        subdomain=args.subdomain,
        target=url,
        type="temporary",
        include_path=True,
        wildcard=False,
    )
    cmd_set_forward(ns)


def cmd_sync_stop(args: argparse.Namespace) -> None:
    stop_id = str(args.stop).strip()
    base = args.target.rstrip("/")
    target_url = f"{base}/?stop={stop_id}"
    if args.name:
        from urllib.parse import quote_plus
        target_url += f"&name={quote_plus(args.name)}"
    sub = f"stop-{stop_id}"
    ns = argparse.Namespace(
        domain=args.domain,
        subdomain=sub,
        target=target_url,
        type="temporary",
        include_path=False,
        wildcard=False,
    )
    cmd_set_forward(ns)
    if args.also_root:
        ns_root = argparse.Namespace(
            domain=args.domain,
            subdomain="",
            target=target_url,
            type="temporary",
            include_path=False,
            wildcard=False,
        )
        cmd_set_forward(ns_root)


def cmd_get_ns(args: argparse.Namespace) -> None:
    res = api_post(f"domain/getNs/{args.domain}")
    for ns in res.get("ns", []):
        print(f"  {ns}")


def cmd_set_ns(args: argparse.Namespace) -> None:
    api_post(f"domain/updateNs/{args.domain}", {"ns": args.nameservers})
    print(f"Updated nameservers for {args.domain}: {', '.join(args.nameservers)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Porkbun DNS & Forwarding CLI for hussh.tech")
    parser.add_argument("--domain", default="hussh.tech", help="Domain name (locked to hussh.tech)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping", help="Verify Porkbun API credentials and connectivity").set_defaults(
        func=cmd_ping
    )
    sub.add_parser("list", help="List all DNS records").set_defaults(func=cmd_list)

    p_upsert = sub.add_parser("upsert", help="Create or update a DNS record")
    p_upsert.add_argument("--type", required=True, help="Record type (A, AAAA, CNAME, ALIAS, TXT)")
    p_upsert.add_argument("--name", default="@", help="Subdomain or '@' for root")
    p_upsert.add_argument("--content", required=True, help="Record target/content")
    p_upsert.add_argument("--ttl", type=int, default=600, help="TTL in seconds (min 600)")
    p_upsert.set_defaults(func=cmd_upsert)

    p_fwd = sub.add_parser("set-forward", help="Configure Porkbun URL forwarding")
    p_fwd.add_argument("--subdomain", default="", help="Subdomain (empty or '@' for root)")
    p_fwd.add_argument("--target", required=True, help="Destination URL (e.g. https://...trycloudflare.com)")
    p_fwd.add_argument("--type", choices=["temporary", "permanent"], default="temporary")
    p_fwd.add_argument("--include-path", action="store_true", default=True)
    p_fwd.add_argument("--wildcard", action="store_true", default=False)
    p_fwd.set_defaults(func=cmd_set_forward)

    sub.add_parser("list-forwards", help="List active URL forwards").set_defaults(
        func=cmd_list_forwards
    )

    p_sync = sub.add_parser(
        "sync-board", help="Fetch active Cloudflare Quick Tunnel from UNO Q board and forward hussh.tech to it"
    )
    p_sync.add_argument("--host", default="hush-board", help="SSH host alias for UNO Q board")
    p_sync.add_argument("--subdomain", default="", help="Subdomain to forward (default: root hussh.tech)")
    p_sync.set_defaults(func=cmd_sync_board)

    p_stop = sub.add_parser(
        "sync-stop", help="Route stop-<ID>.hussh.tech (TriMet Stop ID) to a target Hush URL with ?stop=<ID>"
    )
    p_stop.add_argument("--stop", required=True, help="TriMet Stop ID (e.g. 7777, 8333, 2592, 365)")
    p_stop.add_argument("--target", required=True, help="Base HTTPS tunnel URL (e.g. https://...trycloudflare.com)")
    p_stop.add_argument("--name", default="", help="Optional stop location label (e.g. 'Pioneer Sq South')")
    p_stop.add_argument("--also-root", action="store_true", help="Also forward root hussh.tech to this stop")
    p_stop.set_defaults(func=cmd_sync_stop)

    sub.add_parser("get-ns", help="Get authoritative nameservers").set_defaults(func=cmd_get_ns)

    p_ns = sub.add_parser("set-ns", help="Update authoritative nameservers")
    p_ns.add_argument("nameservers", nargs="+", help="Nameserver hostnames")
    p_ns.set_defaults(func=cmd_set_ns)

    args = parser.parse_args()
    assert_domain_allowed(args.domain)
    args.func(args)


if __name__ == "__main__":
    main()

