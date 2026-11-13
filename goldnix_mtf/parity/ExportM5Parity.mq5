#property strict

// Read-only parity export. No trade functions, imports or expert attachment.
input long ExpectedLogin=0;
input string RunId="";

bool RightAccount()
{
   return ExpectedLogin>0 && AccountInfoInteger(ACCOUNT_LOGIN)==ExpectedLogin &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
      AccountInfoString(ACCOUNT_SERVER)=="JustMarkets-Demo6" &&
      AccountInfoString(ACCOUNT_CURRENCY)=="USC" && TerminalInfoInteger(TERMINAL_CONNECTED);
}

int LastCompletedShift(const ENUM_TIMEFRAMES timeframe,const datetime available)
{
   int shift=iBarShift(_Symbol,timeframe,available,false);
   if(shift<0) return -1;
   while(iTime(_Symbol,timeframe,shift)>0 &&
         iTime(_Symbol,timeframe,shift)+PeriodSeconds(timeframe)>available) shift++;
   return iTime(_Symbol,timeframe,shift)>0 ? shift : -1;
}

bool ExportSeries(const ENUM_TIMEFRAMES timeframe,const int period,const string label)
{
   const int count=1000;
   const int handle=(timeframe==PERIOD_M5 ? iATR(_Symbol,timeframe,period) :
                     iMA(_Symbol,timeframe,period,0,MODE_EMA,PRICE_CLOSE));
   if(handle==INVALID_HANDLE) return false;
   MqlRates rates[];
   ArraySetAsSeries(rates,true);
   bool ready=false;
   int copied=0;
   for(int attempt=0;attempt<120;attempt++)
   {
      copied=CopyRates(_Symbol,timeframe,1,count+period+1,rates);
      if(copied==count+period+1 && BarsCalculated(handle)>count+period) {ready=true;break;}
      Sleep(500);
   }
   if(!ready)
   {
      PrintFormat("GOLDNIX_PARITY_HISTORY: timeframe=%s copied=%d calculated=%d error=%d",
                  EnumToString(timeframe),copied,BarsCalculated(handle),GetLastError());
      IndicatorRelease(handle);return false;
   }
   const int file=FileOpen("goldnix_mtf_parity_"+RunId+"_"+label+".csv",
                           FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(file==INVALID_HANDLE) {IndicatorRelease(handle);return false;}
   FileWrite(file,"server_epoch","open","high","low","close","indicator","compare",
                  "last_completed_h1_open","last_completed_m15_open");
   int written=0;
   for(int shift=count;shift>=1;shift--)
   {
      double value[1];
      if(CopyBuffer(handle,0,shift,1,value)!=1) continue;
      if(!MathIsValidNumber(value[0]) || value[0]<=0 || value[0]==EMPTY_VALUE) continue;
      const int index=shift-1;
      const datetime close_time=rates[index].time+PeriodSeconds(timeframe);
      int hi=-1,mi=-1;
      if(timeframe==PERIOD_M5)
      {
         hi=LastCompletedShift(PERIOD_H1,close_time);
         mi=LastCompletedShift(PERIOD_M15,close_time);
      }
      FileWrite(file,(long)rates[index].time,DoubleToString(rates[index].open,8),
         DoubleToString(rates[index].high,8),DoubleToString(rates[index].low,8),
         DoubleToString(rates[index].close,8),DoubleToString(value[0],10),shift<=200 ? 1 : 0,
         hi>=0 ? (long)iTime(_Symbol,PERIOD_H1,hi) : 0,
         mi>=0 ? (long)iTime(_Symbol,PERIOD_M15,mi) : 0);
      written++;
   }
   FileFlush(file);FileClose(file);IndicatorRelease(handle);
   // Refuse a snapshot spanning a rollover while indicator shifts were read.
   return written==count && iTime(_Symbol,timeframe,1)==rates[0].time;
}

void OnStart()
{
   if(StringLen(RunId)<10 || ExpectedLogin<=0) return;
   for(int attempt=0;attempt<120 && !RightAccount();attempt++) Sleep(500);
   if(!RightAccount() || _Symbol!="XAUUSD.c" || _Period!=PERIOD_M5 ||
      TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || MQLInfoInteger(MQL_TRADE_ALLOWED) ||
      PositionsTotal()!=0 || OrdersTotal()!=0) return;
   // Warm the higher-timeframe histories before M5 availability lookups.
   const bool h1=ExportSeries(PERIOD_H1,50,"H1");
   const bool m15=ExportSeries(PERIOD_M15,20,"M15");
   const bool m5=ExportSeries(PERIOD_M5,14,"M5");
   const int file=FileOpen("goldnix_mtf_parity_"+RunId+"_meta.csv",
                          FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(file==INVALID_HANDLE) return;
   FileWrite(file,"key","value");
   FileWrite(file,"identity_matches_expected",RightAccount() ? 1 : 0);
   FileWrite(file,"h1_complete",h1 ? 1 : 0);
   FileWrite(file,"m15_complete",m15 ? 1 : 0);
   FileWrite(file,"m5_complete",m5 ? 1 : 0);
   FileWrite(file,"terminal_trade_allowed",(long)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED));
   FileWrite(file,"script_trade_allowed",(long)MQLInfoInteger(MQL_TRADE_ALLOWED));
   FileWrite(file,"positions",PositionsTotal());FileWrite(file,"orders",OrdersTotal());
   FileWrite(file,"capture_utc_epoch",(long)TimeGMT());
   FileWrite(file,"observed_server_offset_seconds",(long)(TimeTradeServer()-TimeGMT()));
   FileFlush(file);FileClose(file);
}
