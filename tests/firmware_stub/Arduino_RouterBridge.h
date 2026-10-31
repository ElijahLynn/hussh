#pragma once
#include <algorithm>
#include <cstdint>
using std::max;
#define LOW 0
#define HIGH 1
#define OUTPUT 1
#define LED3_R 0
#define LED3_G 1
#define LED3_B 2
#define LED4_R 3
#define LED4_G 4
#define LED4_B 5
static unsigned long clockMs=100;
static int pins[6];
unsigned long millis(){return clockMs;}
void delay(int ms){clockMs+=ms;}
void pinMode(int,int){}
void digitalWrite(int p,int v){pins[p]=v;}
int digitalRead(int p){return pins[p];}
int constrain(int v,int a,int b){return std::clamp(v,a,b);}
struct {void begin(){} template<class T> void provide(const char*,T){} } Bridge;
