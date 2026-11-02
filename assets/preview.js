/**
 * Huush — Interactive Web Preview & Multi-Phone Simulator
 * 
 * Provides an in-browser sandbox for demonstrating and testing the Huush
 * distributed microphone array without requiring physical phones or an Arduino.
 * 
 * Features:
 * - Dual virtual microphones (Phone 1 & Phone 2) with independent volume sliders
 * - Real-time arbitration: demonstrates how the louder source takes leadership
 * - Hardware simulation: 13-segment blue LED matrix and dual RGB status indicators
 * - HUSH alert triggers when sustained noise crosses threshold (>=75)
 */

// Generate 13 visual matrix segments matching the Arduino UNO Q hardware
const segments = Array.from({ length: 13 }, () => {
  const el = document.createElement('div');
  el.className = 'seg';
  document.querySelector('#meter').append(el);
  return el;
});

// Dual virtual phone input state
let p1 = { active: false, level: 25, name: 'Phone 1 (Stage)' };
let p2 = { active: false, level: 40, name: 'Phone 2 (Audience)' };

// Hardware alert and rendering timer state
let alertActive = false;
let alertUntil = 0;
let alertCooldownUntil = 0;
let displayLevel = 0;

/** Binds UI slider and checkbox controls to simulator state */
function setupControls() {
  const p1Check = document.querySelector('#p1Active');
  const p1Slider = document.querySelector('#p1Slider');
  const p1Val = document.querySelector('#p1Val');

  const p2Check = document.querySelector('#p2Active');
  const p2Slider = document.querySelector('#p2Slider');
  const p2Val = document.querySelector('#p2Val');

  p1Check.onchange = () => {
    p1.active = p1Check.checked;
    p1Slider.disabled = !p1.active;
  };
  p1Slider.oninput = () => {
    p1.level = Number(p1Slider.value);
    p1Val.textContent = p1.level;
    p1Slider.setAttribute('aria-valuetext', `${p1.level} out of 100`);
  };

  p2Check.onchange = () => {
    p2.active = p2Check.checked;
    p2Slider.disabled = !p2.active;
  };
  p2Slider.oninput = () => {
    p2.level = Number(p2Slider.value);
    p2Val.textContent = p2.level;
    p2Slider.setAttribute('aria-valuetext', `${p2.level} out of 100`);
  };
}

/** Updates dual RGB status LED colors based on volume tier */
function updateLEDs(level, active) {
  const led1 = document.querySelector('#led1');
  const led2 = document.querySelector('#led2');

  if (!active || level === 0) {
    led1.className = 'led';
    led2.className = 'led';
    return;
  }

  // Color mapping: Green <45, Yellow 45-74, Red >=75
  const color = level >= 75 ? 'red' : level >= 45 ? 'yellow' : 'green';
  led1.className = `led ${color}`;
  led2.className = `led ${color}`;
}

/**
 * 20 Hz Simulation Loop (every 50ms):
 * - Evaluates multi-source loudness arbitration
 * - Simulates physical Arduino smoothing and HUSH alert state machine
 * - Updates DOM matrix segments, text readouts, and RGB LEDs
 */
function tick() {
  const now = Date.now();
  const activeMics = [];
  if (p1.active) activeMics.push(p1);
  if (p2.active) activeMics.push(p2);

  let targetLevel = 0;
  let loudest = null;

  if (activeMics.length > 0) {
    // Array arbitration: highest active level takes leadership
    activeMics.sort((a, b) => b.level - a.level);
    loudest = activeMics[0];
    targetLevel = loudest.level;
  }

  // Smooth interpolation matching the STM32 firmware filter
  displayLevel += (targetLevel - displayLevel) * (targetLevel > displayLevel ? 0.4 : 0.15);
  const rounded = Math.round(displayLevel);

  // HUSH Alert State Machine: triggers at >=75 with a 4s hold and cooldown
  if (rounded >= 75 && !alertActive && now > alertCooldownUntil && activeMics.length > 0) {
    alertActive = true;
    alertUntil = now + 4000;
  }

  if (alertActive && now > alertUntil) {
    alertActive = false;
    alertCooldownUntil = now + 3000;
  }

  // Render LED matrix segments
  segments.forEach((el, i) => {
    const isLit = !alertActive && activeMics.length > 0 && i < Math.round((rounded * 13) / 100);
    const isHot = i > 9;
    el.className = `seg${isLit ? ' on' : ''}${isLit && isHot ? ' hot' : ''}`;
  });

  // Toggle "LOUD / HUSH" alert overlay
  document.querySelector('#meter').hidden = alertActive;
  document.querySelector('#loud').hidden = !alertActive;

  // Update readouts
  document.querySelector('#reading').textContent = activeMics.length > 0 ? rounded : '—';
  document.querySelector('#meter').setAttribute('aria-valuenow', activeMics.length > 0 ? rounded : 0);
  document.querySelector('#arrayCount').textContent =
    activeMics.length > 0
      ? `${activeMics.length} active virtual phone${activeMics.length === 1 ? '' : 's'}`
      : 'No phones connected';
  document.querySelector('#location').textContent = loudest
    ? `Loudest source: ${loudest.name} (${loudest.level}/100)`
    : 'Toggle a phone slider below to simulate noise';

  updateLEDs(rounded, activeMics.length > 0);
}

// Initialize simulator controls and start render loop
setupControls();
setInterval(tick, 50);
