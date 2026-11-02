"""
Huush — Distributed Microphone Array State & Arbitration Engine

This module coordinates multi-device acoustic telemetry:
- Ingestion: Receives 10 Hz normalized loudness readings (0–100) from connected phones.
- Exponential Smoothing: Applies a 120ms alpha filter to eliminate transient microphone jitter.
- Source Arbitration: Identifies the loudest contributing location to drive board visualizations.
- Memory & Stale Eviction: Automatically purges silent or disconnected devices after 2 seconds.
- Security: Enforces participant caps (64 max) and optional HMAC room join authentication.
"""

import hmac
import math
import threading
import time


class MicrophoneArray:
    """
    Thread-safe acoustic state manager aggregating distributed microphone telemetry.
    """

    def __init__(self, clock=time.monotonic, stale_after=2.0, name_ttl=300.0, max_clients=64, join_key=None):
        """
        Initialize the array state manager.

        :param clock: Time function returning monotonic seconds.
        :param stale_after: Seconds of inactivity before an active microphone reading is evicted.
        :param name_ttl: Seconds to retain friendly client names for inactive/viewer devices.
        :param max_clients: Hard ceiling on concurrent active microphone streams.
        :param join_key: Optional secret key string required for write operations.
        """
        self.clock = clock
        self.stale_after = stale_after
        self.name_ttl = name_ttl
        self.max_clients = max_clients
        self.join_key = join_key.strip() if isinstance(join_key, str) and join_key.strip() else None

        self.sources = {}       # client_id -> {'raw': float, 'smoothed': float, 'seen': float}
        self.names = {}         # client_id -> friendly_name
        self.name_seen = {}     # client_id -> timestamp last registered
        self.authorized = set() # Set of authenticated client_ids
        self.lock = threading.RLock()

    def _is_authorized(self, client, provided_key=None):
        """
        Verify if a client is permitted to contribute readings or update identity.
        Uses constant-time comparison to prevent timing side-channel attacks.
        """
        if self.join_key is None:
            return True
        if client in self.authorized:
            return True
        if isinstance(provided_key, str) and hmac.compare_digest(provided_key, self.join_key):
            self.authorized.add(client)
            return True
        return False

    def _prune_stale_locked(self, now):
        """
        Internal prune routine. Must be called with self.lock acquired.
        Removes sources past stale_after threshold and evicts expired names.
        """
        # Evict inactive microphones from active array calculation
        for client in list(self.sources):
            if now - self.sources[client]['seen'] > self.stale_after:
                del self.sources[client]

        # Evict disconnected client names past their time-to-live
        for client in list(self.names):
            if client not in self.sources and now - self.name_seen.get(client, 0) > self.name_ttl:
                del self.names[client]
                self.name_seen.pop(client, None)

    def identify(self, client, name, key=None):
        """
        Register or update a client's friendly microphone label (e.g., 'Kitchen', 'Table 2').
        Sanitizes name to printable ASCII/Unicode characters with a 32-character limit.
        """
        if not isinstance(name, str):
            return

        # Strip unprintable control characters and truncate
        name = ''.join(c for c in name if c.isprintable()).strip()[:32]
        now = self.clock()

        with self.lock:
            if not self._is_authorized(client, key):
                return

            self._prune_stale_locked(now)

            # Prevent unbounded memory growth from disconnected viewer sessions
            name_cap = self.max_clients * 2
            if client not in self.names and len(self.names) >= name_cap:
                inactive = [c for c in self.names if c not in self.sources]
                if not inactive:
                    return
                # Evict oldest inactive record
                oldest = min(inactive, key=lambda c: self.name_seen.get(c, 0))
                del self.names[oldest]
                self.name_seen.pop(oldest, None)

            self.names[client] = name or f"Mic {str(client)[-4:]}"
            self.name_seen[client] = now

    def update(self, client, data):
        """
        Ingest a 10 Hz loudness reading from a client.

        :param client: Unique identifier for the client session (e.g. Socket.IO sid).
        :param data: Dict containing 'level' (0–100), optional 'name', and optional 'key'.
        :return: True if reading was accepted, False otherwise.
        """
        if not isinstance(data, dict):
            return False

        level = data.get('level')
        if not isinstance(level, (int, float)) or math.isnan(level) or math.isinf(level):
            return False

        clamped = max(0.0, min(100.0, float(level)))
        now = self.clock()

        with self.lock:
            if not self._is_authorized(client, data.get('key')):
                return False

            self._prune_stale_locked(now)

            # Enforce maximum concurrent active microphones
            if client not in self.sources and len(self.sources) >= self.max_clients:
                return False

            if client in self.sources:
                prev = self.sources[client]
                dt = max(0.0, now - prev['seen'])
                # 120ms exponential moving average filter
                alpha = 1.0 - math.exp(-dt / 0.12) if dt < 1.0 else 1.0
                smoothed = prev['smoothed'] + (clamped - prev['smoothed']) * alpha
            else:
                smoothed = clamped

            self.sources[client] = {
                'raw': clamped,
                'smoothed': smoothed,
                'seen': now
            }

            if 'name' in data:
                self.identify(client, data['name'], data.get('key'))

            return True

    def stop(self, client):
        """
        Stops active microphone audio streaming for a client without forgetting their session name.
        """
        with self.lock:
            self.sources.pop(client, None)

    def disconnect(self, client):
        """
        Handles full client socket disconnect: removes active reading, names, and auth session.
        """
        with self.lock:
            self.sources.pop(client, None)
            self.names.pop(client, None)
            self.name_seen.pop(client, None)
            self.authorized.discard(client)

    def remove(self, client):
        """Alias for disconnect."""
        self.disconnect(client)

    def snapshot(self):
        """
        Compile current aggregated array snapshot for distribution to clients and hardware.

        :return: Dict with:
            - 'level': Overall array loudness (0–100 integer)
            - 'count': Number of active contributing microphones
            - 'loudest': Dict with 'id', 'name', and 'level' of the loudest source
            - 'microphones': Sorted list of all active microphones by volume (descending)
        """
        now = self.clock()
        with self.lock:
            self._prune_stale_locked(now)

            if not self.sources:
                return {
                    'level': 0,
                    'count': 0,
                    'microphones': [],
                    'loudest': None
                }

            entries = []
            for client, item in self.sources.items():
                entries.append({
                    'id': client,
                    'name': self.names.get(client, f"Mic {str(client)[-4:]}"),
                    'level': int(round(item['smoothed']))
                })

            # Sort descending: loudest contributor appears first
            entries.sort(key=lambda item: item['level'], reverse=True)
            loudest = entries[0] if entries else None

            return {
                'level': loudest['level'] if loudest else 0,
                'count': len(entries),
                'microphones': entries,
                'loudest': loudest
            }

    def state(self):
        """Alias for snapshot."""
        return self.snapshot()
