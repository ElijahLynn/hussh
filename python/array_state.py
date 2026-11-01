import hmac
import math
import threading
import time

class MicrophoneArray:
    def __init__(self, clock=time.monotonic, stale_after=2.0, name_ttl=300.0, max_clients=64, join_key=None):
        self.clock = clock
        self.stale_after = stale_after
        self.name_ttl = name_ttl
        self.max_clients = max_clients
        self.join_key = join_key.strip() if isinstance(join_key, str) and join_key.strip() else None
        self.sources = {}
        self.names = {}
        self.name_seen = {}
        self.authorized = set()
        self.lock = threading.RLock()

    def _is_authorized(self, client, provided_key=None):
        if self.join_key is None:
            return True
        if client in self.authorized:
            return True
        if isinstance(provided_key, str) and hmac.compare_digest(provided_key, self.join_key):
            self.authorized.add(client)
            return True
        return False

    def _prune_stale_locked(self, now):
        for client in list(self.sources):
            if now - self.sources[client]['seen'] > self.stale_after:
                del self.sources[client]
        for client in list(self.names):
            if client not in self.sources and now - self.name_seen.get(client, 0) > self.name_ttl:
                del self.names[client]
                self.name_seen.pop(client, None)

    def identify(self, client, name, key=None):
        if not isinstance(name, str):
            return
        name = ''.join(c for c in name if c.isprintable()).strip()[:32]
        now = self.clock()
        with self.lock:
            if not self._is_authorized(client, key):
                return
            self._prune_stale_locked(now)
            name_cap = self.max_clients * 2
            if client not in self.names and len(self.names) >= name_cap:
                inactive = [c for c in self.names if c not in self.sources]
                if not inactive:
                    return
                oldest = min(inactive, key=lambda c: self.name_seen.get(c, 0))
                del self.names[oldest]
                self.name_seen.pop(oldest, None)
            self.names[client] = name or 'Mic ' + str(client)[-4:]
            self.name_seen[client] = now

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
            if not self._is_authorized(client, data.get('key')):
                return False
            self._prune_stale_locked(now)
            if client not in self.sources and len(self.sources) >= self.max_clients:
                return False
            if 'name' in data:
                self.identify(client, data['name'], key=data.get('key'))
            elif client in self.names:
                self.name_seen[client] = now
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
            self.name_seen.pop(client, None)
            self.authorized.discard(client)

    def snapshot(self):
        now = self.clock()
        with self.lock:
            self._prune_stale_locked(now)
            microphones = [
                {'id': client, 'name': self.names.get(client, 'Mic ' + str(client)[-4:]),
                 'level': round(source['level'])}
                for client, source in self.sources.items()
            ]
        loudest = max(microphones, key=lambda source: source['level'], default=None)
        return {'microphones': microphones, 'count': len(microphones),
                'level': loudest['level'] if loudest else 0, 'loudest': loudest}
