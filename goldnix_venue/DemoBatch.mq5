#property strict
#define OnStart StandaloneDemoOnStart
#include "DemoRoundTrip.mq5"
#undef OnStart

input int MaxTrades=30;
input int MaxSessionSeconds=1800;
input double LossLimitUSC=20.0;
int batch_audit=INVALID_HANDLE;

void BatchRecord(const string event,const string details)
{
   FileWrite(batch_audit,(long)TimeGMT(),event,details);
   FileFlush(batch_audit);
   Print("DEMO_BATCH: ",event," ",details);
}

void OnStart()
{
   if(ExpectedLogin<=0 || RunMagic==0 || StringLen(RunId)<10 || StringLen(RunId)>35 ||
      StringLen(StopFileName)==0 || MaxTrades<1 || MaxTrades>60 ||
      MaxSessionSeconds<90 || MaxSessionSeconds>3600 || HoldSeconds!=60 ||
      RequiredTimeframe!=PERIOD_M1 || !MathIsValidNumber(LossLimitUSC) || LossLimitUSC<=0 || LossLimitUSC>100) return;
   batch_audit=FileOpen("goldnix_batch_"+RunId+".csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(batch_audit==INVALID_HANDLE) return;
   if(FileSize(batch_audit)==0) FileWrite(batch_audit,"utc_epoch","event","details");
   FileSeek(batch_audit,0,SEEK_END);
   for(int i=0;i<120 && !TerminalInfoInteger(TERMINAL_CONNECTED);i++) Sleep(500);
   if(!RightAccount() || _Period!=PERIOD_M1 || _Symbol!=DEMO_SYMBOL)
   {BatchRecord("ABORT","Matching connected M1 demo account required");FileClose(batch_audit);return;}
   const string start_key="Goldnix.batch."+RunId+".start";
   if(!GlobalVariableCheck(start_key))
   {
      if(GlobalVariableSet(start_key,(double)TimeGMT())==0)
      {BatchRecord("ABORT","Could not persist session start");FileClose(batch_audit);return;}
      GlobalVariablesFlush();
   }
   const datetime started=(datetime)GlobalVariableGet(start_key);
   const datetime deadline=started+MaxSessionSeconds;
   BatchRecord("SESSION_START",StringFormat("max_trades=%d;max_seconds=%d;loss_limit_usc=%.2f;balance_usc=%.2f;deadline_utc_epoch=%I64d;timeframe=M1;volume=0.01",MaxTrades,MaxSessionSeconds,LossLimitUSC,AccountInfoDouble(ACCOUNT_BALANCE),deadline));
   int completed=0,wins=0,losses=0,breakeven=0;
   double cumulative=0;
   string reason="trade_limit";
   for(int i=1;i<=MaxTrades && !IsStopped();i++)
   {
      if(StopRequested()) {reason="stop_requested";break;}
      if(TimeGMT()+HoldSeconds+10>deadline) {reason="time_limit";break;}
      if(cumulative<=-LossLimitUSC) {reason="loss_limit";break;}
      if(!RightAccount()) {reason="account_or_connection_changed";break;}
      const ulong magic=RunMagic+(ulong)i;
      const string trade_id=RunId+StringFormat("_%03d",i);
      BatchRecord("TRADE_START",StringFormat("index=%d;run_id=%s;magic=%I64u",i,trade_id,magic));
      ExecuteDemoRoundTrip(trade_id,magic);
      if(!RightAccount()) {reason="account_or_connection_changed";break;}
      if(OwnPosition()>0 || PositionsTotal()>0 || OrdersTotal()>0)
      {reason="account_not_flat";break;}
      if(!HistorySelect(TimeCurrent()-86400,TimeCurrent()+60)) {reason="history_unavailable";break;}
      const ulong position_id=HistoryPositionForMagic(magic);
      int entries=0,exits=0;
      double entry_volume=0,exit_volume=0,pnl=0,entry_price=0,exit_price=0;
      long entry_time=0,exit_time=0;
      string exit_reason="";
      for(int j=0;j<HistoryDealsTotal();j++)
      {
         const ulong deal=HistoryDealGetTicket(j);
         if(position_id==0 || (ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID)!=position_id) continue;
         const long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
         const double volume=HistoryDealGetDouble(deal,DEAL_VOLUME);
         if(entry==DEAL_ENTRY_IN)
         {entries++;entry_volume+=volume;entry_price=HistoryDealGetDouble(deal,DEAL_PRICE);entry_time=HistoryDealGetInteger(deal,DEAL_TIME);}
         if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY)
         {exits++;exit_volume+=volume;exit_price=HistoryDealGetDouble(deal,DEAL_PRICE);exit_time=HistoryDealGetInteger(deal,DEAL_TIME);exit_reason=EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(deal,DEAL_REASON));}
         pnl+=HistoryDealGetDouble(deal,DEAL_PROFIT)+HistoryDealGetDouble(deal,DEAL_COMMISSION)+HistoryDealGetDouble(deal,DEAL_SWAP)+HistoryDealGetDouble(deal,DEAL_FEE);
      }
      if(entries<1 || exits<1 || MathAbs(entry_volume-0.01)>0.00000001 || MathAbs(exit_volume-entry_volume)>0.00000001)
      {reason="execution_not_confirmed";break;}
      completed++; cumulative+=pnl;
      if(pnl>0) wins++; else if(pnl<0) losses++; else breakeven++;
      BatchRecord("TRADE_COMPLETE",StringFormat("index=%d;position=%I64u;entry_price=%.5f;exit_price=%.5f;held_seconds=%I64d;pnl_usc=%.2f;cumulative_pnl_usc=%.2f;balance_usc=%.2f;exit_reason=%s",i,position_id,entry_price,exit_price,exit_time-entry_time,pnl,cumulative,AccountInfoDouble(ACCOUNT_BALANCE),exit_reason));
      if(i<MaxTrades) Sleep(2000);
   }
   if(IsStopped()) reason="script_stopped";
   BatchRecord("SESSION_END",StringFormat("reason=%s;completed=%d;wins=%d;losses=%d;breakeven=%d;net_pnl_usc=%.2f;balance_usc=%.2f;positions=%d;orders=%d",reason,completed,wins,losses,breakeven,cumulative,AccountInfoDouble(ACCOUNT_BALANCE),PositionsTotal(),OrdersTotal()));
   FileClose(batch_audit);
}
