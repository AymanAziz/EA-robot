#property strict
#define OnStart StandaloneDemoOnStart
#include "DemoRoundTrip.mq5"
#undef OnStart

input int SessionSeconds=10800;
input int MaxTrades=36;
input double LossLimitUSC=20.0;
int session_log=INVALID_HANDLE;

void SessionRecord(const string event,const string details)
{
   FileWrite(session_log,(long)TimeGMT(),event,details);FileFlush(session_log);
   Print("DEMO_SESSION: ",event," ",details);
}

void OnStart()
{
   if(ExpectedLogin<=0 || RunMagic==0 || StringLen(RunId)<10 || StringLen(RunId)>35 ||
      StringLen(StopFileName)==0 || CloseOnly || !StopOnInterruption ||
      RequiredTimeframe!=PERIOD_M5 || HoldSeconds!=300 || SessionSeconds<310 || SessionSeconds>10800 ||
      MaxTrades<1 || MaxTrades>36 || !MathIsValidNumber(LossLimitUSC) || LossLimitUSC<=0 || LossLimitUSC>20) return;
   session_log=FileOpen("goldnix_session_"+RunId+".csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(session_log==INVALID_HANDLE) return;
   if(FileSize(session_log)==0) FileWrite(session_log,"utc_epoch","event","details");
   FileSeek(session_log,0,SEEK_END);
   for(int i=0;i<120 && !TerminalInfoInteger(TERMINAL_CONNECTED);i++) Sleep(500);
   if(!RightAccount() || _Symbol!=DEMO_SYMBOL || _Period!=PERIOD_M5 || PositionsTotal()!=0 || OrdersTotal()!=0)
   {SessionRecord("ABORT","Connected empty matching M5 demo account required");FileClose(session_log);return;}
   const string marker="Goldnix.session."+RunId;
   if(GlobalVariableCheck(marker) || StopRequested())
   {SessionRecord("ABORT","Session already attempted or stopped; use close-only recovery");FileClose(session_log);return;}
   const datetime started=TimeGMT();
   execution_deadline=started+SessionSeconds;
   if(GlobalVariableSet(marker,(double)started)==0)
   {SessionRecord("ABORT","Cannot persist session marker");FileClose(session_log);return;}
   GlobalVariablesFlush();
   SessionRecord("SESSION_START",StringFormat("deadline_utc_epoch=%I64d;max_seconds=%d;max_trades=%d;loss_limit_usc=%.2f;balance_usc=%.2f;timeframe=M5;hold_seconds=300;volume=0.01",execution_deadline,SessionSeconds,MaxTrades,LossLimitUSC,AccountInfoDouble(ACCOUNT_BALANCE)));
   int completed=0,wins=0,losses=0,breakeven=0;double cumulative=0;
   string reason="trade_limit";
   datetime last_loop=TimeGMT(),last_heartbeat=0;
   for(int i=1;i<=MaxTrades && !IsStopped();i++)
   {
      if(TimeGMT()-last_loop>10) InterruptExecution("Clock gap before next trade");
      // At most one attempt per five-minute slot, even after an early stop-loss.
      const datetime slot=started+(i-1)*300;
      while(TimeGMT()<slot && !StopRequested() && !IsStopped())
      {
         const datetime now=TimeGMT();
         if(now-last_loop>10 || !RightAccount()) {InterruptExecution("Clock gap or disconnection between trades");break;}
         if(now-last_heartbeat>=10)
         {SessionRecord("HEARTBEAT",StringFormat("completed=%d;net_pnl_usc=%.2f;positions=%d",completed,cumulative,PositionsTotal()));last_heartbeat=now;}
         last_loop=now;Sleep(200);
      }
      if(StopRequested()) {reason="stop_requested_or_interrupted";break;}
      if(!EntryTimeAvailable()) {reason="time_limit";break;}
      if(cumulative<=-LossLimitUSC) {reason="loss_limit";break;}
      if(!RightAccount()) {reason="account_or_connection_changed";break;}
      const ulong magic=RunMagic+(ulong)i;
      const string id=RunId+StringFormat("_%03d",i);
      SessionRecord("TRADE_START",StringFormat("index=%d;run_id=%s;magic=%I64u",i,id,magic));
      ExecuteDemoRoundTrip(id,magic);
      last_loop=TimeGMT();
      if(!RightAccount()) {reason="account_or_connection_changed";break;}
      if(PositionsTotal()!=0 || OrdersTotal()!=0) {reason="account_not_flat";break;}
      if(!HistorySelect(TimeCurrent()-86400,TimeCurrent()+60)) {reason="history_unavailable";break;}
      const ulong position_id=HistoryPositionForMagic(magic);
      int ins=0,outs=0;double in_volume=0,out_volume=0,pnl=0,entry_price=0,exit_price=0;
      long entry_time=0,exit_time=0;string exit_reason="";
      for(int j=0;j<HistoryDealsTotal();j++)
      {
         const ulong deal=HistoryDealGetTicket(j);
         if(position_id==0 || (ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID)!=position_id) continue;
         const long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
         const double volume=HistoryDealGetDouble(deal,DEAL_VOLUME);
         if(entry==DEAL_ENTRY_IN) {ins++;in_volume+=volume;entry_price=HistoryDealGetDouble(deal,DEAL_PRICE);entry_time=HistoryDealGetInteger(deal,DEAL_TIME);}
         if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY) {outs++;out_volume+=volume;exit_price=HistoryDealGetDouble(deal,DEAL_PRICE);exit_time=HistoryDealGetInteger(deal,DEAL_TIME);exit_reason=EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(deal,DEAL_REASON));}
         pnl+=HistoryDealGetDouble(deal,DEAL_PROFIT)+HistoryDealGetDouble(deal,DEAL_COMMISSION)+HistoryDealGetDouble(deal,DEAL_SWAP)+HistoryDealGetDouble(deal,DEAL_FEE);
      }
      if(ins!=1 || outs!=1 || MathAbs(in_volume-0.01)>0.00000001 || MathAbs(out_volume-in_volume)>0.00000001)
      {reason="execution_not_confirmed";break;}
      completed++;cumulative+=pnl;if(pnl>0) wins++;else if(pnl<0) losses++;else breakeven++;
      SessionRecord("TRADE_COMPLETE",StringFormat("index=%d;position=%I64u;entry_price=%.5f;exit_price=%.5f;held_seconds=%I64d;pnl_usc=%.2f;cumulative_pnl_usc=%.2f;balance_usc=%.2f;exit_reason=%s",i,position_id,entry_price,exit_price,exit_time-entry_time,pnl,cumulative,AccountInfoDouble(ACCOUNT_BALANCE),exit_reason));
      if(cumulative<=-LossLimitUSC) {reason="loss_limit";break;}
      Sleep(2000);
   }
   if(IsStopped()) reason="script_stopped";
   SessionRecord("SESSION_END",StringFormat("reason=%s;completed=%d;wins=%d;losses=%d;breakeven=%d;net_pnl_usc=%.2f;balance_usc=%.2f;positions=%d;orders=%d",reason,completed,wins,losses,breakeven,cumulative,AccountInfoDouble(ACCOUNT_BALANCE),PositionsTotal(),OrdersTotal()));
   FileClose(session_log);
}
