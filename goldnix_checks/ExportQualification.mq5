#property strict
// Read-only symbol qualification. No order placement or position management.
void OnStart()
{
   for(int attempt=0; attempt<120 && !TerminalInfoInteger(TERMINAL_CONNECTED); ++attempt)
      Sleep(500);
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
   {
      Print("QUALIFICATION: disconnected; no export produced");
      return;
   }
   const int file=FileOpen("goldnix_qualification.csv",
                          FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(file==INVALID_HANDLE) return;
   FileWrite(file,"server_time","server","currency","balance","equity","margin_free",
             "symbol","base_currency","volume_min","volume_step","contract_size","tick_size","tick_value_loss",
             "bid","ask","quote_server_time","loss_one_price_unit","margin_buy","margin_sell",
             "status");
   int exported=0;
   const int total=SymbolsTotal(false);
   for(int i=0;i<total;i++)
   {
      const string symbol=SymbolName(i,false);
      string upper=symbol;
      StringToUpper(upper);
      if(StringFind(upper,"XAUUSD")<0 && StringFind(upper,"GOLD")<0) continue;
      // Exclude equity names containing GOLD and instruments with other quote currencies.
      if(SymbolInfoString(symbol,SYMBOL_CURRENCY_PROFIT)!="USD") continue;
      if(SymbolInfoString(symbol,SYMBOL_CURRENCY_BASE)!="XAU") continue;
      const bool was_selected=(bool)SymbolInfoInteger(symbol,SYMBOL_SELECT);
      if(!SymbolSelect(symbol,true)) continue;
      MqlTick tick={};
      bool quote_ok=false;
      for(int attempt=0;attempt<20;attempt++)
      {
         if(SymbolInfoTick(symbol,tick) && tick.bid>0 && tick.ask>=tick.bid)
         { quote_ok=true; break; }
         Sleep(100);
      }
      const double volume=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      double profit=0, margin_buy=0, margin_sell=0;
      const bool ok=quote_ok && volume>0
         && OrderCalcProfit(ORDER_TYPE_BUY,symbol,volume,tick.ask,tick.ask-1.0,profit)
         && OrderCalcMargin(ORDER_TYPE_BUY,symbol,volume,tick.ask,margin_buy)
         && OrderCalcMargin(ORDER_TYPE_SELL,symbol,volume,tick.bid,margin_sell);
      FileWrite(file,TimeToString(TimeCurrent(),TIME_DATE|TIME_SECONDS),
                AccountInfoString(ACCOUNT_SERVER),AccountInfoString(ACCOUNT_CURRENCY),
                DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE),8),
                DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),8),
                DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE),8),symbol,
                SymbolInfoString(symbol,SYMBOL_CURRENCY_BASE),
                DoubleToString(volume,8),
                DoubleToString(SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP),8),
                DoubleToString(SymbolInfoDouble(symbol,SYMBOL_TRADE_CONTRACT_SIZE),8),
                DoubleToString(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE),8),
                DoubleToString(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_LOSS),8),
                DoubleToString(tick.bid,8),DoubleToString(tick.ask,8),
                TimeToString(tick.time,TIME_DATE|TIME_SECONDS),
                DoubleToString(-profit,8),DoubleToString(margin_buy,8),
                DoubleToString(margin_sell,8),ok?"OK":"CALCULATION_FAILED");
      if(!was_selected) SymbolSelect(symbol,false);
      exported++;
   }
   FileClose(file);
   PrintFormat("QUALIFICATION: wrote %d rows; no orders sent",exported);
}
