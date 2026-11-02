/**
 * Huush — Distributed Sound-Awareness Web Client
 * 
 * Architecture Overview:
 * 1. Audio Capture: Samples local microphone RMS level at 10 Hz via Web Audio API.
 * 2. Privacy Guarantee: Zero raw audio leaves the browser; only normalized 0–100 levels are transmitted.
 * 3. Bidirectional Sync: Receives aggregated array state from Arduino UNO Q / Python backend over Socket.IO.
 * 4. SVG Visualizations: Real-time 13-segment meter, live sparkline history, and multi-mic comparative table.
 */

// Initialize Socket.IO connection with standard transport fallbacks
const socket = io({ transports: ['websocket', 'polling'] });

// DOM query helper and key element references
const $ = (selector) => document.querySelector(selector);
const statusEl = $('#status');
const button = $('#start');
const gain = $('#gain');
const nameInput = $('#micName');

// Generate 13 visual meter segments matching the Arduino UNO Q 13-column matrix
const segments = Array.from({ length: 13 }, () => {
  const el = document.createElement('div');
  el.className = 'seg';
  $('#meter').append(el);
  return el;
});

// Runtime audio capture & rendering state
let stream = null;
let ctx = null;
let sampleTimer = null;
let wake = null;
let active = false;
let pending = false;
let pendingAt = 0;
let lastStateAt = 0;
let lastPaint = 0;
let displayLevel = 0;
let dbHistory = [];
let state = {
  level: 0,
  count: 0,
  microphones: [],
  loudest: null,
  alert: false,
  board_ok: false
};

// Map of active microphone table rows keyed by socket ID
const rows = new Map();
let lastNumbers = 0;

/**
 * Updates an element's text content only if the value has changed,
 * preventing unnecessary DOM repaints.
 */
function text(el, value) {
  if (el.textContent !== String(value)) {
    el.textContent = value;
  }
}

/**
 * HistoryChart — Renders a 30-second rolling peak history sparkline
 * using SVG paths with quiet (green), moderate (yellow), and loud (red) bins.
 */
class HistoryChart {
  constructor(label) {
    this.label = label;
    // 120 buckets = 30 seconds at 250ms resolution
    this.values = Array(120).fill(null);
    this.pending = null;

    this.el = document.createElement('div');
    this.el.className = 'history';

    const caption = document.createElement('div');
    caption.className = 'history-caption';
    caption.textContent = `${label} · last 30 seconds`;

    const ns = 'http://www.w3.org/2000/svg';
    this.svg = document.createElementNS(ns, 'svg');
    this.svg.setAttribute('viewBox', '0 0 240 52');
    this.svg.setAttribute('preserveAspectRatio', 'none');
    this.svg.setAttribute('role', 'img');

    // Horizontal dashed threshold guide lines (25%, 50%, 75%)
    for (const y of [13, 26, 39]) {
      const line = document.createElementNS(ns, 'line');
      line.setAttribute('x1', 0);
      line.setAttribute('x2', 240);
      line.setAttribute('y1', y);
      line.setAttribute('y2', y);
      line.setAttribute('stroke', 'var(--chart-grid)');
      line.setAttribute('stroke-dasharray', '2 3');
      this.svg.append(line);
    }

    // Path elements for three amplitude zones: quiet, moderate, loud
    this.paths = ['var(--quiet)', 'var(--moderate)', 'var(--loud)'].map((color) => {
      const path = document.createElementNS(ns, 'path');
      path.setAttribute('fill', color);
      this.svg.append(path);
      return path;
    });

    const axis = document.createElement('div');
    axis.className = 'history-axis';
    const before = document.createElement('span');
    const after = document.createElement('span');
    before.textContent = '30s ago';
    after.textContent = 'now · 0–100';
    axis.append(before, after);

    this.el.append(caption, this.svg, axis);
    this.draw();
  }

  /** Accumulates the peak loudness sample within the current quarter-second bucket */
  observe(value) {
    if (Number.isFinite(value)) {
      this.pending = Math.max(this.pending ?? 0, Math.max(0, Math.min(100, value)));
    }
  }

  /** Advances the 30-second rolling window by one quarter-second step */
  commit(live) {
    this.values.shift();
    this.values.push(live ? this.pending : null);
    this.pending = null;
    this.draw();
  }

  /** Reconstructs the SVG path geometry for all colored segments */
  draw() {
    const paths = ['', '', ''];
    this.values.forEach((v, i) => {
      if (v === null) return;
      const height = Math.max(1, v * 0.52);
      const group = v >= 75 ? 2 : v >= 45 ? 1 : 0;
      paths[group] += `M${i * 2},${52 - height}h1.5v${height}h-1.5z`;
    });

    this.paths.forEach((path, i) => {
      if (path.getAttribute('d') !== paths[i]) {
        path.setAttribute('d', paths[i]);
      }
    });

    const latest = this.values[this.values.length - 1];
    this.svg.setAttribute(
      'aria-label',
      `${this.label}, last 30 seconds${
        latest === null ? ', no recent sample' : `, latest ${Math.round(latest)} out of 100`
      }`
    );
  }
}

// Instantiate and attach global room acoustic history sparkline
const roomHistory = new HistoryChart('Room history');
$('#roomHistory').append(roomHistory.el);

// Commit history buckets every 250ms (4 Hz)
setInterval(() => {
  const live = socket.connected && Date.now() - lastStateAt < 2500;
  roomHistory.commit(live);
  for (const row of rows.values()) {
    row.history.commit(live);
  }
}, 250);

/** LocalStorage persistence helpers */
function saved(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function save(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

// Parse and store optional URL room key, then cleanse query string from address bar
const urlParams = new URLSearchParams(location.search);
if (urlParams.has('key')) {
  try {
    sessionStorage.setItem('vu-room-key', urlParams.get('key'));
  } catch {}
  urlParams.delete('key');
  history.replaceState(
    null,
    '',
    location.pathname + (urlParams.toString() ? `?${urlParams}` : '') + location.hash
  );
}

const roomKey = (() => {
  try {
    return sessionStorage.getItem('vu-room-key') || '';
  } catch {
    return '';
  }
})();

// Restore user preferences
nameInput.value = saved('vu-mic-name', '');
gain.value = saved('vu-mic-gain', '0');

/** Updates gain slider text and accessibility attributes */
function updateGain() {
  const txt = `${+gain.value >= 0 ? '+' : ''}${gain.value} dB`;
  $('#gainLabel').textContent = txt;
  gain.setAttribute('aria-valuetext', txt);
  save('vu-mic-gain', gain.value);
}
gain.oninput = updateGain;
updateGain();

/** Identifies client with the server array */
function identify() {
  save('vu-mic-name', nameInput.value);
  if (socket.connected) {
    socket.emit(
      'identify',
      roomKey ? { name: nameInput.value, key: roomKey } : { name: nameInput.value }
    );
  }
}
nameInput.onchange = identify;

// Socket.IO lifecycle event handlers
socket.on('connect', () => {
  pending = false;
  identify();
  statusEl.textContent = 'Connected. Waiting for array readings…';
});

socket.on('disconnect', () => {
  pending = false;
  statusEl.textContent = 'Connection lost. Reconnecting…';
});

socket.on('ack', () => {
  pending = false;
});

socket.on('array_state', (data) => {
  state = data;
  lastStateAt = Date.now();
  roomHistory.observe(data.level);
  for (const mic of data.microphones) {
    const row = rows.get(mic.id);
    if (row) {
      row.history.observe(mic.level);
    }
  }
});

/** Requests Screen Wake Lock to prevent mobile devices from sleeping during monitoring */
async function keepAwake() {
  try {
    wake = await navigator.wakeLock.request('screen');
  } catch {}
}

/** Shuts down microphone capture stream and resets UI controls */
function stop() {
  active = false;
  pending = false;
  clearInterval(sampleTimer);
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  ctx?.close();
  ctx = null;
  wake?.release();
  button.textContent = 'Start microphone';
  button.setAttribute('aria-pressed', 'false');
  $('#calibrate').disabled = true;
  dbHistory = [];
  if (socket.connected) {
    socket.emit('stop_microphone', {});
  }
}

/** Microphone toggle handler: requests raw uncompressed audio stream */
button.onclick = async () => {
  if (active) {
    stop();
    return;
  }
  button.disabled = true;
  $('#micError').hidden = true;

  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw Error('Microphone requires HTTPS. Open the secure demo link.');
    }

    // Disable browser DSP audio processing to get true ambient acoustic levels
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: false
      }
    });

    // Initialize Web Audio Context and Fast Fourier Transform Analyser
    ctx = new AudioContext();
    await ctx.resume();
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    ctx.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);

    active = true;
    pending = false;
    dbHistory = [];
    button.textContent = 'Stop microphone';
    button.setAttribute('aria-pressed', 'true');
    $('#calibrate').disabled = false;
    identify();
    await keepAwake();

    // 10 Hz sampling loop (every 100ms)
    sampleTimer = setInterval(() => {
      analyser.getFloatTimeDomainData(samples);

      // Compute Root Mean Square (RMS) amplitude
      let sum = 0;
      for (const s of samples) {
        sum += s * s;
      }
      const db = 20 * Math.log10(Math.max(1e-6, Math.sqrt(sum / samples.length)));
      dbHistory.push(db);
      if (dbHistory.length > 12) {
        dbHistory.shift();
      }

      // Map dB to 0–100 scale based on calibrated noise floor
      const level = Math.max(0, Math.min(100, ((db + 60 + Number(gain.value)) / 60) * 100));

      // If disconnected from backend board, update local display meter directly
      if (!socket.connected) {
        displayLevel += (level - displayLevel) * 0.65;
        roomHistory.observe(level);
      }

      // Emit level using volatile transport (drops stale packets on high network jitter)
      if (socket.connected && (!pending || Date.now() - pendingAt > 1000)) {
        pending = true;
        pendingAt = Date.now();
        socket.volatile.emit(
          'level',
          roomKey
            ? { level, name: nameInput.value, key: roomKey }
            : { level, name: nameInput.value }
        );
      }
    }, 100);
  } catch (e) {
    stop();
    $('#micError').textContent = e.message;
    $('#micError').hidden = false;
  } finally {
    button.disabled = false;
  }
};

/** Ambient baseline auto-calibration helper */
$('#calibrate').onclick = () => {
  if (dbHistory.length < 5) {
    $('#calibrationStatus').textContent = 'Let the microphone listen for a second, then try again.';
    return;
  }
  const baseline = dbHistory.reduce((a, b) => a + b, 0) / dbHistory.length;
  gain.value = Math.max(-35, Math.min(40, Math.round(-42 - baseline)));
  updateGain();
  $('#calibrationStatus').textContent =
    'Background sensitivity adjusted. Compare phones and fine-tune with the slider if needed.';
};

/**
 * 20 Hz UI Render Loop:
 * - Interpolates display loudness smoothly
 * - Lights up the 13 matrix segment bars
 * - Updates the leaderboard of active microphones
 */
function paint() {
  const now = Date.now();
  if (now - lastPaint < 100) return;
  lastPaint = now;

  const live = (socket.connected && now - lastStateAt < 2500) || (!socket.connected && active);
  const effectiveLevel = socket.connected ? state.level : (active ? Math.round(displayLevel) : 0);

  // Exponential moving average filter for smooth meter animation
  displayLevel += ((socket.connected ? state.level : displayLevel) - displayLevel) * 0.65;
  const reading = Math.round(displayLevel);

  // Accessible meter attribute update
  $('#meter').setAttribute('aria-valuenow', reading);

  // Render 13 matrix LED segments matching the physical board
  segments.forEach((el, i) => {
    const next =
      'seg' + (live && i < Math.round((reading * 13) / 100) ? ' on' + (i > 9 ? ' hot' : '') : '');
    if (el.className !== next) {
      el.className = next;
    }
  });

  const updateNumbers = now - lastNumbers >= 250;
  if (updateNumbers) {
    lastNumbers = now;
    text($('#reading'), live ? reading : '—');
  }

  // Toggle "LOUD / HUSH" alert overlay when threshold is exceeded
  $('#loud').hidden = !(live && state.alert);
  $('#meter').hidden = live && state.alert;

  text(
    $('#arrayCount'),
    live
      ? `${state.count} active microphone${state.count === 1 ? '' : 's'}`
      : 'Waiting for connection'
  );
  text(
    $('#location'),
    live && state.loudest
      ? `Loudest location: ${state.loudest.name}`
      : 'Start a microphone to join the array'
  );

  const mine = state.microphones.find((m) => m.id === socket.id);
  if (updateNumbers) {
    text(
      $('#myLevel'),
      active
        ? mine
          ? `Your microphone: ${mine.level}/100`
          : `Your microphone: ${reading}/100 (local meter)`
        : 'Viewing the array · your microphone is off'
    );
  }

  text(
    statusEl,
    active && !socket.connected
      ? 'Microphone active (Standalone preview mode · Arduino offline)'
      : !socket.connected
      ? 'Connecting to backend…'
      : !live
      ? 'Waiting for live readings…'
      : !state.board_ok
      ? 'Phones connected · Arduino is reconnecting…'
      : `Live → Arduino · ${active ? 'Your microphone is contributing' : 'Viewer mode'}`
  );

  // Synchronize dynamic table rows for all participating microphones
  const ids = new Set();
  for (const mic of live ? state.microphones : []) {
    ids.add(mic.id);
    let row = rows.get(mic.id);
    if (!row) {
      const el = document.createElement('div');
      el.className = 'source';
      const label = document.createElement('span');
      const value = document.createElement('b');
      const track = document.createElement('div');
      const fill = document.createElement('div');
      track.className = 'track';
      fill.className = 'fill';
      track.append(fill);

      const history = new HistoryChart('Microphone history');
      history.observe(mic.level);
      el.append(label, value, track, history.el);
      $('#sources').append(el);
      row = { el, label, value, fill, history };
      rows.set(mic.id, row);
    }

    text(row.label, mic.name + (mic.id === socket.id ? ' (you)' : ''));
    if (updateNumbers) {
      text(row.value, mic.level);
    }
    row.fill.style.width = `${mic.level}%`;
    row.el.classList.toggle('leading', state.loudest?.id === mic.id);
  }

  // Remove rows for disconnected or stale microphones
  for (const [id, row] of rows) {
    if (!ids.has(id)) {
      row.el.remove();
      rows.delete(id);
    }
  }

  $('#empty').hidden = live && state.count > 0;
}

// 50ms UI update timer
setInterval(paint, 50);

// Re-acquire screen wake lock if tab becomes visible again
document.addEventListener('visibilitychange', () => {
  if (active && document.visibilityState === 'visible') {
    keepAwake();
  }
});
