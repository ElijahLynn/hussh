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
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://api.porkbun.com/api/json/v3"
ALLOWED_DOMAINS = {"hussh.tech"}
ALLOWED_RECORD_TYPES = {"A", "AAAA", "CNAME", "ALIAS", "TXT"}

SUBDOMAIN_RE = re.compile(
    r"^(?:\*|[a-z0-9](?:[a-z0-9_-]{0,61}[a-z0-9])?)(?:\.[a-z0-9](?:[a-z0-9_-]{0,61}[a-z0-9])?)*$",
    re.IGNORECASE,
)
ALLOWED_TARGET_HOST_RE = re.compile(
    r"^(?:[a-z0-9-]+\.trycloudflare\.com|(?:[a-z0-9-]+\.)?hussh\.tech)$",
    re.IGNORECASE,
)
SSH_HOST_RE = re.compile(r"^(?:[A-Za-z0-9_-]+@)?[A-Za-z0-9][A-Za-z0-9._-]{0,252}$")
EMAIL_ALIAS_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}$")
EMAIL_ADDRESS_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
NS_HOST_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def validate_domain(domain: str) -> str:
    cleaned = domain.lower().strip()
    if cleaned not in ALLOWED_DOMAINS:
        raise ValueError(
            f"Refusing to operate on '{domain}'. Only {sorted(ALLOWED_DOMAINS)} is permitted by this project."
        )
    return cleaned


def assert_domain_allowed(domain: str) -> None:
    try:
        validate_domain(domain)
    except ValueError as exc:
        sys.stderr.write(f"SECURITY GUARD: {exc}\n")
        sys.exit(3)


def validate_record_type(rtype: str) -> str:
    cleaned = rtype.strip().upper()
    if cleaned not in ALLOWED_RECORD_TYPES:
        raise ValueError(
            f"Unsupported DNS record type '{rtype}'. Allowed: {sorted(ALLOWED_RECORD_TYPES)}."
        )
    return cleaned


def validate_subdomain(sub: str) -> str:
    cleaned = sub.strip()
    if cleaned in ("", "@"):
        return ""
    if len(cleaned) > 190 or not SUBDOMAIN_RE.match(cleaned):
        raise ValueError(f"Invalid DNS subdomain label: {sub!r}")
    return cleaned.lower()


def validate_forward_target(url: str, allow_external: bool = False) -> str:
    cleaned = url.strip()
    if not cleaned or any(ord(ch) <= 32 or ord(ch) == 127 for ch in cleaned):
        raise ValueError("Forward target URL contains whitespace or control characters.")
    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError(f"Forward target must be a valid https:// URL: {url!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Forward target URL must not include embedded credentials.")
    host = parsed.hostname.lower()
    if not allow_external and not ALLOWED_TARGET_HOST_RE.match(host):
        raise ValueError(
            f"Target host '{host}' is not in the Hush allowlist (*.trycloudflare.com, hussh.tech). "
            "Pass --allow-external-target only when intentionally redirecting outside Hush."
        )
    return cleaned


def validate_ssh_host(host: str) -> str:
    cleaned = host.strip()
    if cleaned.startswith("-") or not SSH_HOST_RE.match(cleaned):
        raise ValueError(f"Invalid SSH target host: {host!r}")
    return cleaned


def validate_email_alias(alias: str) -> str:
    cleaned = alias.strip().lower()
    if not EMAIL_ALIAS_RE.match(cleaned):
        raise ValueError(f"Invalid email alias: {alias!r}")
    return cleaned


def validate_email_address(email: str) -> str:
    cleaned = email.strip()
    if not EMAIL_ADDRESS_RE.match(cleaned):
        raise ValueError(f"Invalid forward email address: {email!r}")
    return cleaned


def validate_nameservers(nameservers: list[str]) -> list[str]:
    if not nameservers:
        raise ValueError("At least one nameserver hostname is required.")
    cleaned_list: list[str] = []
    for ns in nameservers:
        cleaned = ns.strip().lower().rstrip(".")
        if len(cleaned) > 253 or not NS_HOST_RE.match(cleaned):
            raise ValueError(f"Invalid nameserver hostname: {ns!r}")
        cleaned_list.append(cleaned)
    return cleaned_list


def _redact(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted[:300]


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
            if key.startswith("export "):
                key = key[len("export ") :].strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
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
    creds = get_credentials()
    secrets = [creds["apikey"], creds["secretapikey"]]
    body = dict(creds)
    if payload:
        body.update(payload)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/{endpoint.lstrip('/')}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "hussh-porkbun-cli/1.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_text = _redact(exc.read().decode("utf-8", errors="replace"), secrets)
        sys.stderr.write(f"HTTP {exc.code} from Porkbun ({endpoint}): {err_text}\n")
        sys.exit(1)
    except urllib.error.URLError as exc:
        err_text = _redact(str(exc), secrets)
        sys.stderr.write(f"Network error contacting Porkbun ({endpoint}): {err_text}\n")
        sys.exit(1)


def cmd_ping(_args: argparse.Namespace) -> None:
    res = api_post("ping")
    print(f"Status: {res.get('status')} | Your IP: {res.get('yourIp')}")


def cmd_list(args: argparse.Namespace) -> None:
    domain = validate_domain(args.domain)
    res = api_post(f"dns/retrieve/{domain}")
    records = res.get("records", [])
    print(f"DNS Records for {domain} ({len(records)} total):")
    for rec in records:
        print(
            f"  [{rec.get('id')}] {rec.get('type'):6s} "
            f"{rec.get('name'):25s} -> {rec.get('content')} (TTL {rec.get('ttl')})"
        )


def cmd_upsert(args: argparse.Namespace) -> None:
    domain = validate_domain(args.domain)
    rtype = validate_record_type(args.type)
    sub = validate_subdomain(args.name)
    if args.ttl < 600:
        raise ValueError("TTL must be at least 600 seconds for Porkbun DNS.")
    fqdn = f"{sub}.{domain}" if sub else domain
    encoded_sub = urllib.parse.quote(sub, safe="")
    lookup_path = (
        f"dns/retrieveByNameType/{domain}/{rtype}/{encoded_sub}"
        if sub
        else f"dns/retrieveByNameType/{domain}/{rtype}/"
    )
    existing = api_post(lookup_path)
    records = existing.get("records", [])
    payload = {
        "name": sub,
        "type": rtype,
        "content": args.content.strip(),
        "ttl": str(args.ttl),
    }
    if records:
        rec_id = urllib.parse.quote(str(records[0]["id"]), safe="")
        api_post(f"dns/edit/{domain}/{rec_id}", payload)
        print(f"Updated {rtype} record [{rec_id}] for {fqdn} -> {payload['content']}")
    else:
        res = api_post(f"dns/create/{domain}", payload)
        print(f"Created {rtype} record [{res.get('id')}] for {fqdn} -> {payload['content']}")


def cmd_set_forward(args: argparse.Namespace) -> None:
    domain = validate_domain(args.domain)
    sub = validate_subdomain(args.subdomain)
    allow_ext = bool(getattr(args, "allow_external_target", False))
    target = validate_forward_target(args.target, allow_external=allow_ext)

    existing = api_post(f"domain/getUrlForwarding/{domain}")
    for fwd in existing.get("forwards", []):
        if (fwd.get("subdomain") or "").lower() == sub:
            fwd_id = urllib.parse.quote(str(fwd["id"]), safe="")
            api_post(f"domain/deleteUrlForward/{domain}/{fwd_id}")
            print(f"Removed previous URL forward [{fwd_id}] for '{sub or '@'}'")

    payload = {
        "subdomain": sub,
        "location": target,
        "type": args.type,
        "includePath": "yes" if args.include_path else "no",
        "wildcard": "yes" if args.wildcard else "no",
    }
    api_post(f"domain/addUrlForward/{domain}", payload)
    host = f"{sub}.{domain}" if sub else domain
    print(f"Configured URL forward: https://{host} -> {target} ({args.type})")


def cmd_list_forwards(args: argparse.Namespace) -> None:
    domain = validate_domain(args.domain)
    res = api_post(f"domain/getUrlForwarding/{domain}")
    forwards = res.get("forwards", [])
    print(f"URL Forwards for {domain} ({len(forwards)} total):")
    for fwd in forwards:
        sub = fwd.get("subdomain") or "@"
        print(f"  [{fwd.get('id')}] {sub} -> {fwd.get('location')} ({fwd.get('type')})")


def cmd_sync_board(args: argparse.Namespace) -> None:
    domain = validate_domain(args.domain)
    host = validate_ssh_host(args.host)
    sub = validate_subdomain(args.subdomain)
    cmd = ["ssh", "--", host, "cat /home/arduino/ArduinoApps/phone-vu/assets/demo-url.txt"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"Timed out reading demo-url.txt from {host}.\n")
        sys.exit(1)
    if proc.returncode != 0:
        sys.stderr.write(f"Failed to read demo-url.txt from {host}: {proc.stderr}\n")
        sys.exit(1)
    url = validate_forward_target(proc.stdout.strip(), allow_external=False)
    ns = argparse.Namespace(
        domain=domain,
        subdomain=sub,
        target=url,
        type="temporary",
        include_path=True,
        wildcard=False,
        allow_external_target=False,
    )
    cmd_set_forward(ns)


def cmd_get_ns(args: argparse.Namespace) -> None:
    domain = validate_domain(args.domain)
    res = api_post(f"domain/getNs/{domain}")
    for ns in res.get("ns", []):
        print(f"  {ns}")


def cmd_list_email_forwards(args: argparse.Namespace) -> None:
    domain = validate_domain(args.domain)
    res = api_post(f"domain/getEmailForwarding/{domain}")
    forwards = res.get("forwards", [])
    print(f"Email Forwards for {domain} ({len(forwards)} total):")
    for fwd in forwards:
        print(f"  [{fwd.get('id')}] {fwd.get('alias')}@{domain} -> {fwd.get('destination')}")


def cmd_set_email_forward(args: argparse.Namespace) -> None:
    domain = validate_domain(args.domain)
    alias = validate_email_alias(args.alias)
    dest = validate_email_address(args.destination)
    existing = api_post(f"domain/getEmailForwarding/{domain}")
    for fwd in existing.get("forwards", []):
        if (fwd.get("alias") or "").lower() == alias and (fwd.get("destination") or "") == dest:
            print(f"Email forward already active: {alias}@{domain} -> {dest}")
            return
    payload = {"alias": alias, "destination": dest}
    res = api_post(f"domain/addEmailForward/{domain}", payload)
    print(f"Created email forward [{res.get('id')}]: {alias}@{domain} -> {dest}")


def cmd_set_ns(args: argparse.Namespace) -> None:
    domain = validate_domain(args.domain)
    nameservers = validate_nameservers(args.nameservers)
    api_post(f"domain/updateNs/{domain}", {"ns": nameservers})
    print(f"Updated nameservers for {domain}: {', '.join(nameservers)}")


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
    p_fwd.add_argument("--target", required=True, help="Destination URL (https://*.trycloudflare.com)")
    p_fwd.add_argument("--type", choices=["temporary", "permanent"], default="temporary")
    p_fwd.add_argument("--include-path", action="store_true", default=True)
    p_fwd.add_argument("--wildcard", action="store_true", default=False)
    p_fwd.add_argument(
        "--allow-external-target",
        action="store_true",
        default=False,
        help="Allow forwarding to an HTTPS host outside *.trycloudflare.com / hussh.tech",
    )
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

    sub.add_parser("get-ns", help="Get authoritative nameservers").set_defaults(func=cmd_get_ns)

    sub.add_parser("list-emails", help="List active email forwards").set_defaults(
        func=cmd_list_email_forwards
    )

    p_email = sub.add_parser("set-email", help="Configure email forwarding for hussh.tech")
    p_email.add_argument("--alias", required=True, help="Email alias (e.g. 'team' for team@hussh.tech)")
    p_email.add_argument("--destination", required=True, help="Destination email to forward to")
    p_email.set_defaults(func=cmd_set_email_forward)

    p_ns = sub.add_parser("set-ns", help="Update authoritative nameservers")
    p_ns.add_argument("nameservers", nargs="+", help="Nameserver hostnames")
    p_ns.set_defaults(func=cmd_set_ns)

    args = parser.parse_args()
    assert_domain_allowed(args.domain)
    try:
        args.func(args)
    except ValueError as exc:
        sys.stderr.write(f"SECURITY GUARD: {exc}\n")
        sys.exit(3)


if __name__ == "__main__":
    main()
