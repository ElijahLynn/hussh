#pragma once
#include <cstring>
static uint8_t lastFrame[104];
struct Arduino_LED_Matrix {void begin(){} void setGrayscaleBits(int){} void draw(uint8_t* p){memcpy(lastFrame,p,104);} };
