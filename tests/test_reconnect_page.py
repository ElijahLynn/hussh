"""
Runs assets/reconnect.js in Node with a fake page and a fake demo-url.txt, and checks what
the visitor sees. Guards the job of the reconnect page: show the board's secure link that
startup/run-phone-vu-tunnel.sh publishes, and nothing else.
"""

import json
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'assets' / 'reconnect.js'
PAGE = ROOT / 'assets' / 'reconnect.html'

# Loads reconnect.js with a fake document and fetch, waits for its first check, prints the result.
HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const [scriptPath, body, status] = JSON.parse(process.argv[1]);
const els = {
  '#status': { textContent: 'Waiting for the secure demo link…' },
  '#link': { hidden: true, href: '' },
};
const requested = [];
const sandbox = {
  document: { querySelector: (sel) => els[sel] ?? null },
  fetch: async (url) => {
    requested.push(String(url));
    if (status === 0) throw new TypeError('network down');
    return { ok: status === 200, text: async () => body };
  },
  setInterval: () => 0,
  Date,
};
vm.runInNewContext(fs.readFileSync(scriptPath, 'utf8'), sandbox);
setTimeout(() => {
  console.log(JSON.stringify({
    status: els['#status'].textContent,
    linkHidden: els['#link'].hidden,
    href: els['#link'].href,
    requested,
  }));
}, 50);
"""


def run_page(body='', status=200):
    out = subprocess.run(
        ['node', '-e', HARNESS, json.dumps([str(SCRIPT), body, status])],
        capture_output=True, text=True, timeout=10, check=True,
    )
    return json.loads(out.stdout)


class _IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        element_id = dict(attrs).get('id')
        if element_id:
            self.ids.add(element_id)


@unittest.skipIf(shutil.which('node') is None, 'Node.js is required to run the reconnect page script')
class ReconnectPageTests(unittest.TestCase):
    def test_reads_the_link_published_by_the_tunnel_script(self):
        result = run_page('https://calm-room-42.trycloudflare.com\n')
        self.assertTrue(result['requested'][0].startswith('demo-url.txt?t='))
        self.assertFalse(result['linkHidden'])
        self.assertEqual(result['href'], 'https://calm-room-42.trycloudflare.com')
        self.assertIn('Ready', result['status'])

    def test_accepts_the_hussh_domain(self):
        result = run_page('https://live.hussh.tech')
        self.assertFalse(result['linkHidden'])
        self.assertEqual(result['href'], 'https://live.hussh.tech')

    def test_rejects_addresses_outside_the_allow_list(self):
        for bad in ['https://evil.example.com', 'http://calm-room-42.trycloudflare.com',
                    'javascript:alert(1)', 'https://hussh.tech.evil.com']:
            with self.subTest(url=bad):
                result = run_page(bad)
                self.assertTrue(result['linkHidden'])
                self.assertEqual(result['href'], '')

    def test_waits_while_the_link_is_not_published(self):
        for status in (404, 0):
            with self.subTest(status=status):
                result = run_page(status=status)
                self.assertTrue(result['linkHidden'])
                self.assertIn('Board is starting', result['status'])

    def test_script_uses_elements_that_exist_on_the_page(self):
        collector = _IdCollector()
        collector.feed(PAGE.read_text(encoding='utf-8'))
        self.assertTrue({'status', 'link'} <= collector.ids)


if __name__ == '__main__':
    unittest.main()
