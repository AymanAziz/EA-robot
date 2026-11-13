#ifndef GOLDNIX_MTF_POLICY
#define GOLDNIX_MTF_POLICY
// Pure closed-bar policy. Stamps use a single declared candle clock (D01: broker).
class MtfContext
{
private:
   QuoteBar recent[48],hourly[100];
   int count,hours,higher_count;
   long last,higher_close;
   double seed,averages[4],higher_mid;
   bool Aggregate(const int n,QuoteBar &b)
   {
      if(count<n) return false;
      int first=count-n;
      for(int j=first+1;j<count;j++) if(recent[j].server-recent[j-1].server!=300) return false;
      b=recent[first];
      for(int j=first+1;j<count;j++)
      {
         b.bh=MathMax(b.bh,recent[j].bh);b.bl=MathMin(b.bl,recent[j].bl);b.bc=recent[j].bc;
         b.ah=MathMax(b.ah,recent[j].ah);b.al=MathMin(b.al,recent[j].al);b.ac=recent[j].ac;b.ticks+=recent[j].ticks;
      }
      return true;
   }
public:
   void Reset()
   {
      count=0;hours=0;higher_count=0;last=-1;higher_close=0;seed=0;higher_mid=0;
      for(int j=0;j<4;j++) averages[j]=0;
   }
   bool Push(const QuoteBar &b)
   {
      if((long)b.server%300!=0 || (long)b.server<=last || b.ticks<=0 ||
         !MathIsValidNumber(b.bo+b.bh+b.bl+b.bc+b.ao+b.ah+b.al+b.ac) || b.bl<=0 ||
         b.bh<MathMax(b.bo,b.bc) || b.bl>MathMin(b.bo,b.bc) ||
         b.ah<MathMax(b.ao,b.ac) || b.al>MathMin(b.ao,b.ac) ||
         b.ao<b.bo || b.ac<b.bc || b.ah<b.bh || b.al<b.bl) return false;
      if(count==48) {for(int j=1;j<48;j++) recent[j-1]=recent[j];count--;}
      recent[count++]=b;last=(long)b.server;
      QuoteBar combined={};
      if((last+300)%3600==0 && Aggregate(12,combined))
      {
         if(hours==100) {for(int j=1;j<100;j++) hourly[j-1]=hourly[j];hours--;}
         hourly[hours++]=combined;
      }
      if((last+300)%14400==0 && Aggregate(48,combined))
      {
         higher_mid=MidClose(combined);higher_count++;higher_close=last+300;
         for(int j=0;j<3;j++) averages[j]=averages[j+1];
         if(higher_count<=50) {seed+=higher_mid;if(higher_count==50) averages[3]=seed/50;}
         else averages[3]=(2.0/51)*higher_mid+(49.0/51)*averages[2];
      }
      return true;
   }
   int HigherCount() {return higher_count;}
   int HourCount() {return hours;}
   long LastHour() {return hours>0 ? (long)hourly[hours-1].server : 0;}
   long HigherClose() {return higher_close;}
   double Average() {return averages[3];}
   bool TrendReady(const long now) {return higher_count>=100 && now>=higher_close && now<higher_close+14400;}
   int Trend(const long now)
   {
      if(!TrendReady(now)) return 0;
      return higher_mid>averages[3] && averages[3]>averages[0] ? 1 :
         higher_mid<averages[3] && averages[3]<averages[0] ? -1 : 0;
   }
   bool Signal(int &direction,double &atr,double &distance,double &spread,double &nominal,double &level,double &buffer)
   {
      if(hours<100) return false;
      atr=0;double hi=-DBL_MAX,lo=DBL_MAX;
      for(int j=hours-14;j<hours;j++) atr+=MathMax(MidHigh(hourly[j])-MidLow(hourly[j]),
         MathMax(MathAbs(MidHigh(hourly[j])-MidClose(hourly[j-1])),MathAbs(MidLow(hourly[j])-MidClose(hourly[j-1]))));
      atr/=14;
      for(int j=hours-21;j<hours-1;j++) {hi=MathMax(hi,MidHigh(hourly[j]));lo=MathMin(lo,MidLow(hourly[j]));}
      direction=MidClose(hourly[hours-1])>hi ? 1 : MidClose(hourly[hours-1])<lo ? -1 : 0;
      distance=MathMax(2*atr,.5);spread=hourly[hours-1].ac-hourly[hours-1].bc;nominal=(distance+spread)*.01;
      level=direction>0 ? hi : lo;buffer=MathMax(spread,.1*atr);
      return MathIsValidNumber(atr) && atr>0 && spread>=0;
   }
};
struct FakeoutState
{
   long magic,entry,last,previous,warning;
   int direction,seen;
   double level,buffer;
   bool exit_intent;
};
// Returns -1 invalid input, 0 hold, 1 new warning, 2 durable exit.
int FakeoutStep(FakeoutState &s,const long stamp,const double mid)
{
   if(s.exit_intent) return 2;
   if((s.direction!=1 && s.direction!=-1) || s.buffer<0 || !MathIsValidNumber(mid+s.level+s.buffer) ||
      stamp%300!=0 || (s.seen>0 && stamp<=s.last)) return -1;
   bool adverse=s.direction*(mid-s.level)<-s.buffer;
   if(s.warning>0)
   {
      if(stamp==s.warning+300 && adverse) {s.exit_intent=true;return 2;}
      s.warning=0;
   }
   bool complete=(stamp+300)%900==0 && s.seen>=2 && stamp-s.last==300 && s.last-s.previous==300 && stamp-600>=s.entry;
   s.previous=s.last;s.last=stamp;s.seen++;
   if(complete && adverse) {s.warning=stamp;return 1;}
   return 0;
}
#endif
