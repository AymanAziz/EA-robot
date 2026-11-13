#property strict
#include "AutoM1Policy.mqh"
#include "ProfitJournal.mqh"
int passed=0,failed=0;
void Check(const bool ok,const string name)
{
   if(ok) passed++;else {failed++;Print("AUTO_POLICY_FAIL "+name);}
}
#include "ProfitPolicyCases.mqh"
void OnStart()
{
   RunProfitPolicyCases();
   ProfitRecord p={};p.owner=123;p.magic=456;p.position=789;p.direction=1;
   p.entry=100;p.initial_sl=96;p.tp=112;p.peak=106;p.accepted_sl=103;p.close_requested=false;
   string journal="GoldnixProfitPolicyProbeOnly.csv";ProfitRecord reread={};FileDelete(journal,0);
   Check(SaveProfit(journal,p) && ReadProfit(journal,123,456,reread),"native profit journal survives write and reload");
   Check(reread.peak==106 && reread.accepted_sl==103 && reread.initial_sl==96,"restart preserves peak locked stop and original risk");
   Check(!ReadProfit(journal,124,456,reread),"profit journal rejects wrong account");
   Check(!ReadProfit(journal,123,457,reread),"profit journal rejects wrong trade");
   p.close_requested=true;
   Check(SaveProfit(journal,p) && ReadProfit(journal,123,456,reread) && reread.close_requested,"floor exit intent survives restart");
   Check(!ParseProfit(ProfitPayload(p)+"x",123,456,reread),"noncanonical profit journal rejected");
   p.accepted_sl=95;
   Check(!SaveProfit(journal,p),"weakened stop cannot enter durable record");
   Check(ReadProfit(journal,123,456,reread) && reread.accepted_sl==103,"invalid save preserves previous committed protection");
   int corrupt=FileOpen(journal,FILE_WRITE|FILE_TXT|FILE_ANSI);FileWriteString(corrupt,"corrupt");FileClose(corrupt);
   Check(!ReadProfit(journal,123,456,reread),"corrupt committed journal fails closed");
   FileDelete(journal,0);FileDelete(journal+".next",0);
   Check(!ReadProfit(journal,123,456,reread),"missing journal is not treated as valid protection");
   AutoState s={};s.owner=123;s.sequence=1;s.day=20770;s.base_equity=2000;s.attempts=3;s.realized_r=-1;
   string payload=StatePayload(s);AutoState restored={};
   Check(ParseState(payload,123,restored),"checkpoint roundtrip");
   Check(restored.attempts==3 && restored.realized_r==-1,"restart retains consumed budget");
   Check(!ParseState(payload,456,restored),"foreign account checkpoint rejected");
   Check(!ParseState(payload+"junk",123,restored),"corrupt checkpoint rejected");
   Check(StateChecksum(payload)!=StateChecksum(payload+"x"),"checksum catches changed bytes");
   s.last_signal=3000;
   Check(!FreshSignal(s,3000,3060,false),"duplicate bar rejected");
   Check(!FreshSignal(s,3060,3119,false),"forming bar rejected");
   Check(!FreshSignal(s,3060,3130,false),"stale bar rejected");
   Check(!FreshSignal(s,3060,3120,true),"reconnect never enters old signal");
   Check(FreshSignal(s,3060,3120,false),"next completed bar accepted");
   Check(AUTO_BAR_SECONDS==60,"M1 period is sixty seconds");
   Check(!FreshSignal(s,3060,3360,false),"old M5 timing cannot trade stale M1 signal");
   Check(!ExecutionCheckAvailable(0,4000,false),"execution check disabled by default");
   Check(!ExecutionCheckAvailable(4001,4000,false),"future execution request rejected");
   Check(!ExecutionCheckAvailable(4000,7600,false),"execution request expires after one hour");
   Check(!ExecutionCheckAvailable(4000,4001,true),"consumed request cannot repeat after restart");
   Check(ExecutionCheckAvailable(4000,7599,false),"unconsumed request available before expiry");
   QuoteBar candle={};candle.bo=100;candle.ao=100.1;candle.bc=101;candle.ac=101.1;
   Check(ExecutionCheckDirection(candle)==1,"execution check bullish candle chooses buy");
   candle.bc=99;candle.ac=99.1;
   Check(ExecutionCheckDirection(candle)==-1,"execution check bearish candle chooses sell");
   candle.bc=candle.bo;candle.ac=candle.ao;
   Check(ExecutionCheckDirection(candle)==0,"execution check doji does not force a direction");
   double check_distance=0,check_nominal=0;
   Check(ExecutionCheckSizing(3,.6,check_distance,check_nominal) && MathAbs(check_distance-3.4)<1e-10 && MathAbs(check_nominal-.04)<1e-10,
      "execution check caps planned risk at four USC during high volatility");
   Check(ExecutionCheckSizing(1,.6,check_distance,check_nominal) && MathAbs(check_distance-2)<1e-10 && MathAbs(check_nominal-.026)<1e-10,
      "execution check does not enlarge a smaller ATR stop");
   Check(!ExecutionCheckSizing(3,3.6,check_distance,check_nominal),"execution check rejects spread that leaves no minimum stop");
   Check(!ExecutionCheckSizing(0,.6,check_distance,check_nominal),"execution check rejects invalid volatility");
   string receipt="GoldnixM1PolicyProbeOnly.receipt.csv";FileDelete(receipt,0);
   Check(ClaimExecutionCheck(receipt,4000,4001),"execution receipt flushed and read back before entry");
   Check(!ClaimExecutionCheck(receipt,4000,4002),"persisted receipt prevents another claim");
   FileDelete(receipt,0);
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
   int f=FileOpen("goldnix_auto_m1_policy_probe.csv",FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   FileWrite(f,"passed","failed");FileWrite(f,passed,failed);FileClose(f);
   PrintFormat("AUTO_POLICY_TESTS passed=%d failed=%d",passed,failed);
}
