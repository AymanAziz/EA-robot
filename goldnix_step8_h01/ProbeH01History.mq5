#property strict
// Read-only, bounded historical data probe. Never sends or modifies an order.
input long ExpectedLogin=0;
input string RunId="";

bool RightAccount()
{
   return ExpectedLogin>0 && AccountInfoInteger(ACCOUNT_LOGIN)==ExpectedLogin &&
      AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO &&
      AccountInfoString(ACCOUNT_SERVER)=="JustMarkets-Demo6" &&
      AccountInfoString(ACCOUNT_CURRENCY)=="USC" && TerminalInfoInteger(TERMINAL_CONNECTED);
}
void OnStart()
{
   if(ExpectedLogin<=0 || StringLen(RunId)<10) return;
   for(int i=0;i<120 && !RightAccount();i++) Sleep(500);
   if(!RightAccount() || _Symbol!="XAUUSD.c" || PositionsTotal()!=0 || OrdersTotal()!=0 ||
      TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || MQLInfoInteger(MQL_TRADE_ALLOWED)) return;
   MqlRates rates[];
   int n=-1,error=0;
   for(int attempt=0;attempt<120;attempt++)
   {
      ResetLastError();
      n=CopyRates(_Symbol,PERIOD_H1,D'2024.01.22 00:00',D'2024.02.29 23:59:59',rates);
      error=GetLastError();
      if(n>0 && error==0) break;
      Sleep(500);
   }
   int file=FileOpen("H01_"+RunId+"_h1.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(file!=INVALID_HANDLE)
   {
      FileWrite(file,"server_epoch","bid_open","bid_high","bid_low","bid_close","tick_volume");
      for(int i=0;i<n;i++) FileWrite(file,(long)rates[i].time,DoubleToString(rates[i].open,8),
         DoubleToString(rates[i].high,8),DoubleToString(rates[i].low,8),DoubleToString(rates[i].close,8),rates[i].tick_volume);
      FileClose(file);
   }
   MqlTick ticks[];
   ResetLastError();
   const int count=CopyTicksRange(_Symbol,ticks,COPY_TICKS_ALL,
      (ulong)D'2024.02.15 00:00'*1000,(ulong)D'2024.02.15 23:59:59'*1000+999);
   const int tick_error=GetLastError();
   file=FileOpen("H01_"+RunId+"_ticks.bin",FILE_WRITE|FILE_BIN|FILE_COMMON);
   if(file!=INVALID_HANDLE)
   {
      for(int i=0;i<count;i++)
      {
         FileWriteLong(file,ticks[i].time_msc);FileWriteDouble(file,ticks[i].bid);FileWriteDouble(file,ticks[i].ask);
      }
      FileClose(file);
   }
   file=FileOpen("H01_"+RunId+"_meta.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(file==INVALID_HANDLE) return;
   FileWrite(file,"key","value");FileWrite(file,"identity_matches",RightAccount() ? 1 : 0);
   FileWrite(file,"h1_count",n);FileWrite(file,"h1_error",error);
   FileWrite(file,"h1_first_server",n>0 ? (long)rates[0].time : 0);
   FileWrite(file,"h1_last_server",n>0 ? (long)rates[n-1].time : 0);
   FileWrite(file,"series_server_first",SeriesInfoInteger(_Symbol,PERIOD_H1,SERIES_SERVER_FIRSTDATE));
   FileWrite(file,"tick_count",count);FileWrite(file,"tick_error",tick_error);
   FileWrite(file,"tick_first_server_msc",count>0 ? ticks[0].time_msc : 0);
   FileWrite(file,"tick_last_server_msc",count>0 ? ticks[count-1].time_msc : 0);
   FileWrite(file,"positions",PositionsTotal());FileWrite(file,"orders",OrdersTotal());
   FileWrite(file,"balance_usc",DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2));
   FileWrite(file,"terminal_trade_allowed",(long)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED));
   FileWrite(file,"script_trade_allowed",(long)MQLInfoInteger(MQL_TRADE_ALLOWED));
   FileWrite(file,"completed",1);FileClose(file);
}
