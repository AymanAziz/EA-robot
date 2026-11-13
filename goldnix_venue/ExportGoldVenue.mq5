#property strict
// Read-only evidence. Never submits, changes, or closes an order or position.
string Number(const double value) { return DoubleToString(value, 10); }

void OnStart()
{
   for(int attempt=0; attempt<120 && !TerminalInfoInteger(TERMINAL_CONNECTED); ++attempt)
      Sleep(500);
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
   {
      Print("GOLD_VENUE: disconnected; no export produced");
      return;
   }
   const int file=FileOpen("goldnix_venue_qualification.csv",
                          FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON, ',');
   if(file==INVALID_HANDLE) return;
   FileWrite(file,"captured_utc_epoch","server","currency","equity","margin_free",
             "account_trade_mode","margin_mode","connected","symbol","base_currency",
             "profit_currency","is_custom_symbol","symbol_trade_mode","volume_min",
             "volume_step","contract_size","point","stops_level","freeze_level",
             "bid","ask","quote_server_epoch","quote_age_seconds","price_move",
             "loss_buy_one_unit","loss_sell_one_unit","margin_buy","margin_sell",
             "tick_size","tick_value_profit","tick_value_loss","swap_mode",
             "swap_long","swap_short","triple_swap_day","status",
             "error_buyprofit","error_sellprofit","error_buymargin","error_sellmargin",
             "calculation_attempts","calculation_wait_ms");
   int exported=0;
   const int total=SymbolsTotal(false);
   for(int i=0;i<total;i++)
   {
      const string symbol=SymbolName(i,false);
      // Export all actual gold contracts. Do not silently omit unknown profit currencies.
      if(SymbolInfoString(symbol,SYMBOL_CURRENCY_BASE)!="XAU") continue;
      const bool was_selected=(bool)SymbolInfoInteger(symbol,SYMBOL_SELECT);
      const bool selected=SymbolSelect(symbol,true);
      MqlTick tick={};
      bool quote_ok=false;
      for(int attempt=0; selected && attempt<20; ++attempt)
      {
         if(SymbolInfoTick(symbol,tick) && tick.bid>1 && tick.ask>=tick.bid)
         { quote_ok=true; break; }
         Sleep(100);
      }
      const double volume=SymbolInfoDouble(symbol,SYMBOL_VOLUME_MIN);
      double buy_profit=0, sell_profit=0, buy_margin=0, sell_margin=0;
      bool bp=false, sp=false, bm=false, sm=false;
      int ebp=0, esp=0, ebm=0, esm=0;
      bool economic_ready=false;
      int calculation_attempts=0;
      const ulong calculation_start=GetTickCount64();
      if(quote_ok && volume>0)
      {
         // A connected terminal can return true with zero account-currency
         // calculations until conversion quotes arrive. Do not export that as OK.
         for(int attempt=0;attempt<120 && !IsStopped();attempt++)
         {
            calculation_attempts++;
            quote_ok=SymbolInfoTick(symbol,tick) && tick.bid>1 && tick.ask>=tick.bid;
            if(quote_ok)
            {
               ebp=0; esp=0; ebm=0; esm=0;
               ResetLastError();
               bp=OrderCalcProfit(ORDER_TYPE_BUY,symbol,volume,tick.ask,tick.ask-1.0,buy_profit);
               if(!bp) ebp=GetLastError();
               ResetLastError();
               sp=OrderCalcProfit(ORDER_TYPE_SELL,symbol,volume,tick.bid,tick.bid+1.0,sell_profit);
               if(!sp) esp=GetLastError();
               ResetLastError();
               bm=OrderCalcMargin(ORDER_TYPE_BUY,symbol,volume,tick.ask,buy_margin);
               if(!bm) ebm=GetLastError();
               ResetLastError();
               sm=OrderCalcMargin(ORDER_TYPE_SELL,symbol,volume,tick.bid,sell_margin);
               if(!sm) esm=GetLastError();
               economic_ready=bp && sp && bm && sm &&
                  MathIsValidNumber(buy_profit) && MathIsValidNumber(sell_profit) &&
                  MathIsValidNumber(buy_margin) && MathIsValidNumber(sell_margin) &&
                  buy_profit<0 && sell_profit<0 && buy_margin>0 && sell_margin>0;
               if(economic_ready) break;
            }
            if(attempt<119) Sleep(250);
         }
      }
      const string status=!quote_ok ? "QUOTE_UNAVAILABLE" :
         (economic_ready ? "OK" : (bp && sp && bm && sm ? "ECONOMICS_UNAVAILABLE" : "CALCULATION_FAILED"));
      FileWrite(file,(long)TimeGMT(),AccountInfoString(ACCOUNT_SERVER),
         AccountInfoString(ACCOUNT_CURRENCY),Number(AccountInfoDouble(ACCOUNT_EQUITY)),
         Number(AccountInfoDouble(ACCOUNT_MARGIN_FREE)),
         AccountInfoInteger(ACCOUNT_TRADE_MODE),AccountInfoInteger(ACCOUNT_MARGIN_MODE),
         TerminalInfoInteger(TERMINAL_CONNECTED),symbol,
         SymbolInfoString(symbol,SYMBOL_CURRENCY_BASE),SymbolInfoString(symbol,SYMBOL_CURRENCY_PROFIT),
         SymbolInfoInteger(symbol,SYMBOL_CUSTOM),SymbolInfoInteger(symbol,SYMBOL_TRADE_MODE),
         Number(volume),Number(SymbolInfoDouble(symbol,SYMBOL_VOLUME_STEP)),
         Number(SymbolInfoDouble(symbol,SYMBOL_TRADE_CONTRACT_SIZE)),
         Number(SymbolInfoDouble(symbol,SYMBOL_POINT)),SymbolInfoInteger(symbol,SYMBOL_TRADE_STOPS_LEVEL),
         SymbolInfoInteger(symbol,SYMBOL_TRADE_FREEZE_LEVEL),Number(tick.bid),Number(tick.ask),
         (long)tick.time,(long)(TimeTradeServer()-tick.time),"1.0",
         Number(-buy_profit),Number(-sell_profit),Number(buy_margin),Number(sell_margin),
         Number(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_SIZE)),
         Number(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_PROFIT)),
         Number(SymbolInfoDouble(symbol,SYMBOL_TRADE_TICK_VALUE_LOSS)),
         SymbolInfoInteger(symbol,SYMBOL_SWAP_MODE),Number(SymbolInfoDouble(symbol,SYMBOL_SWAP_LONG)),
         Number(SymbolInfoDouble(symbol,SYMBOL_SWAP_SHORT)),
         SymbolInfoInteger(symbol,SYMBOL_SWAP_ROLLOVER3DAYS),status,ebp,esp,ebm,esm,
         calculation_attempts,(long)(GetTickCount64()-calculation_start));
      if(!was_selected && selected) SymbolSelect(symbol,false);
      exported++;
   }
   FileClose(file);
   PrintFormat("GOLD_VENUE: wrote %d gold contracts; no orders sent",exported);
}
