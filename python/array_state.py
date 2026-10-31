import math
import threading
import time

class MicrophoneArray:
    def __init__(self, clock=time.monotonic, stale_after=2.0):
        self.clock = clock
        self.stale_after = stale_after
        self.sources = {}
        self.names = {}
        self.lock = threading.RLock()

    def identify(self, client, name):
        if not isinstance(name, str):
            return
        name = ''.join(c for c in name if c.isprintable()).strip()[:32]
        with self.lock:
            self.names[client] = name or 'Mic ' + str(client)[-4:]

    def update(self, client, data):
        if not isinstance(data, dict):
            return False
        try:
            value = float(data.get('level'))
        except (TypeError, ValueError):
            return False
        if not math.isfinite(value):
            return False
        value = max(0, min(100, value))
        now = self.clock()
        with self.lock:
            if 'name' in data:
                self.identify(client, data['name'])
            previous = self.sources.get(client)
            if previous and now - previous['seen'] <= self.stale_after:
                dt = max(0, now - previous['seen'])
                alpha = 1 - math.exp(-dt / 0.12)
                smoothed = previous['level'] + alpha * (value - previous['level'])
            else:
                smoothed = value
            self.sources[client] = {'level': smoothed, 'seen': now}
        return True

    def stop(self, client):
        with self.lock:
            self.sources.pop(client, None)

    def disconnect(self, client):
        with self.lock:
            self.stop(client)
            self.names.pop(client, None)

    def snapshot(self):
        now = self.clock()
        with self.lock:
            for client in list(self.sources):
                if now - self.sources[client]['seen'] > self.stale_after:
                    del self.sources[client]
            microphones = [
                {'id': client, 'name': self.names.get(client, 'Mic ' + str(client)[-4:]),
                 'level': round(source['level'])}
                for client, source in self.sources.items()
            ]
        loudest = max(microphones, key=lambda source: source['level'], default=None)
        return {'microphones': microphones, 'count': len(microphones),
                'level': loudest['level'] if loudest else 0, 'loudest': loudest}
