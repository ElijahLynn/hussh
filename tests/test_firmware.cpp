#include "../sketch/sketch.ino"
#include <cassert>
#include <iostream>
int main() {
  setup();
  set_level(95); loop(); loop();
  assert(loudActive);
  const uint8_t expected[4][5]={{5,5,7,5,5},{5,5,5,5,2},{7,4,7,1,7},{5,5,7,5,5}};
  for(int letter=0;letter<4;letter++) for(int y=0;y<5;y++) for(int x=0;x<3;x++)
    assert(bool(lastFrame[(y+1)*13+letter*3+x])==bool(expected[letter][y]&(4>>x)));
  for(int y=0;y<8;y++) assert(lastFrame[y*13+12]==0);
  auto started=loudAt;
  while(clockMs-started<4000){set_level(95);loop();}
  set_level(95);loop();assert(!loudActive);
  auto stopped=meterAt;
  while(clockMs-stopped<3000){assert(!loudActive);set_level(95);loop();}
  set_level(95);loop();assert(loudActive);
  std::cout<<"PASS: HUSH fits; four-second warning, three-second meter, sustained sound retriggers.\n";
}
