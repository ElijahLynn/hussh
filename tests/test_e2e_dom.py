import urllib.request
import re
from html.parser import HTMLParser
import unittest

BASE_URL = 'http://127.0.0.1:8765'

class DOMParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []
        self.current_tag = None
        self.text_content = []
        self.in_script = False
        self.inline_scripts = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        self.elements.append({'tag': tag, 'attrs': attr_dict})
        for k in attr_dict:
            if k.lower().startswith('on'):
                raise AssertionError(f'CSP Violation: Inline handler {k} on <{tag}>')
        if tag.lower() == 'script':
            self.in_script = True
            if 'src' not in attr_dict:
                self.inline_scripts.append(tag)

    def handle_endtag(self, tag):
        if tag.lower() == 'script':
            self.in_script = False

    def handle_data(self, data):
        clean = data.strip()
        if clean:
            self.text_content.append(clean)
        if self.in_script and clean:
            self.inline_scripts.append(clean)


class EndToEndWebTests(unittest.TestCase):
    def fetch_dom(self, path):
        req = urllib.request.Request(f'{BASE_URL}/{path}', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            html = resp.read().decode('utf-8')
        parser = DOMParser()
        parser.feed(html)
        return html, parser

    def test_e2e_index_dashboard(self):
        html, dom = self.fetch_dom('index.html')
        
        # 1. Branding & Title
        self.assertIn('<title>Huush · Shared sound awareness</title>', html)
        h1_elems = [e for e in dom.elements if e['tag'] == 'h1']
        self.assertEqual(len(h1_elems), 1)
        self.assertIn('Huush', ' '.join(dom.text_content))

        # 2. Team Credits
        self.assertIn('Team Huush', ' '.join(dom.text_content))

        # 3. Accessibility Attributes
        meter = next(e for e in dom.elements if e['attrs'].get('id') == 'meter')
        self.assertEqual(meter['attrs'].get('role'), 'meter')
        self.assertEqual(meter['attrs'].get('aria-label'), 'Room sound level')
        self.assertEqual(meter['attrs'].get('aria-valuemin'), '0')
        self.assertEqual(meter['attrs'].get('aria-valuemax'), '100')

        btn = next(e for e in dom.elements if e['attrs'].get('id') == 'start')
        self.assertEqual(btn['attrs'].get('aria-pressed'), 'false')

        gain = next(e for e in dom.elements if e['attrs'].get('id') == 'gain')
        self.assertEqual(gain['attrs'].get('aria-valuetext'), '+0 dB')

        # 4. Strict CSP (Zero Inline Scripts)
        self.assertEqual(dom.inline_scripts, [], 'Zero inline scripts required for CSP A+ rating')

    def test_e2e_simulator_preview(self):
        html, dom = self.fetch_dom('preview.html')
        self.assertIn('<title>Huush · Distributed Sound-Awareness Array</title>', html)
        self.assertIn('Team Huush', ' '.join(dom.text_content))
        self.assertEqual(dom.inline_scripts, [], 'Zero inline scripts on preview page')


if __name__ == '__main__':
    unittest.main()
