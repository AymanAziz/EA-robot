#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <random>
bool MathIsValidNumber(double n) { return std::isfinite(n); }
double MathMax(double a,double b) { return std::fmax(a,b); }
double MathAbs(double a) { return std::fabs(a); }
double MathCeil(double a) { return std::ceil(a); }
double MathFloor(double a) { return std::floor(a); }
#include "../ProfitPolicy.mqh"

int passed=0;
void Check(bool ok,const char* name) {
  if(!ok) {std::fprintf(stderr,"FAIL %s\n",name);std::exit(1);}
  passed++;
}
#include "../ProfitPolicyCases.mqh"
int main() {
  RunProfitPolicyCases();
  std::printf("profit policy: %d behaviors passed\n",passed);
  std::mt19937 rng(20261113);
  std::uniform_real_distribution<double> unit(0,1);
  for(int i=0;i<50000;i++) {
    const int side=i%2 ? 1 : -1;
    const double entry=100, risk=.5+unit(rng)*4.5, initial=entry-side*risk;
    const double previous_gain=unit(rng)*2.8*risk, previous=entry+side*previous_gain;
    const double executable=entry+side*((unit(rng)*5-1)*risk),spread=.01+unit(rng);
    const double bid=side>0 ? executable : executable-spread,ask=bid+spread;
    const double current=i%3 ? initial : entry+side*previous_gain*.3;
    const double tp=entry+side*3*risk,tick=.01,stops=unit(rng)*risk;
    double sl=0,peak=0;
    const int action=ProfitPlan(side,entry,initial,current,tp,bid,ask,previous,tick,stops,0,.2,sl,peak);
    Check(action!=PROFIT_INVALID,"valid random fixture accepted");
    Check(side*(peak-previous)>=-1e-8,"observed peak never deteriorates");
    if(action==PROFIT_MODIFY) {
      Check(side*(sl-current)>0,"planned stop always tightens");
      Check(side*(sl-entry)>0,"planned stop locks gross profit");
      Check(side*(executable-sl)+1e-8>=stops+tick,"planned stop respects minimum distance and extra tick");
      Check(side*(tp-sl)>0,"planned stop remains inside frozen TP");
      Check(std::fabs(sl/tick-std::round(sl/tick))<1e-7,"planned stop is on tick grid");
    }
  }
  std::printf("randomized policy: 50000 fixtures; %d total assertions passed\n",passed);
}
