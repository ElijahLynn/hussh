/*
 * Huush — Arduino UNO Q Firmware (STM32 Core)
 * 
 * Hardware Architecture:
 * - Microcontroller: STM32 core on the Arduino UNO Q dual-architecture board.
 * - Linux Bridge: Communicates with host Linux system via Arduino_RouterBridge RPC.
 * - Visual Display: 13-segment blue LED matrix (grayscale, 3-bit depth).
 * - Status LEDs: Dual RGB LEDs (LED3, LED4) for ambient three-zone color signaling.
 * 
 * Control Loop:
 * - 25 Hz execution cadence (40ms tick).
 * - Asymmetric smoothing filter: rapid rise (alpha 0.70) to catch sudden shouts,
 *   gradual decay (alpha 0.14) to maintain visibility.
 * - HUSH Alert State Machine: Triggers a flashing 3x5 "HUSH" text glyph across the matrix
 *   when noise exceeds 75/100, holding for 4 seconds with a 3-second refractory cooldown.
 */

#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>

// Hardware display instance
Arduino_LED_Matrix matrix;

// Shared volatile variables modified by the RPC bridge
volatile int level = 0;
volatile unsigned long lastInput = 0;

// Filter and state machine tracking
float smoothLevel = 0.0f;
float peak = 0.0f;
unsigned long peakAt = 0;
unsigned long loudAt = 0;
bool loudActive = false;
bool loudArmed = true;
unsigned long meterAt = 0;
bool alertHasRun = false;

/** RPC query: returns 1 if HUSH alert is currently displaying, 0 otherwise */
int alert_state() {
  return loudActive ? 1 : 0;
}

/**
 * 3x5 Bitmap Font Glyphs for "HUSH"
 * 4 letters total, 3 columns per letter = 12 columns total on the 13-column matrix.
 * Format: [letter_index][row_index] bitmask
 */
const uint8_t loudGlyphs[4][5] = {
  {5, 5, 7, 5, 5}, // 'H'
  {5, 5, 5, 5, 2}, // 'U'
  {7, 4, 7, 1, 7}, // 'S'
  {5, 5, 7, 5, 5}  // 'H'
};

/**
 * RPC command: Ingests loudness level (0–100) from the Linux bridge daemon.
 */
void set_level(int value) {
  level = constrain(value, 0, 100);
  lastInput = millis();
}

// Active-low RGB status LED pin definitions
const int rgbPins[] = {LED3_R, LED3_G, LED3_B, LED4_R, LED4_G, LED4_B};

/** Reads back the current RGB pin states as a 6-bit diagnostic bitmask */
int rgbMask() {
  int mask = 0;
  for (int i = 0; i < 6; i++) {
    if (digitalRead(rgbPins[i]) == LOW) {
      mask |= (1 << i);
    }
  }
  return mask;
}

/**
 * Updates both RGB status LEDs based on amplitude thresholds:
 * - Green: <45 (quiet conversational noise)
 * - Yellow (Red + Green): 45–74 (moderate noise)
 * - Red: >=75 (loud / alert threshold)
 * Pins are active-low (LOW turns LED on, HIGH turns LED off).
 */
void updateRGB(int value, bool connected) {
  bool red = connected && value >= 45;
  bool green = connected && value < 75;

  for (int offset = 0; offset < 6; offset += 3) {
    digitalWrite(rgbPins[offset], red ? LOW : HIGH);
    digitalWrite(rgbPins[offset + 1], green ? LOW : HIGH);
    digitalWrite(rgbPins[offset + 2], HIGH); // Blue channel unused
  }
}

void setup() {
  // Initialize RGB LED outputs to active-low off state (HIGH)
  for (int pin : rgbPins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, HIGH);
  }

  // Initialize 13-segment LED matrix with 3-bit grayscale support
  matrix.begin();
  matrix.setGrayscaleBits(3);

  // Initialize RouterBridge and export RPC endpoints to the Linux host
  Bridge.begin();
  Bridge.provide("set_level", set_level);
  Bridge.provide("rgb_mask", rgbMask);
  Bridge.provide("alert_state", alert_state);
}

void loop() {
  unsigned long now = millis();

  // If no RPC updates received within 1500ms, gently decay target to 0
  int target = (now - lastInput < 1500) ? level : 0;

  // Asymmetric exponential filter: fast attack (0.70) to catch transients, slow release (0.14)
  smoothLevel += (target - smoothLevel) * (target > smoothLevel ? 0.70f : 0.14f);

  // HUSH Alert State Machine: Hold for 4 seconds after triggering
  if (loudActive && now - loudAt >= 4000) {
    loudActive = false;
    meterAt = now;
  }

  // Refractory cooldown: Must wait 3 seconds after an alert before re-arming
  loudArmed = !alertHasRun || (!loudActive && now - meterAt >= 3000);

  if (!loudActive && loudArmed && smoothLevel >= 75 && (now - lastInput < 1500)) {
    loudActive = true;
    loudArmed = false;
    loudAt = now;
    alertHasRun = true;
  }

  // Maintain peak meter dot with 1200ms hold time
  if (smoothLevel >= peak || now - peakAt >= 1200) {
    peak = smoothLevel;
    peakAt = now;
  }

  // Update dual RGB LEDs
  updateRGB((int)smoothLevel, (now - lastInput < 2000));

  // Render LED matrix
  if (loudActive) {
    // Flash the 3x5 "HUSH" text glyph at 3 Hz
    bool blinkOn = ((now - loudAt) / 333) % 2 == 0;
    if (blinkOn) {
      uint8_t frame[8][12] = {0};
      for (int letter = 0; letter < 4; letter++) {
        for (int r = 0; r < 5; r++) {
          uint8_t rowBits = loudGlyphs[letter][r];
          for (int c = 0; c < 3; c++) {
            if (rowBits & (1 << (2 - c))) {
              frame[r + 1][letter * 3 + c] = 7; // Max brightness
            }
          }
        }
      }
      matrix.renderBitmap(frame, 8, 12);
    } else {
      matrix.clear();
    }
  } else {
    // Render standard volume level bar (0 to 13 segments)
    int litSegments = constrain((int)round((smoothLevel / 100.0f) * 13.0f), 0, 13);
    uint8_t frame[8][12] = {0};

    for (int col = 0; col < 12; col++) {
      if (col < litSegments) {
        for (int row = 0; row < 8; row++) {
          frame[row][col] = (col >= 10) ? 7 : 4; // Top segments glow brighter
        }
      }
    }
    matrix.renderBitmap(frame, 8, 12);
  }

  // 25 Hz control loop cadence (40ms)
  delay(40);
}
