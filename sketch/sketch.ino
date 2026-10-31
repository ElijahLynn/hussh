#include <Arduino_RouterBridge.h>
#include <Arduino_LED_Matrix.h>
Arduino_LED_Matrix matrix;
volatile int level = 0;
volatile unsigned long lastInput = 0;
float smoothLevel = 0, peak = 0;
unsigned long peakAt = 0;
unsigned long loudAt = 0;
bool loudActive = false, loudArmed = true;
unsigned long meterAt = 0;
bool alertHasRun = false;
int alert_state() { return loudActive ? 1 : 0; }
// Complete 3x5 HUSH letters: 12 columns total, with a blank right margin.
const uint8_t loudGlyphs[4][5] = {
  {5,5,7,5,5}, {5,5,5,5,2}, {7,4,7,1,7}, {5,5,7,5,5}
};
void set_level(int value) { level = constrain(value, 0, 100); lastInput = millis(); }
const int rgbPins[] = {LED3_R, LED3_G, LED3_B, LED4_R, LED4_G, LED4_B};
int rgbMask() {
  int mask = 0;
  for (int i=0; i<6; i++) if (digitalRead(rgbPins[i]) == LOW) mask |= (1 << i);
  return mask;
}
void updateRGB(int value, bool connected) {
  // Both RGB LEDs: green <45, yellow 45-74, red >=75. Active-low outputs.
  bool red = connected && value >= 45;
  bool green = connected && value < 75;
  for (int offset=0; offset<6; offset+=3) {
    digitalWrite(rgbPins[offset], red ? LOW : HIGH);
    digitalWrite(rgbPins[offset+1], green ? LOW : HIGH);
    digitalWrite(rgbPins[offset+2], HIGH);
  }
}
void setup() {
  for (int pin : rgbPins) { pinMode(pin, OUTPUT); digitalWrite(pin, HIGH); }
  matrix.begin();
  matrix.setGrayscaleBits(3);
  Bridge.begin();
  Bridge.provide("set_level", set_level);
  Bridge.provide("rgb_mask", rgbMask);
  Bridge.provide("alert_state", alert_state);
}
void loop() {
  unsigned long now = millis();
  int target = now - lastInput < 1500 ? level : 0;
  smoothLevel += (target - smoothLevel) * (target > smoothLevel ? 0.7f : 0.14f);
  if (loudActive && now - loudAt >= 4000) { loudActive = false; meterAt = now; }
  loudArmed = !alertHasRun || (!loudActive && now - meterAt >= 3000);
  if (!loudActive && loudArmed && smoothLevel >= 75 && now - lastInput < 1500) {
    loudActive = true; loudArmed = false; loudAt = now; alertHasRun = true;
  }
  if (loudActive) {
    bool flashOn = ((now - loudAt) / 400) % 2 == 0;
    updateRGB(100, flashOn);
    uint8_t warning[8 * 13] = {};
    const int widths[] = {3,3,3,3};
    const int starts[] = {0,3,6,9};
    if (flashOn) for (int letter=0; letter<4; letter++)
      for (int y=0; y<5; y++) for (int x=0; x<widths[letter]; x++) {
        int col = starts[letter] + x;
        if (loudGlyphs[letter][y] & (1 << (widths[letter]-1-x)))
          warning[(y+1)*13+col] = 7;
      }
    matrix.draw(warning);
    delay(40);
    return;
  }
  updateRGB((int)smoothLevel, now - lastInput < 1500);
  float width = smoothLevel * 13 / 100;
  if (width >= peak) { peak = width; peakAt = now; }
  else if (now - peakAt > 650) peak = max(width, peak - 0.12f);
  uint8_t pixels[8 * 13] = {};
  int filled = constrain((int)(width + 0.5f), 0, 13);
  int peakCol = constrain((int)(peak - 0.01f), 0, 12);
  for (int y=1; y<7; y++) for (int x=0; x<13; x++) {
    if (x < filled) pixels[y*13+x] = 7;
    else if (peak > 0.5f && x == peakCol) pixels[y*13+x] = 3;
  }
  if (now - lastInput >= 1500) pixels[(now/180)%13] = 2;
  matrix.draw(pixels);
  delay(40);
}
