#property strict

// Read-only reconciliation of an explicitly identified demo execution batch.
input string VerificationRunId="";
input ulong VerificationMagicBase=0;
input int VerificationMaxTrades=0;
input ENUM_TIMEFRAMES VerificationTimeframe=PERIOD_M1;
input long VerificationExpectedLogin=0;

void OnStart()
{
   if(StringLen(VerificationRunId)<10 || VerificationMagicBase==0 ||
      VerificationMaxTrades<1 || VerificationMaxTrades>60) return;
   for(int i=0;i<120 && !TerminalInfoInteger(TERMINAL_CONNECTED);i++) Sleep(500);
   Sleep(5000);
   const int f=FileOpen("goldnix_batch_restore_"+VerificationRunId+".csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(f==INVALID_HANDLE) return;
   FileWrite(f,"key","value");
   FileWrite(f,"captured_utc_epoch",(long)TimeGMT());
   FileWrite(f,"server",AccountInfoString(ACCOUNT_SERVER));
   FileWrite(f,"currency",AccountInfoString(ACCOUNT_CURRENCY));
   FileWrite(f,"account_trade_mode",AccountInfoInteger(ACCOUNT_TRADE_MODE));
   FileWrite(f,"identity_matches",VerificationExpectedLogin>0 && AccountInfoInteger(ACCOUNT_LOGIN)==VerificationExpectedLogin ? 1 : 0);
   FileWrite(f,"connected",TerminalInfoInteger(TERMINAL_CONNECTED));
   FileWrite(f,"terminal_trade_allowed",TerminalInfoInteger(TERMINAL_TRADE_ALLOWED));
   FileWrite(f,"mql_trade_allowed",MQLInfoInteger(MQL_TRADE_ALLOWED));
   FileWrite(f,"positions",PositionsTotal());
   FileWrite(f,"orders",OrdersTotal());
   FileWrite(f,"balance_usc",DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),2));
   const bool history_ok=HistorySelect(TimeCurrent()-86400,TimeCurrent()+60);
   FileWrite(f,"history_selected",history_ok?1:0);
   ulong position_ids[];
   int ins=0,outs=0;
   double pnl=0,entry_volume=0,exit_volume=0;
   if(history_ok)
   {
      for(int i=0;i<HistoryDealsTotal();i++)
      {
         const ulong d=HistoryDealGetTicket(i);
         const ulong magic=(ulong)HistoryDealGetInteger(d,DEAL_MAGIC);
         if(magic<=VerificationMagicBase || magic>VerificationMagicBase+(ulong)VerificationMaxTrades ||
            HistoryDealGetString(d,DEAL_SYMBOL)!="XAUUSD.c" ||
            HistoryDealGetInteger(d,DEAL_ENTRY)!=DEAL_ENTRY_IN) continue;
         const ulong id=(ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID);
         bool found=false;
         for(int j=0;j<ArraySize(position_ids);j++) if(position_ids[j]==id) found=true;
         if(!found) {const int n=ArraySize(position_ids);ArrayResize(position_ids,n+1);position_ids[n]=id;}
      }
      const int deals=FileOpen("goldnix_batch_history_"+VerificationRunId+".csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
      if(deals!=INVALID_HANDLE)
         FileWrite(deals,"deal","position","magic","entry","symbol","volume","price","profit","commission","swap","fee","time_server_epoch","reason");
      for(int i=0;i<HistoryDealsTotal();i++)
      {
         const ulong d=HistoryDealGetTicket(i);
         const ulong id=(ulong)HistoryDealGetInteger(d,DEAL_POSITION_ID);
         bool found=false;
         for(int j=0;j<ArraySize(position_ids);j++) if(position_ids[j]==id) found=true;
         if(!found) continue;
         const long entry=HistoryDealGetInteger(d,DEAL_ENTRY);
         const double volume=HistoryDealGetDouble(d,DEAL_VOLUME);
         if(entry==DEAL_ENTRY_IN) {ins++;entry_volume+=volume;}
         if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY) {outs++;exit_volume+=volume;}
         pnl+=HistoryDealGetDouble(d,DEAL_PROFIT)+HistoryDealGetDouble(d,DEAL_COMMISSION)+HistoryDealGetDouble(d,DEAL_SWAP)+HistoryDealGetDouble(d,DEAL_FEE);
         if(deals!=INVALID_HANDLE)
            FileWrite(deals,d,id,HistoryDealGetInteger(d,DEAL_MAGIC),entry,HistoryDealGetString(d,DEAL_SYMBOL),
               DoubleToString(volume,2),DoubleToString(HistoryDealGetDouble(d,DEAL_PRICE),5),
               DoubleToString(HistoryDealGetDouble(d,DEAL_PROFIT),2),DoubleToString(HistoryDealGetDouble(d,DEAL_COMMISSION),2),
               DoubleToString(HistoryDealGetDouble(d,DEAL_SWAP),2),DoubleToString(HistoryDealGetDouble(d,DEAL_FEE),2),
               HistoryDealGetInteger(d,DEAL_TIME),EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(d,DEAL_REASON)));
      }
      if(deals!=INVALID_HANDLE) FileClose(deals);
   }
   FileWrite(f,"matching_positions",ArraySize(position_ids));
   FileWrite(f,"entry_deals",ins);
   FileWrite(f,"exit_deals",outs);
   FileWrite(f,"entry_volume",DoubleToString(entry_volume,2));
   FileWrite(f,"exit_volume",DoubleToString(exit_volume,2));
   FileWrite(f,"net_pnl_usc",DoubleToString(pnl,2));
   FileClose(f);
   MqlRates rates[];
   int copied=0;
   for(int i=0;i<20 && copied<1;i++)
   {copied=CopyRates("XAUUSD.c",VerificationTimeframe,0,150,rates);if(copied<1) Sleep(500);}
   const int bars=FileOpen("goldnix_batch_bars_"+VerificationRunId+".csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(bars!=INVALID_HANDLE)
   {
      FileWrite(bars,"bar_server_epoch","open","high","low","close","tick_volume","spread_points");
      for(int i=0;i<copied;i++) FileWrite(bars,(long)rates[i].time,DoubleToString(rates[i].open,5),DoubleToString(rates[i].high,5),DoubleToString(rates[i].low,5),DoubleToString(rates[i].close,5),rates[i].tick_volume,rates[i].spread);
      FileClose(bars);
   }
   Print("DEMO_BATCH_VERIFY: read-only account and position-history reconciliation saved");
}
