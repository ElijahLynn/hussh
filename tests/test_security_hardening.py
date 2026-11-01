import importlib.util
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("porkbun_dns", ROOT / "scripts" / "porkbun-dns.py")
porkbun_dns = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(porkbun_dns)


class _CspHtmlInspector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_script = False
        self.current_script_has_src = False
        self.inline_scripts = []
        self.inline_handlers = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        for attr_name in attr_map:
            if attr_name.lower().startswith("on"):
                self.inline_handlers.append((tag, attr_name))
        if tag.lower() == "script":
            self.in_script = True
            self.current_script_has_src = bool(attr_map.get("src"))
            if not self.current_script_has_src:
                self.inline_scripts.append("<script without src>")

    def handle_data(self, data):
        if self.in_script and data.strip():
            self.inline_scripts.append(data.strip()[:40])

    def handle_endtag(self, tag):
        if tag.lower() == "script":
            self.in_script = False
            self.current_script_has_src = False


class SecurityHardeningTests(unittest.TestCase):
    def test_domain_lock(self):
        self.assertEqual(porkbun_dns.validate_domain("HUSSH.TECH "), "hussh.tech")
        for bad in ["evil.com", "hussh.tech.evil.com", "hussh.tec", ""]:
            with self.assertRaises(ValueError):
                porkbun_dns.validate_domain(bad)

    def test_forward_target_allowlist(self):
        self.assertEqual(
            porkbun_dns.validate_forward_target("https://calm-meadow-123.trycloudflare.com"),
            "https://calm-meadow-123.trycloudflare.com",
        )
        self.assertEqual(
            porkbun_dns.validate_forward_target("https://live.hussh.tech/?stop=7777"),
            "https://live.hussh.tech/?stop=7777",
        )
        for bad in [
            "http://calm-meadow-123.trycloudflare.com",
            "https://evil.example.com/phish",
            "https://hussh.tech@evil.example.com",
            "https://admin:secret@hussh.tech",
            "javascript:alert(1)",
            "https://calm.trycloudflare.com\nhttps://evil.com",
        ]:
            with self.assertRaises(ValueError):
                porkbun_dns.validate_forward_target(bad)

        # Explicit override permits external HTTPS but still blocks HTTP and credentials
        self.assertEqual(
            porkbun_dns.validate_forward_target("https://example.org/demo", allow_external=True),
            "https://example.org/demo",
        )
        with self.assertRaises(ValueError):
            porkbun_dns.validate_forward_target("http://example.org/demo", allow_external=True)

    def test_ssh_host_and_double_dash_guard(self):
        self.assertEqual(porkbun_dns.validate_ssh_host("hush-board"), "hush-board")
        self.assertEqual(porkbun_dns.validate_ssh_host("arduino@192.168.1.50"), "arduino@192.168.1.50")
        for bad in ["-oProxyCommand=calc", "--help", "board;id", "board name", ""]:
            with self.assertRaises(ValueError):
                porkbun_dns.validate_ssh_host(bad)

        args = mock.MagicMock(domain="hussh.tech", host="hush-board", subdomain="")
        fake_proc = mock.MagicMock(returncode=0, stdout="https://quick-box.trycloudflare.com\n", stderr="")
        with mock.patch.object(porkbun_dns.subprocess, "run", return_value=fake_proc) as run_mock, \
             mock.patch.object(porkbun_dns, "cmd_set_forward") as fwd_mock:
            porkbun_dns.cmd_sync_board(args)
            called_cmd = run_mock.call_args[0][0]
            self.assertEqual(called_cmd[:3], ["ssh", "--", "hush-board"])
            fwd_mock.assert_called_once()

    def test_dns_label_stop_and_secret_redaction(self):
        self.assertEqual(porkbun_dns.validate_subdomain("@"), "")
        self.assertEqual(porkbun_dns.validate_subdomain("Stop-7777"), "stop-7777")
        for bad_sub in ["../admin", "a/b", "sub?x=1", "-leading"]:
            with self.assertRaises(ValueError):
                porkbun_dns.validate_subdomain(bad_sub)

        for bad_type in ["MX", "CNAME/../../ping", ""]:
            with self.assertRaises(ValueError):
                porkbun_dns.validate_record_type(bad_type)

        for bad_ns in ["-bad.ns.com", "not_a_host", ""]:
            with self.assertRaises(ValueError):
                porkbun_dns.validate_nameservers([bad_ns])

        redacted = porkbun_dns._redact("err pk1_testsecret and sk1_supersecret", ["pk1_testsecret", "sk1_supersecret"])
        self.assertNotIn("pk1_testsecret", redacted)
        self.assertNotIn("sk1_supersecret", redacted)

    def test_zero_unsafe_inline_scripts_across_assets(self):
        html_files = sorted((ROOT / "assets").glob("*.html"))
        self.assertGreaterEqual(len(html_files), 3)
        for html_file in html_files:
            inspector = _CspHtmlInspector()
            inspector.feed(html_file.read_text(encoding="utf-8"))
            self.assertEqual(
                inspector.inline_scripts,
                [],
                f"{html_file.name} contains inline <script> violating CSP zero-unsafe-inline",
            )
            self.assertEqual(
                inspector.inline_handlers,
                [],
                f"{html_file.name} contains inline event handlers violating CSP zero-unsafe-inline",
            )

    def test_tunnel_script_avoids_dotenv_source_and_cli_token(self):
        tunnel_sh = (ROOT / "startup" / "run-phone-vu-tunnel.sh").read_text(encoding="utf-8")
        self.assertNotRegex(tunnel_sh, re.compile(r"^\s*\.\s+[\"']?\$ENV_FILE", re.MULTILINE))
        self.assertNotIn("--token", tunnel_sh)
        self.assertIn("TUNNEL_TOKEN=", tunnel_sh)


if __name__ == "__main__":
    unittest.main()

