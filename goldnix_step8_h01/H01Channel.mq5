#property strict
#include <Trade/Trade.mqh>

// Research EA: cannot initialize outside the Strategy Tester.
input double RiskLot=0.01;
input int ChannelPeriod=20;
input int ATRPeriod=14;
input double StopATR=2.0;
input double TargetR=3.0;
input double MinDistance=0.5;
input double ReferenceAccountUSD=20.0;
input double RiskShare=0.0025;
input double USDPerPriceUnit=0.01;
input double VolCeilingATR=0.3;
input double DailyHaltR=2.0;
input double DDHaltUSD=0.0;
input int FridayFlatUTC=20;
input int FridayNoEntryUTC=19;
input int WarmupBars=100;
input ulong Magic=2026111208;
input datetime TradeFromUTC=D'2026.11.09 00:00';
input datetime WindowStartUTC=D'2026.11.02 00:00';
input datetime WindowEndUTC=D'2026.11.11 22:00';
input int ServerOffsetSeconds=7200;
input string RunId="";

struct Bar { datetime utc; double bh,bl,bc,ah,al,ac; };
Bar bars[];
Bar forming;
CTrade trade;
datetime current_hour=0, last_exit_m5=0;
long booked_day=-1;
double daily_r=0, peak_usd=0;
bool halted=false, failed=false;
ulong active_id=0;
double frozen_atr=0, distance=0, entry_price=0;
int direction=0;
long tick_count=0;
long callback_ticks=0, first_callback_msc=0, last_callback_msc=0;
int orders_sent=0, rejected=0;
int ticks_file=INVALID_HANDLE, signals_file=INVALID_HANDLE, trades_file=INVALID_HANDLE;
string prefix;

string Key(const string name) { return prefix+name; }
double MidHigh(const Bar &b) { return (b.bh+b.ah)/2; }
double MidLow(const Bar &b) { return (b.bl+b.al)/2; }
double MidClose(const Bar &b) { return (b.bc+b.ac)/2; }
datetime UTC(const datetime server) { return server-ServerOffsetSeconds; }
double EquityUSD()
{
   return AccountInfoDouble(ACCOUNT_EQUITY)/(AccountInfoString(ACCOUNT_CURRENCY)=="USC" ? 100.0 : 1.0);
}
void Persist()
{
   GlobalVariableSet(Key("day"),(double)booked_day);
   GlobalVariableSet(Key("dailyR"),daily_r);
   GlobalVariableSet(Key("halt"),halted ? 1 : 0);
   GlobalVariableSet(Key("peakUSD"),peak_usd);
   GlobalVariableSet(Key("lastExit"),(double)last_exit_m5);
}
void RollDay(const datetime stamp)
{
   long day=(long)stamp/86400;
   if(day!=booked_day) {booked_day=day;daily_r=0;Persist();}
}
bool Holiday(const datetime stamp)
{
   MqlDateTime t;TimeToStruct(stamp,t);
   if((t.mon==12 && t.day>=24 && t.day<=26) || (t.mon==1 && t.day==1)) return true;
   if(t.mon==11 && t.day_of_week==4 && t.day>=22 && t.day<=28) return true;
   // Gregorian Easter, then Good Friday, matching the Python calendar.
   int a=t.year%19,b=t.year/100,c=t.year%100,d=b/4,e=b%4,f=(b+8)/25;
   int g=(b-f+1)/3,h=(19*a+b-d-g+15)%30,i=c/4,k=c%4;
   int l=(32+2*e+2*i-h-k)%7,m=(a+11*h+22*l)/451;
   MqlDateTime easter=t;easter.mon=(h+l-7*m+114)/31;
   easter.day=(h+l-7*m+114)%31+1;easter.hour=0;easter.min=0;easter.sec=0;
   return (long)stamp/86400==(long)(StructToTime(easter)-2*86400)/86400;
}

void StartBar(const datetime server_hour,const MqlTick &tick)
{
   forming.utc=UTC(server_hour);
   forming.bh=tick.bid;forming.bl=tick.bid;forming.bc=tick.bid;
   forming.ah=tick.ask;forming.al=tick.ask;forming.ac=tick.ask;
}
void UpdateBar(const MqlTick &tick)
{
   forming.bh=MathMax(forming.bh,tick.bid);forming.bl=MathMin(forming.bl,tick.bid);forming.bc=tick.bid;
   forming.ah=MathMax(forming.ah,tick.ask);forming.al=MathMin(forming.al,tick.ask);forming.ac=tick.ask;
}
void CompleteBar()
{
   int size=ArraySize(bars);
   ArrayResize(bars,size+1);bars[size]=forming;
}

void Reconcile()
{
   if(active_id==0 || PositionSelect(_Symbol)) return;
   if(!HistorySelectByPosition(active_id)) {failed=true;return;}
   ulong closing=0,opening=0;
   long opening_time=0,closing_time=0,reason=0;
   double closing_price=0;
   for(int j=0;j<HistoryDealsTotal();j++)
   {
      ulong deal=HistoryDealGetTicket(j);
      long side=0,stamp=0,why=0;
      double price=0;
      // Capture checked values while this deal is selected. A later ticketed
      // read returned ERR_TRADE_DEAL_NOT_FOUND in the installed tester build.
      ResetLastError();
      if(deal==0 || !HistoryDealGetInteger(deal,DEAL_ENTRY,side) ||
         !HistoryDealGetInteger(deal,DEAL_TIME,stamp) ||
         !HistoryDealGetInteger(deal,DEAL_REASON,why) ||
         !HistoryDealGetDouble(deal,DEAL_PRICE,price))
      {
         PrintFormat("H01_DEAL_AUDIT_FAILED ticket=%I64u error=%d",deal,GetLastError());
         failed=true;return;
      }
      if(side==DEAL_ENTRY_IN) {opening=deal;opening_time=stamp;}
      if(side==DEAL_ENTRY_OUT) {closing=deal;closing_time=stamp;closing_price=price;reason=why;}
   }
   if(opening==0 || closing==0) return;
   datetime entry_utc=UTC((datetime)opening_time),exit_utc=UTC((datetime)closing_time);
   if(entry_utc<TradeFromUTC || entry_utc>=WindowEndUTC || exit_utc<entry_utc || exit_utc>WindowEndUTC ||
      distance<=0 || closing_price<=0)
   {
      failed=true;Print("H01_DEAL_AUDIT_INVALID_FIELDS");return;
   }
   double price=closing_price;
   double r=direction*(price-entry_price)/distance;
   RollDay(exit_utc);daily_r+=r;
   string label=reason==DEAL_REASON_SL ? "stop" : reason==DEAL_REASON_TP ? "target" : "expert_close";
   MqlDateTime t;TimeToStruct(exit_utc,t);
   if(label=="expert_close" && t.day_of_week==5 && t.hour>=FridayFlatUTC) label="friday_flat";
   if(label=="expert_close" && halted) label="drawdown_halt";
   FileWrite(trades_file,(long)entry_utc,(long)exit_utc,
             direction>0 ? "BUY" : "SELL",DoubleToString(entry_price,8),DoubleToString(price,8),
             DoubleToString(frozen_atr,12),DoubleToString(distance,12),DoubleToString(r,12),label,
             (long)opening,(long)closing);
   FileFlush(trades_file);
   last_exit_m5=(datetime)((long)exit_utc/300*300);active_id=0;Persist();
}

void Evaluate(const MqlTick &tick)
{
   int n=ArraySize(bars);
   if(n<MathMax(WarmupBars,MathMax(ChannelPeriod+1,ATRPeriod+1))) return;
   const Bar signal=bars[n-1];
   double atr=0,hi=-DBL_MAX,lo=DBL_MAX;
   for(int j=n-ATRPeriod;j<n;j++)
      atr+=MathMax(MidHigh(bars[j])-MidLow(bars[j]),
           MathMax(MathAbs(MidHigh(bars[j])-MidClose(bars[j-1])),
                   MathAbs(MidLow(bars[j])-MidClose(bars[j-1]))));
   atr/=ATRPeriod;
   for(int j=n-1-ChannelPeriod;j<n-1;j++) {hi=MathMax(hi,MidHigh(bars[j]));lo=MathMin(lo,MidLow(bars[j]));}
   int side=MidClose(signal)>hi ? 1 : MidClose(signal)<lo ? -1 : 0;
   double spread=signal.ac-signal.bc;
   double stop_distance=MathMax(StopATR*atr,MinDistance);
   datetime stamp=UTC(tick.time);
   MqlDateTime t;TimeToStruct(stamp,t);
   string skip="eligible";
   if(stamp<TradeFromUTC) skip="warmup_window";
   else if(side==0) skip="no_breakout";
   else if(atr<=0) skip="invalid_atr";
   else if((stop_distance+spread)*USDPerPriceUnit>ReferenceAccountUSD*RiskShare) skip="risk_cap";
   else if(spread>VolCeilingATR*atr) skip="spread";
   else if(t.day_of_week==5 && t.hour>=FridayNoEntryUTC) skip="friday";
   else if(Holiday(signal.utc)) skip="holiday";
   else if(PositionSelect(_Symbol)) skip="position_open";
   else if((datetime)((long)stamp/300*300)<=last_exit_m5) skip="exit_bar";
   else if(daily_r<=-DailyHaltR) skip="daily_halt";
   else if(halted || failed) skip="halt";
   FileWrite(signals_file,(long)stamp,(long)signal.utc,side,DoubleToString(atr,12),
             DoubleToString(stop_distance,12),DoubleToString(spread,8),skip);
   if(skip!="eligible") return;
   double anchor=side>0 ? tick.bid : tick.ask;
   double sl=NormalizeDouble(anchor-side*stop_distance,_Digits);
   double tp=NormalizeDouble(anchor+side*TargetR*stop_distance,_Digits);
   orders_sent++;
   bool sent=side>0 ? trade.Buy(RiskLot,_Symbol,0,sl,tp,"H01 tester") :
                      trade.Sell(RiskLot,_Symbol,0,sl,tp,"H01 tester");
   if(!sent || trade.ResultRetcode()!=TRADE_RETCODE_DONE || !PositionSelect(_Symbol))
   {
      rejected++;PrintFormat("H01_ORDER_REJECTED code=%u",trade.ResultRetcode());return;
   }
   active_id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
   frozen_atr=atr;distance=stop_distance;direction=side;entry_price=PositionGetDouble(POSITION_PRICE_OPEN);
   string ticket=Key((string)active_id+"_");
   GlobalVariableSet(ticket+"atr",atr);GlobalVariableSet(ticket+"distance",distance);
   GlobalVariableSet(ticket+"entry",entry_price);GlobalVariableSet(ticket+"direction",direction);
   Persist();
}

int OnInit()
{
   // Two bounded, explicit intervals. February 2024 is independently clock-checked.
   const bool known_interval=(WindowStartUTC>=D'2026.11.02 00:00' && WindowEndUTC<=D'2026.11.11 22:00') ||
                             (WindowStartUTC>=D'2024.01.22 00:00' && WindowEndUTC<=D'2024.02.29 22:00');
   if(!MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_OPTIMIZATION) || _Period!=PERIOD_H1 ||
      _Symbol!="XAUUSD.c" || StringLen(RunId)<10 || StringLen(RunId)>28 ||
      ChannelPeriod<1 || ATRPeriod<1 || WarmupBars<ChannelPeriod+1 ||
      StopATR<=0 || TargetR<=0 || MinDistance<=0 || RiskLot!=0.01 ||
      ReferenceAccountUSD<=0 || RiskShare<=0 || USDPerPriceUnit!=0.01 ||
      DailyHaltR<=0 || DDHaltUSD<0 || VolCeilingATR<0 ||
      MathAbs(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE)-1.0)>1e-9 ||
      (AccountInfoString(ACCOUNT_CURRENCY)!="USD" && AccountInfoString(ACCOUNT_CURRENCY)!="USC") ||
      WindowStartUTC>=TradeFromUTC || TradeFromUTC>=WindowEndUTC || ServerOffsetSeconds!=7200 || !known_interval)
      return INIT_PARAMETERS_INCORRECT;
   prefix="H01_"+RunId+"_";
   ticks_file=FileOpen(prefix+"ticks.bin",FILE_WRITE|FILE_BIN|FILE_COMMON);
   signals_file=FileOpen(prefix+"signals.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   trades_file=FileOpen(prefix+"trades.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(ticks_file==INVALID_HANDLE || signals_file==INVALID_HANDLE || trades_file==INVALID_HANDLE) return INIT_FAILED;
   FileWrite(signals_file,"entry_utc","signal_utc","direction","atr","distance","spread","reason");
   FileWrite(trades_file,"entry_utc","exit_utc","dir","entry","exit","atr","distance","r_multiple","exit_reason","entry_deal","exit_deal");
   trade.SetExpertMagicNumber(Magic);trade.SetTypeFillingBySymbol(_Symbol);trade.SetAsyncMode(false);
   if(GlobalVariableCheck(Key("day")))
   {
      booked_day=(long)GlobalVariableGet(Key("day"));daily_r=GlobalVariableGet(Key("dailyR"));
      halted=GlobalVariableGet(Key("halt"))!=0;peak_usd=GlobalVariableGet(Key("peakUSD"));
      last_exit_m5=(datetime)GlobalVariableGet(Key("lastExit"));
   }
   else peak_usd=EquityUSD();
   if(PositionSelect(_Symbol))
   {
      if((ulong)PositionGetInteger(POSITION_MAGIC)!=Magic) return INIT_FAILED;
      active_id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
      string ticket=Key((string)active_id+"_");
      if(!GlobalVariableCheck(ticket+"atr")) return INIT_FAILED;
      frozen_atr=GlobalVariableGet(ticket+"atr");distance=GlobalVariableGet(ticket+"distance");
      entry_price=GlobalVariableGet(ticket+"entry");direction=(int)GlobalVariableGet(ticket+"direction");
   }
   return INIT_SUCCEEDED;
}

void OnTick()
{
   MqlTick tick;if(!SymbolInfoTick(_Symbol,tick)) return;
   datetime stamp=UTC(tick.time);
   if(stamp<WindowStartUTC) return;
   if(stamp>=WindowEndUTC) {failed=true;ExpertRemove();return;}
   if(tick.bid<=0 || tick.ask<tick.bid) {failed=true;return;}
   // Export the actual processed price path incrementally. Generated tick history
   // otherwise becomes unavailable after the tester's 128,000-tick cache rolls.
   FileWriteLong(ticks_file,tick.time_msc);FileWriteDouble(ticks_file,tick.bid);FileWriteDouble(ticks_file,tick.ask);
   tick_count++;
   callback_ticks++;
   if(first_callback_msc==0) first_callback_msc=tick.time_msc;
   last_callback_msc=tick.time_msc;
   Reconcile();RollDay(stamp);
   peak_usd=MathMax(peak_usd,EquityUSD());
   if(DDHaltUSD>0 && peak_usd-EquityUSD()>=DDHaltUSD) {halted=true;Persist();}
   MqlDateTime t;TimeToStruct(stamp,t);
   // Broker SL/TP orders are active continuously. These closes also run every tick.
   if(PositionSelect(_Symbol) && (halted || (t.day_of_week==5 && t.hour>=FridayFlatUTC)))
   {
      if(!trade.PositionClose(_Symbol)) {failed=true;Print("H01_CLOSE_FAILED");}
      Reconcile();
   }
   datetime hour=(datetime)((long)tick.time/3600*3600);
   if(current_hour==0) {current_hour=hour;StartBar(hour,tick);return;}
   if(hour==current_hour) {UpdateBar(tick);return;}
   CompleteBar();
   current_hour=hour;
   StartBar(hour,tick);
   Evaluate(tick);
}

void Finish()
{
   Reconcile();
   if(current_hour>0) {CompleteBar();current_hour=0;}
   int file=FileOpen(prefix+"meta.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(file!=INVALID_HANDLE)
   {
      FileWrite(file,"key","value");FileWrite(file,"tester",(long)MQLInfoInteger(MQL_TESTER));
      FileWrite(file,"failed",failed ? 1 : 0);FileWrite(file,"ticks",tick_count);
      FileWrite(file,"callback_ticks",callback_ticks);
      FileWrite(file,"first_callback_server_msc",first_callback_msc);
      FileWrite(file,"last_callback_server_msc",last_callback_msc);
      FileWrite(file,"h1_bars",ArraySize(bars));FileWrite(file,"orders_sent",orders_sent);
      FileWrite(file,"rejected_orders",rejected);FileWrite(file,"unreconciled_position",(long)active_id);
      FileWrite(file,"server_offset_seconds",ServerOffsetSeconds);
      FileWrite(file,"terminal_trade_allowed",(long)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED));
      FileWrite(file,"expert_trade_allowed",(long)MQLInfoInteger(MQL_TRADE_ALLOWED));
      FileWrite(file,"completed",1);FileClose(file);
   }
}
void OnDeinit(const int reason)
{
   if(StringLen(prefix)>0) Finish();
   if(ticks_file!=INVALID_HANDLE) FileClose(ticks_file);
   if(signals_file!=INVALID_HANDLE) FileClose(signals_file);
   if(trades_file!=INVALID_HANDLE) FileClose(trades_file);
}
