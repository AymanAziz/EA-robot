#property strict
#property version "1.00"
#property description "Automatic M5 capture and bounded DEMO trading while MT5 is open."
#include <Trade/Trade.mqh>
#include "AutoPolicy.mqh"

input long ExpectedLogin=0;
input bool EnableDemoTrading=false;

const string ROOT="GoldnixAutoM5Demo";
AutoState state={};
CTrade trade;
QuoteBar bars[];
MqlRates warm_rates[];
int lock_file=INVALID_HANDLE,events=INVALID_HANDLE,barfile=INVALID_HANDLE,signals=INVALID_HANDLE,closed=INVALID_HANDLE,tickfile=INVALID_HANDLE;
int offset_seconds=0,warm_index=-1;
bool state_loaded=false,state_broken=false,ready=false,was_connected=false,instance_owner=false,lock_verified=false;
datetime current_bar=0,last_timer=0,stable_since=0,last_status=0;
long capture_cursor=0,captured_ticks=0;
int capture_seen=0;
string run_folder,display_state="starting",last_decision="none";

bool Identity()
{
   return ExpectedLogin>0 && AccountInfoInteger(ACCOUNT_LOGIN)==ExpectedLogin &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
      AccountInfoString(ACCOUNT_SERVER)=="JustMarkets-Demo6" &&
      AccountInfoString(ACCOUNT_CURRENCY)=="USC" && _Symbol=="XAUUSD.c";
}
bool Connected() {return Identity() && TerminalInfoInteger(TERMINAL_CONNECTED);}
bool CanTrade() {return Connected() && EnableDemoTrading && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED);}
datetime ToUTC(const datetime server) {return server-offset_seconds;}
void Event(const string name,const string detail)
{
   if(events!=INVALID_HANDLE) {FileWrite(events,(long)TimeGMT(),name,detail);FileFlush(events);}
}
int OwnPositions()
{
   int n=0;
   for(int j=PositionsTotal()-1;j>=0;j--)
      if(PositionGetTicket(j)>0 && PositionGetString(POSITION_SYMBOL)==_Symbol && AutoOwnedMagic(PositionGetInteger(POSITION_MAGIC))) n++;
   return n;
}
int OwnOrders()
{
   int n=0;
   for(int j=OrdersTotal()-1;j>=0;j--)
      if(OrderGetTicket(j)>0 && OrderGetString(ORDER_SYMBOL)==_Symbol && AutoOwnedMagic(OrderGetInteger(ORDER_MAGIC))) n++;
   return n;
}
bool ReadCheckpoint(const string path,AutoState &s)
{
   int f=FileOpen(path,FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ,',');
   if(f==INVALID_HANDLE) return false;
   string k1=FileReadString(f),payload=FileReadString(f),k2=FileReadString(f),sum=FileReadString(f),k3=FileReadString(f),commit=FileReadString(f);
   bool ended=FileIsEnding(f);FileClose(f);
   return k1=="payload" && k2=="checksum" && k3=="commit" && commit=="GNA1" && ended &&
      sum==(string)(long)StateChecksum(payload) && ParseState(payload,ExpectedLogin,s);
}
bool Persist()
{
   if(!state_loaded || state_broken) return false;
   state.sequence++;
   string path=ROOT+"\\state.csv",temp=ROOT+"\\state.next.csv",payload=StatePayload(state);
   int f=FileOpen(temp,FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(f==INVALID_HANDLE) {state_broken=true;return false;}
   bool wrote=FileWrite(f,"payload",payload)>0 && FileWrite(f,"checksum",(long)StateChecksum(payload))>0 && FileWrite(f,"commit","GNA1")>0;
   FileFlush(f);FileClose(f);
   AutoState verify={};
   if(!wrote || !ReadCheckpoint(temp,verify) || StatePayload(verify)!=payload || !FileMove(temp,0,path,0|FILE_REWRITE) ||
      !ReadCheckpoint(path,verify) || StatePayload(verify)!=payload)
   {state_broken=true;Event("STATE_ERROR","checkpoint_not_confirmed");return false;}
   return true;
}
void Fatal(const string reason)
{
   if(!state.fatal) {state.fatal=true;state.fatal_reason=reason;Event("AUDIT_HALT",reason);Persist();}
}
bool LoadState()
{
   string path=ROOT+"\\state.csv",marker=ROOT+"\\commissioned";
   if(FileIsExist(path,0))
   {
      if(!ReadCheckpoint(path,state)) {state_broken=true;Event("STATE_ERROR","invalid_checkpoint");return false;}
      state_loaded=true;
   }
   else
   {
      if(FileIsExist(marker,0) || OwnPositions()>0 || OwnOrders()>0)
      {state_broken=true;Event("STATE_ERROR","missing_checkpoint_or_untracked_exposure");return false;}
      state.owner=ExpectedLogin;state.day=MalaysiaDay(TimeGMT());state.base_equity=AccountInfoDouble(ACCOUNT_EQUITY);
      state_loaded=true;if(!Persist()) return false;
   }
   if(!FileIsExist(marker,0))
   {
      int f=FileOpen(marker,FILE_WRITE|FILE_TXT|FILE_ANSI);
      if(f==INVALID_HANDLE) {state_broken=true;return false;}
      FileWriteString(f,"GNA1: missing or corrupt state must block new entries\n");FileFlush(f);FileClose(f);
   }
   if(state.pending_magic!=0) {state.recover=true;if(!Persist()) return false;}
   Event("STATE_LOADED",StringFormat("day=%I64d;attempts=%d;daily_r=%.8f;pending=%d",state.day,state.attempts,state.realized_r,state.pending_magic!=0));
   return true;
}
bool ObserveClock()
{
   long observed=(long)(TimeTradeServer()-TimeGMT());int rounded=(int)MathRound((double)observed/3600)*3600;
   if((rounded!=7200 && rounded!=10800) || MathAbs((double)observed-rounded)>5) return false;
   if(offset_seconds!=rounded)
   {
      Event("CLOCK_OFFSET",StringFormat("seconds=%d",rounded));offset_seconds=rounded;
      ready=false;warm_index=-1;capture_cursor=0;capture_seen=0;
   }
   return true;
}
datetime MarketEndUTC(const datetime now)
{
   datetime server=now+offset_seconds,midnight=(datetime)((long)server/86400*86400);
   for(int previous=0;previous<=1;previous++)
   {
      datetime day=midnight-previous*86400;MqlDateTime t;TimeToStruct(day,t);
      for(uint j=0;j<20;j++)
      {
         datetime from=0,to=0;if(!SymbolInfoSessionTrade(_Symbol,(ENUM_DAY_OF_WEEK)t.day_of_week,j,from,to)) break;
         long begin=(long)from,end=(long)to;if(begin==0 && end==0) continue;if(end<=begin) end+=86400;
         if(server>=day+begin && server<day+end) return ToUTC(day+end);
      }
   }
   return 0;
}
bool Holiday(const datetime stamp)
{
   MqlDateTime t;TimeToStruct(stamp,t);
   if((t.mon==12 && t.day>=24 && t.day<=26) || (t.mon==1 && t.day==1)) return true;
   if(t.mon==11 && t.day_of_week==4 && t.day>=22 && t.day<=28) return true;
   int a=t.year%19,b=t.year/100,c=t.year%100,d=b/4,e=b%4,f=(b+8)/25;
   int g=(b-f+1)/3,h=(19*a+b-d-g+15)%30,i=c/4,k=c%4;
   int l=(32+2*e+2*i-h-k)%7,m=(a+11*h+22*l)/451;
   MqlDateTime easter=t;easter.mon=(h+l-7*m+114)/31;easter.day=(h+l-7*m+114)%31+1;easter.hour=0;easter.min=0;easter.sec=0;
   return (long)stamp/86400==(long)(StructToTime(easter)-2*86400)/86400;
}
bool CloseOwned()
{
   if(OwnPositions()==0 && OwnOrders()==0) return true;
   if(!CanTrade()) return false;
   for(int j=OrdersTotal()-1;j>=0;j--)
   {
      ulong ticket=OrderGetTicket(j);
      if(ticket>0 && OrderGetString(ORDER_SYMBOL)==_Symbol && AutoOwnedMagic(OrderGetInteger(ORDER_MAGIC))) trade.OrderDelete(ticket);
   }
   for(int j=PositionsTotal()-1;j>=0;j--)
   {
      ulong ticket=PositionGetTicket(j);
      if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || !AutoOwnedMagic(PositionGetInteger(POSITION_MAGIC))) continue;
      if(!trade.PositionClose(ticket) || trade.ResultRetcode()!=TRADE_RETCODE_DONE)
         Event("CLOSE_RETRY",StringFormat("position=%I64u;retcode=%u",ticket,trade.ResultRetcode()));
   }
   return OwnPositions()==0 && OwnOrders()==0;
}
bool Reconcile()
{
   if(!state_loaded || state_broken) return false;
   if(OwnOrders()>0 || OwnPositions()>1) {Fatal("unexpected_owned_exposure");CloseOwned();return false;}
   if(state.pending_magic==0)
   {
      if(OwnPositions()>0) {Fatal("untracked_position");CloseOwned();return false;}
      return true;
   }
   if(OwnPositions()>0)
   {
      for(int j=0;j<PositionsTotal();j++)
      {
         ulong ticket=PositionGetTicket(j);
         if(ticket==0 || PositionGetString(POSITION_SYMBOL)!=_Symbol || !AutoOwnedMagic(PositionGetInteger(POSITION_MAGIC))) continue;
         if(PositionGetInteger(POSITION_MAGIC)!=state.pending_magic) {Fatal("position_intent_mismatch");CloseOwned();return false;}
         ulong id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
         if(state.position_id==0) {state.position_id=id;if(!Persist()) return false;}
         if(state.position_id!=id) {Fatal("position_identifier_mismatch");CloseOwned();return false;}
         double entry=PositionGetDouble(POSITION_PRICE_OPEN),sl=PositionGetDouble(POSITION_SL),risk=0;
         ENUM_ORDER_TYPE type=state.pending_direction>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
         if(sl<=0 || PositionGetDouble(POSITION_TP)<=0 || MathAbs(PositionGetDouble(POSITION_VOLUME)-.01)>1e-8 ||
            !OrderCalcProfit(type,_Symbol,.01,entry,sl,risk) || risk>=0 || -risk>5.000001)
         {Fatal("position_protection_or_risk_invalid");CloseOwned();return false;}
         if(state.recover || state.fatal || state.daily_halt) CloseOwned();
         return OwnPositions()>0 ? true : Reconcile();
      }
      return false;
   }
   if(state.position_id==0)
   {
      if(!HistorySelect((datetime)(state.pending_server-86400),TimeTradeServer()+60)) return false;
      for(int j=0;j<HistoryDealsTotal();j++)
      {
         ulong deal=HistoryDealGetTicket(j);long magic=0,side=0,id=0;
         if(deal==0 || !HistoryDealGetInteger(deal,DEAL_MAGIC,magic) || !HistoryDealGetInteger(deal,DEAL_ENTRY,side)) return false;
         if(magic==state.pending_magic && side==DEAL_ENTRY_IN)
         {
            if(!HistoryDealGetInteger(deal,DEAL_POSITION_ID,id)) return false;
            state.position_id=(ulong)id;break;
         }
      }
      if(state.position_id==0)
      {
         if(TimeTradeServer()-state.pending_server<30) return false;
         Fatal("unconfirmed_order_intent");return false;
      }
      if(!Persist()) return false;
   }
   if(!HistorySelectByPosition(state.position_id)) return false;
   int ins=0,outs=0;double in_volume=0,out_volume=0,entry=0,exit_notional=0,pnl=0;long open_time=0,close_time=0;
   for(int j=0;j<HistoryDealsTotal();j++)
   {
      ulong deal=HistoryDealGetTicket(j);long side=0,stamp=0;double price=0,volume=0,profit=0,commission=0,swap=0,fee=0;
      if(deal==0 || !HistoryDealGetInteger(deal,DEAL_ENTRY,side) || !HistoryDealGetInteger(deal,DEAL_TIME,stamp) ||
         !HistoryDealGetDouble(deal,DEAL_PRICE,price) || !HistoryDealGetDouble(deal,DEAL_VOLUME,volume) ||
         !HistoryDealGetDouble(deal,DEAL_PROFIT,profit) || !HistoryDealGetDouble(deal,DEAL_COMMISSION,commission) ||
         !HistoryDealGetDouble(deal,DEAL_SWAP,swap) || !HistoryDealGetDouble(deal,DEAL_FEE,fee)) return false;
      pnl+=profit+commission+swap+fee;
      if(side==DEAL_ENTRY_IN) {ins++;entry=price;open_time=stamp;in_volume+=volume;}
      if(side==DEAL_ENTRY_OUT || side==DEAL_ENTRY_OUT_BY) {outs++;close_time=MathMax(close_time,stamp);out_volume+=volume;exit_notional+=price*volume;}
   }
   if(ins==0 || outs==0) return false; // Broker history may lag a confirmed close.
   if(ins!=1 || MathAbs(in_volume-.01)>1e-8 || MathAbs(out_volume-in_volume)>1e-8 || close_time<open_time)
   {Fatal("incomplete_broker_history");return false;}
   double exit_price=exit_notional/out_volume,r=state.pending_direction*(exit_price-entry)/state.pending_distance;
   if(FileWrite(closed,(long)ToUTC((datetime)open_time),(long)ToUTC((datetime)close_time),state.position_id,
      state.pending_direction>0 ? "BUY" : "SELL",DoubleToString(entry,8),DoubleToString(exit_price,8),
      DoubleToString(state.pending_atr,12),DoubleToString(state.pending_distance,12),DoubleToString(r,12),DoubleToString(pnl,2))==0)
   {Fatal("trade_log_write_failed");return false;}
   FileFlush(closed);
   Event("TRADE_CLOSED",StringFormat("position=%I64u;r=%.8f;pnl_usc=%.2f",state.position_id,r,pnl));
   state.realized_r+=r;state.last_exit_bar=(long)ToUTC((datetime)close_time)/300*300;
   state.pending_magic=0;state.pending_server=0;state.pending_direction=0;state.pending_atr=0;state.pending_distance=0;state.position_id=0;state.recover=false;
   return Persist();
}
bool CaptureTicks()
{
   MqlTick quote;if(!SymbolInfoTick(_Symbol,quote) || quote.time_msc<=0) return false;
   if(capture_cursor==0) {capture_cursor=quote.time_msc;capture_seen=0;}
   if(quote.time_msc<capture_cursor) return false;
   MqlTick ticks[];ResetLastError();
   int count=CopyTicksRange(_Symbol,ticks,COPY_TICKS_ALL,(ulong)capture_cursor,(ulong)quote.time_msc);
   int error=GetLastError();if(count<0 || error!=0) return false;
   long group=0;int seen=0;
   for(int j=0;j<count;j++)
   {
      if(ticks[j].bid<=0 || ticks[j].ask<ticks[j].bid) return false;
      if(ticks[j].time_msc!=group) {group=ticks[j].time_msc;seen=0;}seen++;
      if(group==capture_cursor && seen<=capture_seen) continue;
      if(FileWriteLong(tickfile,group)==0 || FileWriteDouble(tickfile,ticks[j].bid)==0 || FileWriteDouble(tickfile,ticks[j].ask)==0)
      {Fatal("quote_archive_write_failed");return false;}
      captured_ticks++;
   }
   if(count>0 && group==capture_cursor && seen<capture_seen) return false;
   if(count>0) {capture_cursor=group;capture_seen=seen;}
   FileFlush(tickfile);return true;
}
bool AppendBar(const datetime server_open)
{
   MqlTick ticks[];ResetLastError();
   int count=CopyTicksRange(_Symbol,ticks,COPY_TICKS_ALL,(ulong)server_open*1000,(ulong)(server_open+300)*1000-1);
   int error=GetLastError();
   if(count<=0 || error!=0) {Event("DATA_WAIT",StringFormat("bar=%I64d;count=%d;error=%d",(long)server_open,count,error));return false;}
   QuoteBar bar;bar.server=server_open;bar.bo=ticks[0].bid;bar.ao=ticks[0].ask;bar.bh=-DBL_MAX;bar.ah=-DBL_MAX;bar.bl=DBL_MAX;bar.al=DBL_MAX;bar.ticks=count;
   for(int j=0;j<count;j++)
   {
      if(ticks[j].bid<=0 || ticks[j].ask<ticks[j].bid) return false;
      bar.bh=MathMax(bar.bh,ticks[j].bid);bar.bl=MathMin(bar.bl,ticks[j].bid);bar.bc=ticks[j].bid;
      bar.ah=MathMax(bar.ah,ticks[j].ask);bar.al=MathMin(bar.al,ticks[j].ask);bar.ac=ticks[j].ask;
   }
   int n=ArraySize(bars);
   if(n>=200) {for(int j=1;j<n;j++) bars[j-1]=bars[j];n--;ArrayResize(bars,n);}
   ArrayResize(bars,n+1);bars[n]=bar;
   if(FileWrite(barfile,(long)ToUTC(server_open),DoubleToString(bar.bo,8),DoubleToString(bar.bh,8),DoubleToString(bar.bl,8),DoubleToString(bar.bc,8),
      DoubleToString(bar.ao,8),DoubleToString(bar.ah,8),DoubleToString(bar.al,8),DoubleToString(bar.ac,8),count)==0) return false;
   FileFlush(barfile);
   return true;
}
void Evaluate(const bool allow_entry,const string context)
{
   int direction=0;double atr=0,distance=0,spread=0,nominal=0;
   if(!SignalStats(bars,direction,atr,distance,spread,nominal)) {Fatal("invalid_signal_inputs");return;}
   datetime now=TimeGMT();long signal_utc=(long)ToUTC(bars[ArraySize(bars)-1].server);
   MqlDateTime t;TimeToStruct(now,t);MqlTick quote={};bool quote_ok=SymbolInfoTick(_Symbol,quote);
   datetime market_end=MarketEndUTC(now);
   string reason=RiskReason(state,AccountInfoDouble(ACCOUNT_EQUITY));
   if(reason=="")
   {
      if(!Connected() || !ObserveClock()) reason="account_connection_or_clock";
      else if(MalaysiaDay(now)!=state.day) reason="clock_risk_day_mismatch";
      else if(state_broken) reason="checkpoint_error";
      else if(direction==0) reason="no_breakout";
      else if(nominal>.05) reason="risk_cap";
      else if(spread>.30*atr) reason="spread";
      else if(t.day_of_week==5 && t.hour>=19) reason="friday";
      else if(Holiday((datetime)signal_utc)) reason="holiday";
      else if(state.pending_magic!=0 || PositionsTotal()>0 || OrdersTotal()>0) reason="position_or_order_open";
      else if((long)now/300*300<=state.last_exit_bar) reason="exit_bar";
      else if(market_end==0 || now>=market_end-120) reason="market_closed_or_buffer";
      else if(!quote_ok || MathAbs((double)(now-ToUTC(quote.time)))>3 || quote.ask<quote.bid) reason="stale_quote";
      else if(!allow_entry) reason="startup_resync_or_stale_bar";
      else if(!CanTrade()) reason="capture_only_trading_disabled";
      else reason="eligible";
   }
   double sl=0,tp=0,risk=0,margin=0;
   if(reason=="eligible")
   {
      double anchor=direction>0 ? quote.bid : quote.ask,entry=direction>0 ? quote.ask : quote.bid;
      sl=NormalizeDouble(anchor-direction*distance,_Digits);tp=NormalizeDouble(anchor+direction*3*distance,_Digits);
      ENUM_ORDER_TYPE type=direction>0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
      if(!OrderCalcProfit(type,_Symbol,.01,entry,sl,risk) || risk>=0 || -risk>5.000001) reason="actual_risk_cap";
      else if(!OrderCalcMargin(type,_Symbol,.01,entry,margin) || margin>AccountInfoDouble(ACCOUNT_MARGIN_FREE)) reason="margin";
      else if(MathAbs(anchor-sl)<SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL)*_Point) reason="broker_stop_distance";
   }
   last_decision=reason;
   if(FileWrite(signals,(long)now,signal_utc,direction,DoubleToString(atr,12),DoubleToString(distance,12),DoubleToString(spread,8),
      DoubleToString(nominal,12),reason,context,DoubleToString(quote.bid,8),DoubleToString(quote.ask,8))==0)
   {Fatal("signal_log_write_failed");return;}
   FileFlush(signals);
   Event("DECISION",StringFormat("dir=%d;reason=%s;planned_usd=%.6f",direction,reason,nominal));
   if(reason!="eligible") return;
   // Durable intent consumes an attempt before the only order-send path.
   if(!CanTrade() || !ObserveClock() || state_broken || MalaysiaDay(TimeGMT())!=state.day || RiskReason(state,AccountInfoDouble(ACCOUNT_EQUITY))!="" ||
      PositionsTotal()!=0 || OrdersTotal()!=0 || MarketEndUTC(TimeGMT())<=TimeGMT()+120 || TimeGMT()>=signal_utc+310) return;
   state.attempts++;state.pending_magic=AUTO_MAGIC_BASE+state.day*100+state.attempts;state.pending_server=(long)TimeTradeServer();
   state.pending_direction=direction;state.pending_atr=atr;state.pending_distance=distance;state.position_id=0;
   if(!Persist()) return;
   if(!CanTrade() || !ObserveClock() || MalaysiaDay(TimeGMT())!=state.day || MarketEndUTC(TimeGMT())<=TimeGMT()+120 || TimeGMT()>=signal_utc+310)
   {
      // No request has been sent. Keep the consumed attempt, cancel its intent.
      state.pending_magic=0;state.pending_server=0;state.pending_direction=0;state.pending_atr=0;state.pending_distance=0;
      Persist();Event("ORDER_SKIPPED","execution guard changed while checkpointing");return;
   }
   trade.SetExpertMagicNumber((ulong)state.pending_magic);
   bool sent=direction>0 ? trade.Buy(.01,_Symbol,0,sl,tp,"Goldnix auto M5 demo") : trade.Sell(.01,_Symbol,0,sl,tp,"Goldnix auto M5 demo");
   Event("ORDER_RESULT",StringFormat("magic=%I64d;sent=%d;retcode=%u",state.pending_magic,sent,trade.ResultRetcode()));
   if(!sent || trade.ResultRetcode()!=TRADE_RETCODE_DONE) {Fatal("order_not_fully_confirmed");CloseOwned();return;}
   Reconcile();
}
bool WarmupStep()
{
   if(warm_index<0)
   {
      if(CopyRates(_Symbol,PERIOD_M5,1,100,warm_rates)!=100) return false;
      ArrayResize(bars,0);warm_index=0;Event("WARMUP","100 completed M5 bars");
   }
   for(int j=0;j<5 && warm_index<100;j++)
   {
      if(!Connected() || !AppendBar(warm_rates[warm_index].time)) {warm_index=-1;return false;}
      warm_index++;
   }
   if(warm_index<100) return false;
   if(warm_rates[99].time!=iTime(_Symbol,PERIOD_M5,1)) {warm_index=-1;return false;}
   current_bar=iTime(_Symbol,PERIOD_M5,0);if(current_bar<=0) return false;
   state.last_signal=MathMax(state.last_signal,(long)ToUTC(warm_rates[99].time));
   if(!Persist()) return false;
   Evaluate(false,"startup_or_resync");ready=true;Event("READY","capture active; wait for next new M5 bar");return true;
}
void Status()
{
   string permission=CanTrade() ? "DEMO orders enabled" : "Capture only / trading disabled";
   Comment("GOLDNIX AUTO M5 | DEMO\n",display_state,"\nNo operating-hours cutoff | M5 signals\n",permission,
      "\n0.01 lot | $0.05 planned-risk cap | attempts ",state.attempts,"/7\nLast decision: ",last_decision,
      "\nCaptured ticks: ",captured_ticks," | Open positions: ",OwnPositions(),"\nMalaysia: ",TimeToString(TimeGMT()+8*3600,TIME_DATE|TIME_SECONDS));
   if(TimeGMT()-last_status<5) return;last_status=TimeGMT();
   int f=FileOpen(ROOT+"\\status.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ,',');
   if(f==INVALID_HANDLE) return;
   FileWrite(f,"key","value");FileWrite(f,"state",display_state);FileWrite(f,"captured_utc",(long)TimeGMT());
   FileWrite(f,"run_folder",run_folder);FileWrite(f,"chart_id",ChartID());FileWrite(f,"timeframe","M5");FileWrite(f,"bar_seconds",300);
   FileWrite(f,"identity_matches",Identity());FileWrite(f,"connected",Connected());FileWrite(f,"data_ready",ready);
   FileWrite(f,"exclusive_lock_verified",lock_verified);
   FileWrite(f,"demo_trading_configured",EnableDemoTrading);FileWrite(f,"trade_permission",CanTrade());
   FileWrite(f,"terminal_trade_allowed",(long)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED));
   FileWrite(f,"expert_trade_allowed",(long)MQLInfoInteger(MQL_TRADE_ALLOWED));
   FileWrite(f,"market_end_utc",(long)MarketEndUTC(TimeGMT()));FileWrite(f,"server_offset_seconds",offset_seconds);
   FileWrite(f,"daily_attempts",state.attempts);FileWrite(f,"daily_r",DoubleToString(state.realized_r,12));
   FileWrite(f,"daily_loss_halt",state.daily_halt);FileWrite(f,"audit_halt",state.fatal);FileWrite(f,"audit_reason",state.fatal_reason);
   FileWrite(f,"state_broken",state_broken);FileWrite(f,"state_sequence",state.sequence);FileWrite(f,"last_signal_utc",state.last_signal);
   FileWrite(f,"pending_magic",state.pending_magic);FileWrite(f,"own_positions",OwnPositions());FileWrite(f,"positions",PositionsTotal());FileWrite(f,"orders",OrdersTotal());
   FileWrite(f,"balance_usc",DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2));FileWrite(f,"captured_ticks",captured_ticks);
   FileWrite(f,"capture_cursor_msc",capture_cursor);FileWrite(f,"capture_boundary_count",capture_seen);FileWrite(f,"last_decision",last_decision);
   FileWrite(f,"data_path",TerminalInfoString(TERMINAL_DATA_PATH));FileWrite(f,"fixed_start_hour","none");FileWrite(f,"fixed_stop_hour","none");FileClose(f);
}
void OnTimer()
{
   datetime now=TimeGMT();
   bool paused=last_timer>0 && (now-last_timer>10 || now<last_timer);last_timer=now;
   bool connected=Connected() && ObserveClock();
   if(!connected || paused)
   {
      if(was_connected || paused)
      {
         Event("PAUSE",paused ? "host_paused_or_clock_changed" : "connection_or_identity_unavailable");
         if(state_loaded && state.pending_magic!=0) {state.recover=true;Persist();}
      }
      was_connected=false;stable_since=0;ready=false;warm_index=-1;capture_cursor=0;capture_seen=0;
      display_state="Waiting for connection / clock synchronization";Status();return;
   }
   if(!was_connected) {was_connected=true;stable_since=now;Event("CONNECTED","fresh data required before new entries");}
   if(MathAbs(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE)-1)>1e-9 || MathAbs(SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN)-.01)>1e-9)
   {display_state="Blocked: demo contract changed";Status();return;}
   trade.SetTypeFillingBySymbol(_Symbol);
   if(!state_loaded && !state_broken) LoadState();
   if(state_broken) {CloseOwned();display_state="Blocked: checkpoint requires review";Status();return;}
   if(state.base_equity-AccountInfoDouble(ACCOUNT_EQUITY)>=AUTO_LOSS_USC && !state.daily_halt)
   {state.daily_halt=true;Persist();Event("RISK_HALT","10 USC daily equity loss");}
   datetime market_end=MarketEndUTC(now);MqlDateTime t;TimeToStruct(now,t);
   bool broker_buffer=market_end>0 && now>=market_end-120;
   bool friday_flat=t.day_of_week==5 && t.hour>=20;
   if(state.daily_halt || state.fatal || broker_buffer || friday_flat) CloseOwned();
   bool reconciled=Reconcile();
   if(reconciled && ResetDayIfFlat(state,MalaysiaDay(now),AccountInfoDouble(ACCOUNT_EQUITY),OwnPositions(),OwnOrders()))
   {Persist();Event("NEW_RISK_DAY","flat; daily budget reset");}
   bool captured=CaptureTicks();
   if(!captured) {ready=false;warm_index=-1;display_state="Capturing paused: tick history synchronizing";Status();return;}
   if(now-stable_since<5) {display_state="Connected: verifying stable feed";Status();return;}
   if(!ready)
   {
      display_state="Capturing / warming completed M5 bars";WarmupStep();Status();return;
   }
   datetime next=iTime(_Symbol,PERIOD_M5,0);
   if(next>current_bar)
   {
      if(next-current_bar!=300 || !AppendBar(current_bar))
      {ready=false;warm_index=-1;Event("RESYNC","bar gap; no catch-up entries");}
      else
      {
         long stamp=(long)ToUTC(current_bar);bool fresh=FreshSignal(state,stamp,(long)TimeGMT(),false);
         current_bar=next;
         if(stamp>state.last_signal)
         {state.last_signal=stamp;if(Persist()) Evaluate(fresh && reconciled,"new_m5");}
      }
   }
   string risk=RiskReason(state,AccountInfoDouble(ACCOUNT_EQUITY));
   if(state_broken) display_state="Blocked: checkpoint requires review";
   else if(state.fatal) display_state="Capturing | audit halt: "+state.fatal_reason;
   else if(MalaysiaDay(now)!=state.day) display_state="Capturing | clock/risk-day mismatch";
   else if(market_end==0) display_state="Capturing | market closed: waiting for quotes";
   else if(broker_buffer || friday_flat) display_state="Capturing | broker/Friday close buffer";
   else if(risk!="") display_state="Capturing | "+risk;
   else if(!reconciled || state.recover) display_state="Capturing | reconciling previous position";
   else display_state="CAPTURING | M5 analysis active";
   Status();
}
void CloseFiles()
{
   if(events!=INVALID_HANDLE) FileClose(events);if(barfile!=INVALID_HANDLE) FileClose(barfile);
   if(signals!=INVALID_HANDLE) FileClose(signals);if(closed!=INVALID_HANDLE) FileClose(closed);
   if(tickfile!=INVALID_HANDLE) FileClose(tickfile);if(lock_file!=INVALID_HANDLE) FileClose(lock_file);
   events=INVALID_HANDLE;barfile=INVALID_HANDLE;signals=INVALID_HANDLE;closed=INVALID_HANDLE;tickfile=INVALID_HANDLE;lock_file=INVALID_HANDLE;
}
int OnInit()
{
   if(MQLInfoInteger(MQL_TESTER) || ExpectedLogin<=0 || _Symbol!="XAUUSD.c") return INIT_PARAMETERS_INCORRECT;
   FolderCreate(ROOT,0);FolderCreate(ROOT+"\\runs",0);
   // No sharing flags: one owner per terminal data folder, released on exit.
   lock_file=FileOpen(ROOT+"\\owner.lock",FILE_READ|FILE_WRITE|FILE_BIN);
   if(lock_file==INVALID_HANDLE) {Print("GOLDNIX_AUTO duplicate instance blocked");return INIT_FAILED;}
   instance_owner=true;
   int probe=FileOpen(ROOT+"\\owner.lock",FILE_READ|FILE_WRITE|FILE_BIN);
   if(probe!=INVALID_HANDLE) {FileClose(probe);CloseFiles();Print("GOLDNIX_AUTO exclusive lock unavailable");return INIT_FAILED;}
   lock_verified=true;
   run_folder=ROOT+"\\runs\\AUTO_"+(string)(long)TimeGMT()+"_"+(string)GetTickCount64();FolderCreate(run_folder,0);
   int flags=FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ;
   events=FileOpen(run_folder+"\\events.csv",flags,',');barfile=FileOpen(run_folder+"\\m5.csv",flags,',');
   signals=FileOpen(run_folder+"\\signals.csv",flags,',');closed=FileOpen(run_folder+"\\trades.csv",flags,',');
   tickfile=FileOpen(run_folder+"\\ticks.bin",FILE_WRITE|FILE_BIN|FILE_SHARE_READ);
   if(events==INVALID_HANDLE || barfile==INVALID_HANDLE || signals==INVALID_HANDLE || closed==INVALID_HANDLE || tickfile==INVALID_HANDLE)
   {CloseFiles();return INIT_FAILED;}
   FileWrite(events,"utc_epoch","event","details");
   FileWrite(barfile,"epoch_seconds","bid_open","bid_high","bid_low","bid_close","ask_open","ask_high","ask_low","ask_close","ticks");
   FileWrite(signals,"decision_utc","signal_utc","direction","atr","distance","spread","nominal_usd","reason","context","bid","ask");
   FileWrite(closed,"entry_utc","exit_utc","position","dir","entry","exit","atr","distance","r_multiple","pnl_usc");
   trade.SetTypeFillingBySymbol(_Symbol);trade.SetAsyncMode(false);trade.SetDeviationInPoints(20);
   if(!EventSetTimer(1)) {CloseFiles();return INIT_FAILED;}
   Event("INIT","persistent EA; no operating-hours cutoff; no startup entry");Status();return INIT_SUCCEEDED;
}
void OnDeinit(const int reason)
{
   if(!instance_owner) return;
   EventKillTimer();Event("DEINIT",StringFormat("reason=%d;server SL/TP retained; restart requires reconciliation",reason));
   if(state_loaded && !state_broken) Persist();
   ready=false;display_state="Stopped: MT5 closed or EA removed";last_status=0;Status();Comment("");CloseFiles();
}
