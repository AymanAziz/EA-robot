#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cfloat>
using datetime=long;
bool MathIsValidNumber(double x){return std::isfinite(x);}
double MathMax(double a,double b){return std::fmax(a,b);}
double MathMin(double a,double b){return std::fmin(a,b);}
double MathAbs(double x){return std::fabs(x);}
struct QuoteBar {datetime server; double bo,bh,bl,bc,ao,ah,al,ac; int ticks;};
double MidHigh(const QuoteBar &b){return (b.bh+b.ah)/2;}
double MidLow(const QuoteBar &b){return (b.bl+b.al)/2;}
double MidClose(const QuoteBar &b){return (b.bc+b.ac)/2;}
#include "../MtfPolicy.mqh"
int passed=0;
void Check(bool ok,const char *name){if(!ok){std::fprintf(stderr,"FAIL %s\n",name);std::exit(1);}passed++;}
#include "../MtfCases.mqh"
int main(){RunMtfCases();std::printf("MTF policy: %d behaviors passed\n",passed);return 0;}
