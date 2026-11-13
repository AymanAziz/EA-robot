#property strict
#include <Trade/Trade.mqh>

// Explicitly invoked demo execution test. Defaults cannot place an order.
input long ExpectedLogin=0;
input ulong RunMagic=0;
input string RunId="";
input int HoldSeconds=3;
input ENUM_TIMEFRAMES RequiredTimeframe=PERIOD_CURRENT;
input string StopFileName="";
input bool CloseOnly=false;
input bool StopOnInterruption=false;
const string DEMO_SYMBOL="XAUUSD.c";
int audit=INVALID_HANDLE;
ulong active_magic=0;
string active_run_id="";
datetime execution_deadline=0;
bool interrupted=false;

bool StopRequested()
{
   return interrupted || (StringLen(StopFileName)>0 && FileIsExist(StopFileName,FILE_COMMON));
}

void InterruptExecution(const string reason)
{
   interrupted=true;
   if(StringLen(StopFileName)>0)
   {
      const int f=FileOpen(StopFileName,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON);
      if(f!=INVALID_HANDLE) {FileWriteString(f,reason);FileClose(f);}
   }
   Print("DEMO_INTERRUPTED: ",reason);
}

bool EntryTimeAvailable()
{
   return execution_deadline==0 || TimeGMT()+HoldSeconds+5<execution_deadline;
}

void Record(const string event,const string details)
{
   if(audit!=INVALID_HANDLE)
   { FileWrite(audit,(long)TimeGMT(),event,details); FileFlush(audit); }
   Print("DEMO_ROUNDTRIP: ",event," ",details);
}

bool RightAccount()
{
   return ExpectedLogin>0 && AccountInfoInteger(ACCOUNT_LOGIN)==ExpectedLogin &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
      AccountInfoInteger(ACCOUNT_MARGIN_MODE)==ACCOUNT_MARGIN_MODE_RETAIL_HEDGING &&
      AccountInfoString(ACCOUNT_SERVER)=="JustMarkets-Demo6" &&
      AccountInfoString(ACCOUNT_CURRENCY)=="USC" && TerminalInfoInteger(TERMINAL_CONNECTED);
}

ulong OwnPosition()
{
   for(int i=0;i<PositionsTotal();i++)
   {
      const ulong ticket=PositionGetTicket(i);
      if(ticket>0 && PositionGetString(POSITION_SYMBOL)==DEMO_SYMBOL &&
         (ulong)PositionGetInteger(POSITION_MAGIC)==active_magic) return ticket;
   }
   return 0;
}

// Requires HistorySelect first. Include broker/user exits of the same position,
// even if their closing deal has a different magic number.
ulong HistoryPositionForMagic(const ulong magic)
{
   for(int i=0;i<HistoryDealsTotal();i++)
   {
      const ulong d=HistoryDealGetTicket(i);
      if((ulong)HistoryDealGetInteger(d,DEAL_MAGIC)==magic &&
         HistoryDealGetInteger(d,DEAL_ENTRY)==DEAL_ENTRY_IN &&
         HistoryDealGetString(d,DEAL_SYMBOL)==DEMO_SYMBOL)
         return (ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID);
   }
   return 0;
}

void ExecuteDemoRoundTrip(const string run_id,const ulong magic)
{
   active_magic=magic; active_run_id=run_id;
   if(ExpectedLogin<=0 || active_magic==0 || StringLen(active_run_id)<10 || HoldSeconds<1 || HoldSeconds>300) return;
   audit=FileOpen("goldnix_demo_"+active_run_id+".csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(audit==INVALID_HANDLE) return;
   if(FileSize(audit)==0) FileWrite(audit,"utc_epoch","event","details");
   FileSeek(audit,0,SEEK_END);
   for(int i=0;i<120 && !TerminalInfoInteger(TERMINAL_CONNECTED);i++) Sleep(500);
   if(!RightAccount()) {Record("ABORT","Required matching JustMarkets USC demo hedging account is not connected");FileClose(audit);return;}
   if(_Symbol!=DEMO_SYMBOL || (RequiredTimeframe!=PERIOD_CURRENT && _Period!=RequiredTimeframe))
   {Record("ABORT","Chart symbol or timeframe does not match this execution test");FileClose(audit);return;}
   Record("SETUP",StringFormat("chart_timeframe=%s;hold_seconds=%d;volume=0.01",EnumToString(_Period),HoldSeconds));
   Record("ACCOUNT",StringFormat("server=JustMarkets-Demo6;currency=USC;balance=%.2f;equity=%.2f",AccountInfoDouble(ACCOUNT_BALANCE),AccountInfoDouble(ACCOUNT_EQUITY)));
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      !AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
   {Record("ABORT","Trading permission is disabled");FileClose(audit);return;}
   CTrade trade;
   trade.SetExpertMagicNumber(active_magic);
   trade.SetDeviationInPoints(50);
   trade.SetAsyncMode(false);
   if(!SymbolSelect(DEMO_SYMBOL,true) || !trade.SetTypeFillingBySymbol(DEMO_SYMBOL))
   {Record("ABORT","Symbol or filling policy unavailable");FileClose(audit);return;}
   const string marker="Goldnix.demo."+active_run_id;
   if(!GlobalVariableCheck(marker) && !CloseOnly)
   {
      if(StopRequested()) {Record("ABORT","Stop requested before entry");FileClose(audit);return;}
      if(PositionsTotal()!=0 || OrdersTotal()!=0 || SymbolInfoInteger(DEMO_SYMBOL,SYMBOL_CUSTOM) ||
         SymbolInfoInteger(DEMO_SYMBOL,SYMBOL_TRADE_MODE)!=SYMBOL_TRADE_MODE_FULL ||
         MathAbs(SymbolInfoDouble(DEMO_SYMBOL,SYMBOL_VOLUME_MIN)-0.01)>0.00000001 ||
         MathAbs(SymbolInfoDouble(DEMO_SYMBOL,SYMBOL_VOLUME_STEP)-0.01)>0.00000001)
      {Record("ABORT","Expected empty account and standard 0.01 minimum/step");FileClose(audit);return;}
      MqlTick tick={}; double margin=0,profit=0; bool ready=false;
      for(int i=0;i<120;i++)
      {
         if(StopRequested() || !EntryTimeAvailable()) break;
         ready=RightAccount() && SymbolInfoTick(DEMO_SYMBOL,tick) && tick.bid>1 && tick.ask>=tick.bid &&
            tick.ask-tick.bid<=2 && TimeTradeServer()-tick.time>=0 && TimeTradeServer()-tick.time<=30 &&
            OrderCalcProfit(ORDER_TYPE_BUY,DEMO_SYMBOL,0.01,tick.ask,tick.ask-1,profit) &&
            OrderCalcMargin(ORDER_TYPE_BUY,DEMO_SYMBOL,0.01,tick.ask,margin) &&
            MathIsValidNumber(profit) && profit<0 && MathIsValidNumber(margin) && margin>0 &&
            margin<AccountInfoDouble(ACCOUNT_MARGIN_FREE);
         if(ready) break;
         Sleep(250);
      }
      if(!ready) {Record("ABORT","Fresh quotes and positive affordable economics unavailable");FileClose(audit);return;}
      if(StopRequested() || !EntryTimeAvailable()) {Record("ABORT","Stop or deadline prevents entry");FileClose(audit);return;}
      const double distance=MathMax(1.0,SymbolInfoInteger(DEMO_SYMBOL,SYMBOL_TRADE_STOPS_LEVEL)*SymbolInfoDouble(DEMO_SYMBOL,SYMBOL_POINT)+0.05);
      if(distance>2) {Record("ABORT","Broker stop distance exceeds this execution test's bound");FileClose(audit);return;}
      const double sl=NormalizeDouble(tick.bid-distance,(int)SymbolInfoInteger(DEMO_SYMBOL,SYMBOL_DIGITS));
      // Persist before the single entry request. Re-running this run can only close/reconcile.
      if(GlobalVariableSet(marker,(double)TimeGMT())==0)
      {Record("ABORT","Could not persist single-entry marker");FileClose(audit);return;}
      GlobalVariablesFlush();
      Record("ENTRY_INTENT",StringFormat("symbol=%s;volume=0.01;side=BUY;stop_loss=%.5f;margin_USC=%.2f",DEMO_SYMBOL,sl,margin));
      Record("ENTRY_QUOTE",StringFormat("bid=%.5f;ask=%.5f;spread=%.5f;quote_server_epoch=%I64d",tick.bid,tick.ask,tick.ask-tick.bid,tick.time));
      if(!RightAccount()) {Record("ABORT","Account changed before entry");FileClose(audit);return;}
      const bool sent=trade.Buy(0.01,DEMO_SYMBOL,0,sl,0,"Goldnix demo execution");
      Record("BUY_RESULT",StringFormat("sent=%s;retcode=%u;order=%I64u;deal=%I64u;price=%.5f",sent?"true":"false",trade.ResultRetcode(),trade.ResultOrder(),trade.ResultDeal(),trade.ResultPrice()));
      Record("BUY_COMMENT",trade.ResultComment());
      for(int i=0;i<60 && OwnPosition()==0;i++) Sleep(250);
   }
   else Record("RESUME","Close-only or entry already attempted; no new BUY will be sent");
   ulong position=OwnPosition();
   if(position>0)
   {
      Record("POSITION",StringFormat("ticket=%I64u;volume=%.2f;price=%.5f",position,PositionGetDouble(POSITION_VOLUME),PositionGetDouble(POSITION_PRICE_OPEN)));
      const ulong hold_start=GetTickCount64();
      datetime last_loop=TimeGMT(),last_heartbeat=0;
      while(!CloseOnly && OwnPosition()>0 && GetTickCount64()-hold_start<(ulong)(HoldSeconds*1000) && !IsStopped() && !StopRequested())
      {
         const datetime now=TimeGMT();
         if(StopOnInterruption && (now-last_loop>10 || !RightAccount()))
         {InterruptExecution("Clock gap, disconnection, or account change during hold");break;}
         if(execution_deadline>0 && now>=execution_deadline) break;
         if(now-last_heartbeat>=10)
         {
            Record("HEARTBEAT",StringFormat("connected=%d;balance_usc=%.2f;equity_usc=%.2f;positions=%d",TerminalInfoInteger(TERMINAL_CONNECTED),AccountInfoDouble(ACCOUNT_BALANCE),AccountInfoDouble(ACCOUNT_EQUITY),PositionsTotal()));
            last_heartbeat=now;
         }
         last_loop=now;Sleep(200);
      }
      Record("HOLD_END",StringFormat("elapsed_ms=%I64u;position_still_open=%d",GetTickCount64()-hold_start,OwnPosition()>0?1:0));
      for(int i=0;i<10 && OwnPosition()>0;i++)
      {
         position=OwnPosition();
         if(!RightAccount() || !PositionSelectByTicket(position) || PositionGetDouble(POSITION_VOLUME)>0.01000001) break;
         const bool sent=trade.PositionClose(position,50);
         Record("CLOSE_RESULT",StringFormat("sent=%s;retcode=%u;order=%I64u;deal=%I64u;price=%.5f",sent?"true":"false",trade.ResultRetcode(),trade.ResultOrder(),trade.ResultDeal(),trade.ResultPrice()));
         Sleep(500);
      }
   }
   Sleep(1000);
   int entries=0,exits=0;
   if(HistorySelect(TimeCurrent()-86400,TimeCurrent()+60))
   {
      const ulong position_id=HistoryPositionForMagic(active_magic);
      for(int i=0;i<HistoryDealsTotal();i++)
      {
         const ulong deal=HistoryDealGetTicket(i);
         if(position_id==0 || (ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID)!=position_id) continue;
         const long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
         if(entry==DEAL_ENTRY_IN) entries++;
         if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY) exits++;
         Record("DEAL",StringFormat("ticket=%I64u;position=%I64u;entry=%d;type=%d;volume=%.2f;price=%.5f;profit=%.2f;commission=%.2f;swap=%.2f;fee=%.2f;time_server_epoch=%I64d;reason=%s",deal,
            HistoryDealGetInteger(deal,DEAL_POSITION_ID),entry,HistoryDealGetInteger(deal,DEAL_TYPE),
            HistoryDealGetDouble(deal,DEAL_VOLUME),HistoryDealGetDouble(deal,DEAL_PRICE),HistoryDealGetDouble(deal,DEAL_PROFIT),
            HistoryDealGetDouble(deal,DEAL_COMMISSION),HistoryDealGetDouble(deal,DEAL_SWAP),HistoryDealGetDouble(deal,DEAL_FEE),
            HistoryDealGetInteger(deal,DEAL_TIME),EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(deal,DEAL_REASON))));
      }
   }
   Record("FINAL",StringFormat("entries=%d;exits=%d;own_open_positions=%d;all_positions=%d;all_orders=%d;balance_USC=%.2f;equity_USC=%.2f",entries,exits,OwnPosition()>0?1:0,PositionsTotal(),OrdersTotal(),AccountInfoDouble(ACCOUNT_BALANCE),AccountInfoDouble(ACCOUNT_EQUITY)));
   FileClose(audit);
}

void OnStart()
{
   ExecuteDemoRoundTrip(RunId,RunMagic);
}
