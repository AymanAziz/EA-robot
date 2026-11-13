#property strict
#include "AutoPolicy.mqh"
int passed=0,failed=0;
void Check(const bool ok,const string name)
{
   if(ok) passed++;else {failed++;Print("AUTO_POLICY_FAIL "+name);}
}
void OnStart()
{
   AutoState s={};s.owner=123;s.sequence=1;s.day=20770;s.base_equity=2000;s.attempts=3;s.realized_r=-1;
   string payload=StatePayload(s);AutoState restored={};
   Check(ParseState(payload,123,restored),"checkpoint roundtrip");
   Check(restored.attempts==3 && restored.realized_r==-1,"restart retains consumed budget");
   Check(!ParseState(payload,456,restored),"foreign account checkpoint rejected");
   Check(!ParseState(payload+"junk",123,restored),"corrupt checkpoint rejected");
   Check(StateChecksum(payload)!=StateChecksum(payload+"x"),"checksum catches changed bytes");
   s.last_signal=3000;
   Check(!FreshSignal(s,3000,3300,false),"duplicate bar rejected");
   Check(!FreshSignal(s,3300,3599,false),"forming bar rejected");
   Check(!FreshSignal(s,3300,3610,false),"stale bar rejected");
   Check(!FreshSignal(s,3300,3600,true),"reconnect never enters old signal");
   Check(FreshSignal(s,3300,3600,false),"next completed bar accepted");
   Check(!ResetDayIfFlat(s,20770,2000,0,0) && s.attempts==3,"same day reopen does not reset");
   Check(!ResetDayIfFlat(s,20769,2000,0,0) && s.attempts==3,"backward clock cannot restore a spent budget");
   s.pending_magic=AUTO_MAGIC_BASE+2077001;
   Check(!ResetDayIfFlat(s,20771,2000,0,0),"unreconciled intent prevents rollover");
   s.pending_magic=0;
   Check(!ResetDayIfFlat(s,20771,2000,1,0),"open position prevents rollover");
   s.fatal=true;
   Check(ResetDayIfFlat(s,20771,1990,0,0) && s.attempts==0 && s.fatal,"new flat day resets budget but preserves audit halt");
   s.fatal=false;s.attempts=7;
   Check(RiskReason(s,1990)=="daily_attempt_limit","seven attempt cap");
   s.attempts=0;s.realized_r=-2;
   Check(RiskReason(s,1990)=="daily_r_limit","minus two R cap");
   s.realized_r=0;
   Check(RiskReason(s,1980)=="daily_loss_limit","ten USC equity loss cap");
   Check(MalaysiaDay(1794585599)+1==MalaysiaDay(1794585600),"Malaysia midnight boundary");
   QuoteBar bars[];ArrayResize(bars,100);
   for(int j=0;j<100;j++) {bars[j].bh=100.5;bars[j].bl=99.5;bars[j].bc=100;bars[j].ah=100.6;bars[j].al=99.6;bars[j].ac=100.1;}
   int direction=0;double atr=0,distance=0,spread=0,nominal=0;
   Check(SignalStats(bars,direction,atr,distance,spread,nominal) && direction==0 && MathAbs(atr-1)<1e-10,"flat channel");
   bars[99].bh=101;bars[99].bc=101;bars[99].ah=101.1;bars[99].ac=101.1;
   Check(SignalStats(bars,direction,atr,distance,spread,nominal) && direction==1 && MathAbs(atr-14.5/14)<1e-10,"buy breakout");
   bars[99].bh=100.5;bars[99].ah=100.6;bars[99].bl=99;bars[99].bc=99;bars[99].al=99.1;bars[99].ac=99.1;
   Check(SignalStats(bars,direction,atr,distance,spread,nominal) && direction==-1 && MathAbs(atr-14.5/14)<1e-10,"sell breakout");
   int f=FileOpen("goldnix_auto_policy_probe.csv",FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,',');
   FileWrite(f,"passed","failed");FileWrite(f,passed,failed);FileClose(f);
   PrintFormat("AUTO_POLICY_TESTS passed=%d failed=%d",passed,failed);
}
