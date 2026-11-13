#property strict
#include <Trade/Trade.mqh>

// Resident script. DEMO identity, one-attempt marker, wall-clock deadline and
// broker-side SL/TP apply independently of the Python watchdog.
input long ExpectedLogin=0;
input string RunId="";
input ulong MagicBase=0;
input int Mode=0; // 0: read-only preflight, 1: bounded session, 2: close-only recovery
input datetime StartUTC=0;
input datetime EndUTC=0;
input int ExpectedOffsetSeconds=0;
input string StopFile="";
input int MaxTrades=7;
input double SessionLossLimitUSC=10.0;

struct QuoteBar { datetime server; double bo,bh,bl,bc,ao,ah,al,ac; int ticks; };
QuoteBar bars[];
CTrade trade;
int events=INVALID_HANDLE,barfile=INVALID_HANDLE,signals=INVALID_HANDLE,closed=INVALID_HANDLE;
int tickfile=INVALID_HANDLE;
long captured_session_ticks=0;
bool quote_archive_complete=true;
int offset_seconds=0,entry_attempts=0,completed=0;
datetime current_hour=0,last_heartbeat=0,last_loop=0,last_exit_m5=0;
double daily_r=0,start_equity=0;
long booked_day=-1;
bool entry_halt=false;
bool audit_failed=false;
string halt_reason="",prefix;
ulong active_id=0,active_ticket=0;
double active_atr=0,active_distance=0,active_entry=0;
int active_direction=0;

bool Identity()
{
   return ExpectedLogin>0 && AccountInfoInteger(ACCOUNT_LOGIN)==ExpectedLogin &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
      AccountInfoString(ACCOUNT_SERVER)=="JustMarkets-Demo6" &&
      AccountInfoString(ACCOUNT_CURRENCY)=="USC" && _Symbol=="XAUUSD.c";
}
bool Connected() {return Identity() && TerminalInfoInteger(TERMINAL_CONNECTED);}
bool OwnedMagic(const ulong magic) {return magic>MagicBase && magic<=MagicBase+(ulong)MaxTrades;}
int OwnPositions()
{
   int count=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
      if(PositionGetTicket(i)>0 && PositionGetString(POSITION_SYMBOL)==_Symbol &&
         OwnedMagic((ulong)PositionGetInteger(POSITION_MAGIC))) count++;
   return count;
}
int OwnOrders()
{
   int count=0;
   for(int i=OrdersTotal()-1;i>=0;i--)
      if(OrderGetTicket(i)>0 && OrderGetString(ORDER_SYMBOL)==_Symbol &&
         OwnedMagic((ulong)OrderGetInteger(ORDER_MAGIC))) count++;
   return count;
}
void Event(const string name,const string detail)
{
   FileWrite(events,(long)TimeGMT(),name,detail);FileFlush(events);
}
void Halt(const string reason)
{
   if(!entry_halt) {entry_halt=true;halt_reason=reason;Event("HALT",reason);}
}
bool ObserveClock()
{
   if(!Connected()) return false;
   long observed=(long)(TimeTradeServer()-TimeGMT());
   int rounded=(int)MathRound((double)observed/3600)*3600;
   if((rounded!=7200 && rounded!=10800) || MathAbs((double)observed-rounded)>5) return false;
   if(offset_seconds==0) offset_seconds=rounded;
   return rounded==offset_seconds && (ExpectedOffsetSeconds==0 || rounded==ExpectedOffsetSeconds);
}
datetime ToUTC(const datetime server) {return server-offset_seconds;}
double MidHigh(const QuoteBar &bar) {return (bar.bh+bar.ah)/2;}
double MidLow(const QuoteBar &bar) {return (bar.bl+bar.al)/2;}
double MidClose(const QuoteBar &bar) {return (bar.bc+bar.ac)/2;}
bool Holiday(const datetime stamp)
{
   MqlDateTime t;TimeToStruct(stamp,t);
   if((t.mon==12 && t.day>=24 && t.day<=26) || (t.mon==1 && t.day==1)) return true;
   if(t.mon==11 && t.day_of_week==4 && t.day>=22 && t.day<=28) return true;
   int a=t.year%19,b=t.year/100,c=t.year%100,d=b/4,e=b%4,f=(b+8)/25;
   int g=(b-f+1)/3,h=(19*a+b-d-g+15)%30,i=c/4,k=c%4;
   int l=(32+2*e+2*i-h-k)%7,m=(a+11*h+22*l)/451;
   MqlDateTime easter=t;easter.mon=(h+l-7*m+114)/31;
   easter.day=(h+l-7*m+114)%31+1;easter.hour=0;easter.min=0;easter.sec=0;
   return (long)stamp/86400==(long)(StructToTime(easter)-2*86400)/86400;
}

datetime MarketEndUTC(const datetime now_utc)
{
   datetime server_now=now_utc+offset_seconds;
   datetime midnight=(datetime)((long)server_now/86400*86400);
   // Previous day's session can carry past midnight. Preserve raw end seconds.
   for(int previous=0;previous<=1;previous++)
   {
      datetime day=midnight-previous*86400;
      MqlDateTime t;TimeToStruct(day,t);
      for(uint j=0;j<20;j++)
      {
         datetime from=0,to=0;
         if(!SymbolInfoSessionTrade(_Symbol,(ENUM_DAY_OF_WEEK)t.day_of_week,j,from,to)) break;
         long begin=(long)from,end=(long)to;
         if(begin==0 && end==0) continue;
         if(end<=begin) end+=86400;
         if(server_now>=day+begin && server_now<day+end) return ToUTC(day+end);
      }
   }
   return 0;
}
bool AppendBar(const datetime server_open,const bool archive_only=false)
{
   MqlTick ticks[];
   datetime through=(datetime)MathMin((double)(server_open+3599),(double)(EndUTC+offset_seconds-1));
   if(through<server_open) return archive_only;
   ResetLastError();
   int count=CopyTicksRange(_Symbol,ticks,COPY_TICKS_ALL,(ulong)server_open*1000,
                           (ulong)through*1000+999);
   int error=GetLastError();
   if(archive_only && count==0 && error==0) return true;
   if(count<=0 || error!=0) {Event("DATA_ERROR",StringFormat("bar=%I64d;count=%d;error=%d",(long)server_open,count,error));return false;}
   QuoteBar bar;bar.server=server_open;bar.bo=ticks[0].bid;bar.ao=ticks[0].ask;
   bar.bh=-DBL_MAX;bar.ah=-DBL_MAX;bar.bl=DBL_MAX;bar.al=DBL_MAX;bar.bc=0;bar.ac=0;bar.ticks=count;
   for(int j=0;j<count;j++)
   {
      if(ticks[j].bid<=0 || ticks[j].ask<ticks[j].bid) return false;
      bar.bh=MathMax(bar.bh,ticks[j].bid);bar.bl=MathMin(bar.bl,ticks[j].bid);bar.bc=ticks[j].bid;
      bar.ah=MathMax(bar.ah,ticks[j].ask);bar.al=MathMin(bar.al,ticks[j].ask);bar.ac=ticks[j].ask;
   }
   // Keep original bid/ask ticks from the session for independent daily review.
   // Warmup prices remain in h1.csv; avoid repeatedly copying days of old ticks.
   if(tickfile!=INVALID_HANDLE)
      for(int j=0;j<count;j++)
         if(ToUTC(ticks[j].time)>=StartUTC && ToUTC(ticks[j].time)<EndUTC)
         {
            FileWriteLong(tickfile,ticks[j].time_msc);FileWriteDouble(tickfile,ticks[j].bid);FileWriteDouble(tickfile,ticks[j].ask);
            captured_session_ticks++;
         }
   int size=ArraySize(bars);ArrayResize(bars,size+1);bars[size]=bar;
   FileWrite(barfile,(long)ToUTC(bar.server),DoubleToString(bar.bo,8),DoubleToString(bar.bh,8),
      DoubleToString(bar.bl,8),DoubleToString(bar.bc,8),DoubleToString(bar.ao,8),DoubleToString(bar.ah,8),
      DoubleToString(bar.al,8),DoubleToString(bar.ac,8),count);
   FileFlush(barfile);return true;
}
bool Warmup()
{
   MqlRates rates[];int count=-1;
   for(int j=0;j<30 && count!=100;j++) {count=CopyRates(_Symbol,PERIOD_H1,1,100,rates);if(count!=100) Sleep(500);}
   if(count!=100) return false;
   for(int j=0;j<count;j++)
   {
      if(IsStopped() || TimeGMT()>=EndUTC || !Connected() || !AppendBar(rates[j].time)) return false;
      if(j%20==0) Event("WARMUP",StringFormat("completed_bars=%d",j+1));
   }
   MqlTick tick;if(!SymbolInfoTick(_Symbol,tick)) return false;
   current_hour=(datetime)((long)tick.time/3600*3600);
   // Refuse history spanning a rollover; the controller can start a fresh check.
   return rates[99].time==iTime(_Symbol,PERIOD_H1,1) && ObserveClock();
}
void RollDay(const datetime stamp)
{
   long day=(long)stamp/86400;
   if(day!=booked_day) {booked_day=day;daily_r=0;}
}
bool Reconcile()
{
   if(active_id==0 || OwnPositions()>0) return true;
   if(!HistorySelectByPosition(active_id)) return false;
   long open_time=0,close_time=0,why=0;double close_price=0,pnl=0,in_volume=0,out_volume=0;
   int ins=0,outs=0;
   for(int j=0;j<HistoryDealsTotal();j++)
   {
      ulong deal=HistoryDealGetTicket(j);long side=0,stamp=0,reason=0;
      double price=0,volume=0,profit=0,commission=0,swap=0,fee=0;
      if(deal==0 || !HistoryDealGetInteger(deal,DEAL_ENTRY,side) || !HistoryDealGetInteger(deal,DEAL_TIME,stamp) ||
         !HistoryDealGetInteger(deal,DEAL_REASON,reason) || !HistoryDealGetDouble(deal,DEAL_PRICE,price) ||
         !HistoryDealGetDouble(deal,DEAL_VOLUME,volume) || !HistoryDealGetDouble(deal,DEAL_PROFIT,profit) ||
         !HistoryDealGetDouble(deal,DEAL_COMMISSION,commission) || !HistoryDealGetDouble(deal,DEAL_SWAP,swap) ||
         !HistoryDealGetDouble(deal,DEAL_FEE,fee)) return false;
      pnl+=profit+commission+swap+fee;
      if(side==DEAL_ENTRY_IN) {ins++;open_time=stamp;in_volume+=volume;}
      if(side==DEAL_ENTRY_OUT) {outs++;close_time=stamp;close_price=price;why=reason;out_volume+=volume;}
   }
   if(ins!=1 || outs!=1 || open_time<=0 || close_time<open_time || active_distance<=0 ||
      MathAbs(in_volume-out_volume)>1e-8) return false;
   double r=active_direction*(close_price-active_entry)/active_distance;
   RollDay(ToUTC((datetime)close_time));daily_r+=r;
   string label=why==DEAL_REASON_SL ? "stop" : why==DEAL_REASON_TP ? "target" : halt_reason;
   FileWrite(closed,(long)ToUTC((datetime)open_time),(long)ToUTC((datetime)close_time),active_id,
      active_direction>0 ? "BUY" : "SELL",DoubleToString(active_entry,8),DoubleToString(close_price,8),
      DoubleToString(active_atr,12),DoubleToString(active_distance,12),DoubleToString(r,12),DoubleToString(pnl,2),label);
   FileFlush(closed);completed++;last_exit_m5=(datetime)((long)ToUTC((datetime)close_time)/300*300);
   Event("TRADE_CLOSED",StringFormat("position=%I64u;r=%.8f;pnl_usc=%.2f;reason=%s",active_id,r,pnl,label));
   active_id=0;active_ticket=0;return true;
}
bool CloseOwned()
{
   if(!Connected()) return false;
   for(int j=OrdersTotal()-1;j>=0;j--)
   {
      ulong ticket=OrderGetTicket(j);
      if(ticket>0 && OrderGetString(ORDER_SYMBOL)==_Symbol && OwnedMagic((ulong)OrderGetInteger(ORDER_MAGIC)))
      {
         if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)) return false;
         if(!trade.OrderDelete(ticket)) Event("CANCEL_RETRY",StringFormat("ticket=%I64u;retcode=%u",ticket,trade.ResultRetcode()));
      }
   }
   for(int j=PositionsTotal()-1;j>=0;j--)
   {
      ulong ticket=PositionGetTicket(j);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || !OwnedMagic((ulong)PositionGetInteger(POSITION_MAGIC))) continue;
      if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)) return false;
      bool sent=trade.PositionClose(ticket);
      if(!sent || trade.ResultRetcode()!=TRADE_RETCODE_DONE)
         Event("CLOSE_RETRY",StringFormat("ticket=%I64u;retcode=%u",ticket,trade.ResultRetcode()));
   }
   return OwnPositions()==0 && OwnOrders()==0;
}

void Evaluate(const bool allow_entry,const string context)
{
   int n=ArraySize(bars);if(n<100) {Halt("history_not_ready");return;}
   double atr=0,hi=-DBL_MAX,lo=DBL_MAX;
   for(int j=n-14;j<n;j++) atr+=MathMax(MidHigh(bars[j])-MidLow(bars[j]),
      MathMax(MathAbs(MidHigh(bars[j])-MidClose(bars[j-1])),MathAbs(MidLow(bars[j])-MidClose(bars[j-1]))));
   atr/=14;
   for(int j=n-21;j<n-1;j++) {hi=MathMax(hi,MidHigh(bars[j]));lo=MathMin(lo,MidLow(bars[j]));}
   QuoteBar signal=bars[n-1];
   int direction=MidClose(signal)>hi ? 1 : MidClose(signal)<lo ? -1 : 0;
   double distance=MathMax(2*atr,.5),spread=signal.ac-signal.bc,nominal=(distance+spread)*.01;
   datetime now=TimeGMT();RollDay(now);MqlDateTime t;TimeToStruct(now,t);
   MqlTick quote={};bool quote_ok=SymbolInfoTick(_Symbol,quote);
   datetime market_end=MarketEndUTC(now);
   string reason="eligible";
   if(!Connected() || !ObserveClock()) reason="account_connection_or_clock";
   else if(now<StartUTC || now>=EndUTC || entry_halt) reason="session_halted";
   else if(direction==0) reason="no_breakout";
   else if(atr<=0 || nominal>.05) reason="risk_cap";
   else if(spread>.30*atr) reason="spread";
   else if(t.day_of_week==5 && t.hour>=19) reason="friday";
   else if(Holiday(ToUTC(signal.server))) reason="holiday";
   else if(daily_r<=-2) reason="daily_halt";
   else if(OwnPositions()>0 || PositionsTotal()>0 || OrdersTotal()>0) reason="position_or_order_open";
   else if((datetime)((long)now/300*300)<=last_exit_m5) reason="exit_bar";
   else if(entry_attempts>=MaxTrades) reason="session_trade_limit";
   else if(market_end==0 || now>=market_end-120 || now>=EndUTC-120) reason="market_or_session_cutoff";
   else if(!quote_ok || MathAbs((double)(now-ToUTC(quote.time)))>3 || quote.ask<quote.bid) reason="stale_quote";
   else if(!allow_entry) reason="read_only";
   double sl=0,tp=0,risk=0,margin=0;
   if(reason=="eligible")
   {
      double anchor=direction>0 ? quote.bid : quote.ask;
      sl=NormalizeDouble(anchor-direction*distance,_Digits);tp=NormalizeDouble(anchor+direction*3*distance,_Digits);
      ENUM_ORDER_TYPE type=direction>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      double entry=direction>0 ? quote.ask : quote.bid;
      if(!OrderCalcProfit(type,_Symbol,.01,entry,sl,risk) || risk>=0 || -risk>5.000001) reason="actual_risk_cap";
      else if(!OrderCalcMargin(type,_Symbol,.01,entry,margin) || margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)) reason="margin";
      else if(MathAbs(anchor-sl)<SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point) reason="broker_stop_distance";
   }
   FileWrite(signals,(long)now,(long)ToUTC(signal.server),direction,DoubleToString(atr,12),DoubleToString(distance,12),
      DoubleToString(spread,8),DoubleToString(nominal,12),reason,context,DoubleToString(quote.bid,8),DoubleToString(quote.ask,8));
   FileFlush(signals);
   Event("DECISION",StringFormat("dir=%d;atr=%.8f;planned_usd=%.6f;reason=%s",direction,atr,nominal,reason));
   if(reason!="eligible") return;
   // Recheck the hard boundary directly before the only new-order path.
   if(Mode!=1 || !Connected() || !ObserveClock() || TimeGMT()>=EndUTC-120 ||
      FileIsExist(StopFile,FILE_COMMON) || OwnPositions()>0 || PositionsTotal()!=0 || OrdersTotal()!=0 ||
      !TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)) {Halt("final_entry_guard");return;}
   entry_attempts++;ulong magic=MagicBase+(ulong)entry_attempts;trade.SetExpertMagicNumber(magic);
   bool sent=direction>0 ? trade.Buy(.01,_Symbol,0,sl,tp,"H01 session demo") : trade.Sell(.01,_Symbol,0,sl,tp,"H01 session demo");
   Event("ORDER_RESULT",StringFormat("magic=%I64u;sent=%d;retcode=%u",magic,sent ? 1 : 0,trade.ResultRetcode()));
   if(!sent || trade.ResultRetcode()!=TRADE_RETCODE_DONE) {Halt("order_not_fully_confirmed");CloseOwned();return;}
   for(int j=0;j<PositionsTotal();j++)
   {
      ulong ticket=PositionGetTicket(j);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || (ulong)PositionGetInteger(POSITION_MAGIC)!=magic) continue;
      active_ticket=ticket;active_id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
      active_atr=atr;active_distance=distance;active_direction=direction;active_entry=PositionGetDouble(POSITION_PRICE_OPEN);
      double actual_risk=0;
      if(PositionGetDouble(POSITION_SL)<=0 || PositionGetDouble(POSITION_TP)<=0 || MathAbs(PositionGetDouble(POSITION_VOLUME)-.01)>1e-8)
      {Halt("position_protection_invalid");CloseOwned();return;}
      if(!OrderCalcProfit(direction>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL,_Symbol,.01,active_entry,PositionGetDouble(POSITION_SL),actual_risk) ||
         actual_risk>=0 || -actual_risk>5.000001) {Halt("filled_risk_exceeded");CloseOwned();return;}
      string key="S9."+(string)active_id+".";
      GlobalVariableSet(key+"atr",atr);GlobalVariableSet(key+"distance",distance);
      GlobalVariableSet(key+"entry",active_entry);GlobalVariableSet(key+"dir",direction);GlobalVariablesFlush();
      Event("ENTRY_FILLED",StringFormat("position=%I64u;dir=%d;price=%.8f;sl=%.8f;tp=%.8f",active_id,direction,active_entry,sl,tp));return;
   }
   Halt("filled_position_not_found");
}

void Receipt(const string state)
{
   int file=FileOpen(prefix+"receipt.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,',');
   if(file==INVALID_HANDLE) return;
   FileWrite(file,"key","value");FileWrite(file,"state",state);FileWrite(file,"mode",Mode);
   FileWrite(file,"identity_matches",Identity() ? 1 : 0);FileWrite(file,"connected",Connected() ? 1 : 0);
   FileWrite(file,"server_offset_seconds",offset_seconds);FileWrite(file,"own_positions",OwnPositions());
   FileWrite(file,"own_orders",OwnOrders());FileWrite(file,"audit_failed",audit_failed ? 1 : 0);
   FileWrite(file,"unreconciled_position",active_id);
   FileWrite(file,"positions",PositionsTotal());FileWrite(file,"orders",OrdersTotal());
   FileWrite(file,"balance_usc",DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2));
   FileWrite(file,"terminal_trade_allowed",(long)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED));
   FileWrite(file,"script_trade_allowed",(long)MQLInfoInteger(MQL_TRADE_ALLOWED));
   FileWrite(file,"current_market_end_utc",(long)MarketEndUTC(TimeGMT()));
   FileWrite(file,"deadline_utc",(long)EndUTC);FileWrite(file,"completed_trades",completed);
   FileWrite(file,"entry_attempts",entry_attempts);FileWrite(file,"halt_reason",halt_reason);
   FileWrite(file,"captured_session_ticks",captured_session_ticks);FileWrite(file,"quote_archive_complete",quote_archive_complete ? 1 : 0);
   FileWrite(file,"captured_utc",(long)TimeGMT());FileClose(file);
}
void CloseFiles()
{
   if(events!=INVALID_HANDLE) FileClose(events);
   if(barfile!=INVALID_HANDLE) FileClose(barfile);
   if(signals!=INVALID_HANDLE) FileClose(signals);
   if(closed!=INVALID_HANDLE) FileClose(closed);
   if(tickfile!=INVALID_HANDLE) FileClose(tickfile);
}
void OnStart()
{
   if(MQLInfoInteger(MQL_TESTER) || ExpectedLogin<=0 || MagicBase==0 || StringLen(RunId)<10 || StringLen(RunId)>35 ||
      Mode<0 || Mode>2 || _Symbol!="XAUUSD.c" || _Period!=PERIOD_H1 || MaxTrades<1 || MaxTrades>7 ||
      StringLen(StopFile)<10 || SessionLossLimitUSC<=0 || SessionLossLimitUSC>10 ||
      StartUTC<=0 || EndUTC<=StartUTC || EndUTC-StartUTC>23400)
   {
      PrintFormat("H01_SESSION_INPUT_REJECT configured_login=%d mode=%d symbol=%s period=%s start=%I64d end=%I64d span=%I64d run_length=%d stop_length=%d max_trades=%d loss=%.2f",
         ExpectedLogin>0 ? 1 : 0,Mode,_Symbol,EnumToString(_Period),(long)StartUTC,(long)EndUTC,(long)(EndUTC-StartUTC),
         StringLen(RunId),StringLen(StopFile),MaxTrades,SessionLossLimitUSC);return;
   }
   prefix="goldnix_h01_"+RunId+"_";
   events=FileOpen(prefix+"events.csv",FILE_READ|FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,',');
   if(events==INVALID_HANDLE) {PrintFormat("H01_SESSION_FILE_ERROR %d",GetLastError());return;}
   if(FileSize(events)==0) FileWrite(events,"utc_epoch","event","details");FileSeek(events,0,SEEK_END);
   for(int j=0;j<120 && !Connected() && !IsStopped();j++) Sleep(500);
   if(!Connected() || !ObserveClock() || MathAbs(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE)-1)>1e-9 ||
      MathAbs(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN)-.01)>1e-9)
   {Event("ABORT","account_clock_or_contract");Receipt("aborted");CloseFiles();return;}
   trade.SetTypeFillingBySymbol(_Symbol);trade.SetAsyncMode(false);trade.SetDeviationInPoints(20);
   if(Mode==2)
   {
      Halt("close_only_recovery");datetime until=TimeGMT()+600;
      while(!IsStopped() && TimeGMT()<until && !CloseOwned()) {Event("RECOVERING","own_position_close_retry");Sleep(2000);}
      Receipt(Connected() && OwnPositions()==0 && OwnOrders()==0 ? "recovered_flat" : "needs_reconciliation");CloseFiles();return;
   }
   if(TimeGMT()<StartUTC || TimeGMT()>=EndUTC || PositionsTotal()!=0 || OrdersTotal()!=0 || FileIsExist(StopFile,FILE_COMMON) ||
      (Mode==1 && (!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))))
   {Event("ABORT","window_account_not_flat_or_stopped");Receipt("aborted");CloseFiles();return;}
   string marker="S9.session."+RunId;
   if(Mode==1 && GlobalVariableCheck(marker)) {Event("ABORT","session_already_attempted");Receipt("aborted");CloseFiles();return;}
   barfile=FileOpen(prefix+"h1.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,',');
   signals=FileOpen(prefix+"signals.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,',');
   closed=FileOpen(prefix+"trades.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,',');
   tickfile=FileOpen(prefix+"session_ticks.bin",FILE_WRITE|FILE_BIN|FILE_COMMON|FILE_SHARE_READ);
   if(barfile==INVALID_HANDLE || signals==INVALID_HANDLE || closed==INVALID_HANDLE || tickfile==INVALID_HANDLE) {Event("ABORT","file_error");CloseFiles();return;}
   FileWrite(barfile,"epoch_seconds","bid_open","bid_high","bid_low","bid_close","ask_open","ask_high","ask_low","ask_close","ticks");
   FileWrite(signals,"decision_utc","signal_utc","direction","atr","distance","spread","nominal_usd","reason","context","bid","ask");
   FileWrite(closed,"entry_utc","exit_utc","position","dir","entry","exit","atr","distance","r_multiple","pnl_usc","reason");
   if(!Warmup()) {Event("ABORT","warmup_unavailable");Receipt("aborted");CloseFiles();return;}
   Evaluate(false,"preflight");Receipt("ready");Event("READY",StringFormat("offset=%d;deadline=%I64d;market_end=%I64d;mode=%d",offset_seconds,(long)EndUTC,(long)MarketEndUTC(TimeGMT()),Mode));
   if(Mode==0) {Event("END","read_only_check");CloseFiles();return;}
   if(GlobalVariableSet(marker,(double)TimeGMT())==0) {Event("ABORT","marker_write_failed");CloseFiles();return;}
   GlobalVariablesFlush();start_equity=AccountInfoDouble(ACCOUNT_EQUITY);last_loop=TimeGMT();
   Event("SESSION_START",StringFormat("start_equity_usc=%.2f;deadline=%I64d",start_equity,(long)EndUTC));
   datetime close_retry_since=0;
   while(!IsStopped())
   {
      datetime now=TimeGMT();
      if(!Identity()) {Halt("account_changed");break;}
      if(now-last_loop>10 || now<last_loop) Halt("host_paused_or_clock_changed");last_loop=now;
      if(!Connected() || !ObserveClock()) Halt("connection_or_clock_changed");
      if(FileIsExist(StopFile,FILE_COMMON)) Halt("stop_requested");
      if(now>=EndUTC) Halt("session_deadline");
      MqlDateTime t;TimeToStruct(now,t);
      if(t.day_of_week==5 && t.hour>=20) Halt("friday_flat");
      if(Connected() && start_equity-AccountInfoDouble(ACCOUNT_EQUITY)>=SessionLossLimitUSC) Halt("session_loss_limit");
      datetime market_end=MarketEndUTC(now);
      if(market_end>0 && now>=market_end-120) Halt("market_close_buffer");
      if(Connected() && !Reconcile()) {audit_failed=true;Halt("trade_reconciliation_error");}
      if(entry_halt)
      {
         bool flat=CloseOwned();if(flat && !Reconcile()) {audit_failed=true;Halt("trade_reconciliation_error");}
         if(close_retry_since==0) close_retry_since=now;
         if(flat && (now>=EndUTC || FileIsExist(StopFile,FILE_COMMON))) break;
         if(!flat && now-close_retry_since>=600) break;
      }
      else
      {
         MqlTick quote;
         if(SymbolInfoTick(_Symbol,quote))
         {
            datetime hour=(datetime)((long)quote.time/3600*3600);
            if(hour>current_hour)
            {
               if(hour-current_hour!=3600 || !AppendBar(current_hour)) Halt("missing_closed_hour");
               else {current_hour=hour;Evaluate(true,"new_h1");}
            }
         }
      }
      if(now-last_heartbeat>=10)
      {
         Receipt(entry_halt ? "monitoring_halted" : "running");
         Event("HEARTBEAT",StringFormat("own_positions=%d;completed=%d;attempts=%d;daily_r=%.8f;balance_usc=%.2f",OwnPositions(),completed,entry_attempts,daily_r,AccountInfoDouble(ACCOUNT_BALANCE)));
         last_heartbeat=now;
      }
      Sleep(100);
   }
   bool flat=Connected() && OwnPositions()==0 && OwnOrders()==0 && active_id==0 && !audit_failed;
   // Positions are already flat before any potentially blocking archive calls.
   if(flat)
   {
      datetime archive_end=(datetime)MathMin((double)TimeGMT(),(double)EndUTC)+offset_seconds;
      for(datetime hour=current_hour;hour<archive_end && !IsStopped();hour+=3600)
         if(!AppendBar(hour,true)) quote_archive_complete=false;
      FileFlush(tickfile);
   }
   Receipt(flat ? "complete" : "needs_reconciliation");Event("END",flat ? halt_reason : "needs_reconciliation");CloseFiles();
}
