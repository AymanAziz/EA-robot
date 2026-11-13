#define main behavior_main
#include "policy.cpp"
#undef main
#include <iostream>
#include <sstream>
#include <string>
int main(){
  MtfContext c;c.Reset();std::string line;
  std::cout<<"decision_server,h4_count,h4_available_server,ema50,h4_ready,h4_direction,h1_open_server,h1_ready,direction,atr,level,buffer\n";
  while(std::getline(std::cin,line)){
    QuoteBar b={};char comma;std::istringstream in(line);
    in>>b.server>>comma>>b.bo>>comma>>b.bh>>comma>>b.bl>>comma>>b.bc>>comma>>b.ao>>comma>>b.ah>>comma>>b.al>>comma>>b.ac>>comma>>b.ticks;
    if(!in || !c.Push(b)) return 2;
    int dir=0;double atr=0,d=0,spread=0,nom=0,level=0,buffer=0;
    bool available=c.Signal(dir,atr,d,spread,nom,level,buffer);
    std::printf("%ld,%d,%ld,%.12f,%d,%d,%ld,%d,%d,%.12f,%.12f,%.12f\n", b.server+300,c.HigherCount(),c.HigherClose(),c.Average(),c.TrendReady(b.server+300),c.Trend(b.server+300),c.LastHour(),available,dir,atr,level,buffer);
  }
}
