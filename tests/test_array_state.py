import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from array_state import MicrophoneArray

class ArrayTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.array = MicrophoneArray(clock=lambda: self.now)

    def test_quiet_sender_cannot_override_louder_source(self):
        self.array.update('back', {'level': 90, 'name': 'Back table'})
        self.array.update('front', {'level': 10, 'name': 'Front table'})
        self.assertEqual(self.array.snapshot()['level'], 90)
        self.assertEqual(self.array.snapshot()['loudest']['name'], 'Back table')
        self.array.stop('back')
        self.assertEqual(self.array.snapshot()['level'], 10)

    def test_expiry_removes_only_inactive_microphones(self):
        self.array.update('old', {'level': 95})
        self.now = 1.5
        self.array.update('active', {'level': 35})
        self.now = 2.1
        result = self.array.snapshot()
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['level'], 35)
        self.now = 4
        self.assertEqual(self.array.snapshot()['level'], 0)

    def test_viewer_and_disconnect(self):
        self.array.identify('viewer', 'Observer')
        self.assertEqual(self.array.snapshot()['count'], 0)
        self.array.update('mic', {'level': 60})
        self.array.disconnect('mic')
        self.assertEqual(self.array.snapshot()['count'], 0)

    def test_invalid_levels_and_clamping(self):
        for value in [math.nan, math.inf, None, 'bad']:
            self.assertFalse(self.array.update('bad', {'level': value}))
        self.assertFalse(self.array.update('bad', None))
        self.array.update('max', {'level': 200})
        self.assertEqual(self.array.snapshot()['level'], 100)

    def test_smoothing_and_name_sanitization(self):
        self.array.update('mic', {'level': 0, 'name': 'A\n' * 100})
        self.now = .1
        self.array.update('mic', {'level': 100})
        level = self.array.snapshot()['level']
        self.assertGreater(level, 0)
        self.assertLess(level, 100)
        self.assertEqual(len(self.array.snapshot()['loudest']['name']), 32)

if __name__ == '__main__':
    unittest.main()
