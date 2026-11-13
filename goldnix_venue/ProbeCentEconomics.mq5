#property strict
// Read-only diagnostic: calculation calls only; no order requests are submitted.
#define OnStart ExportVenue
#include "ExportGoldVenue.mq5"
#undef OnStart

void OnStart()
{
   for(int i=0;i<120 && !TerminalInfoInteger(TERMINAL_CONNECTED);i++) Sleep(500);
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
   { Print("CENT_PROBE: disconnected; no diagnostic produced"); return; }
   const int catalog=FileOpen("goldnix_cent_symbol_catalog.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(catalog==INVALID_HANDLE) return;
   FileWrite(catalog,"symbol","base","profit","margin_currency","selected","visible","calc_mode");
   for(int i=0;i<SymbolsTotal(false);i++)
   {
      const string s=SymbolName(i,false);
      FileWrite(catalog,s,SymbolInfoString(s,SYMBOL_CURRENCY_BASE),
         SymbolInfoString(s,SYMBOL_CURRENCY_PROFIT),SymbolInfoString(s,SYMBOL_CURRENCY_MARGIN),
         SymbolInfoInteger(s,SYMBOL_SELECT),SymbolInfoInteger(s,SYMBOL_VISIBLE),
         SymbolInfoInteger(s,SYMBOL_TRADE_CALC_MODE));
   }
   FileClose(catalog);
   const int file=FileOpen("goldnix_cent_probe.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(file==INVALID_HANDLE) return;
   FileWrite(file,"captured_utc_epoch","elapsed_seconds","server","account_currency",
      "currency_digits","leverage","symbol","synchronized","bid","ask","volume","price_move",
      "buy_profit_ok","buy_profit_error","buy_profit","sell_profit_ok","sell_profit_error","sell_profit",
      "buy_margin_ok","buy_margin_error","buy_margin","sell_margin_ok","sell_margin_error","sell_margin",
      "tick_value_profit","tick_value_loss","initial_margin","maintenance_margin");
   string symbols[]={"XAUUSD.c","EURUSD.c"};
   bool selected_before[2];
   for(int i=0;i<2;i++)
   {
      selected_before[i]=(bool)SymbolInfoInteger(symbols[i],SYMBOL_SELECT);
      SymbolSelect(symbols[i],true);
   }
   int seconds[]={0,5,15,30,60};
   const ulong start=GetTickCount64();
   for(int sample=0;sample<ArraySize(seconds) && !IsStopped();sample++)
   {
      while(GetTickCount64()-start<(ulong)(seconds[sample]*1000) && !IsStopped()) Sleep(100);
      for(int i=0;i<2;i++)
      {
         const string s=symbols[i];
         MqlTick tick={};
         if(!SymbolInfoTick(s,tick) || tick.bid<=0 || tick.ask<tick.bid) continue;
         double volumes[]={SymbolInfoDouble(s,SYMBOL_VOLUME_MIN),1.0,100.0};
         double moves[]={i==0 ? 1.0 : 0.0001,i==0 ? 100.0 : 0.01};
         for(int v=0;v<ArraySize(volumes);v++)
         {
            if(volumes[v]>SymbolInfoDouble(s,SYMBOL_VOLUME_MAX)) continue;
            for(int m=0;m<ArraySize(moves);m++)
            {
               if(tick.ask<=moves[m]) continue;
               double bp=0,sp=0,bm=0,sm=0;
               ResetLastError(); bool bp_ok=OrderCalcProfit(ORDER_TYPE_BUY,s,volumes[v],tick.ask,tick.ask-moves[m],bp); int bp_err=GetLastError();
               ResetLastError(); bool sp_ok=OrderCalcProfit(ORDER_TYPE_SELL,s,volumes[v],tick.bid,tick.bid+moves[m],sp); int sp_err=GetLastError();
               ResetLastError(); bool bm_ok=OrderCalcMargin(ORDER_TYPE_BUY,s,volumes[v],tick.ask,bm); int bm_err=GetLastError();
               ResetLastError(); bool sm_ok=OrderCalcMargin(ORDER_TYPE_SELL,s,volumes[v],tick.bid,sm); int sm_err=GetLastError();
               FileWrite(file,(long)TimeGMT(),Number((GetTickCount64()-start)/1000.0),
                  AccountInfoString(ACCOUNT_SERVER),AccountInfoString(ACCOUNT_CURRENCY),
                  AccountInfoInteger(ACCOUNT_CURRENCY_DIGITS),AccountInfoInteger(ACCOUNT_LEVERAGE),s,
                  SymbolIsSynchronized(s),Number(tick.bid),Number(tick.ask),Number(volumes[v]),Number(moves[m]),
                  bp_ok,bp_err,Number(bp),sp_ok,sp_err,Number(sp),bm_ok,bm_err,Number(bm),sm_ok,sm_err,Number(sm),
                  Number(SymbolInfoDouble(s,SYMBOL_TRADE_TICK_VALUE_PROFIT)),Number(SymbolInfoDouble(s,SYMBOL_TRADE_TICK_VALUE_LOSS)),
                  Number(SymbolInfoDouble(s,SYMBOL_MARGIN_INITIAL)),Number(SymbolInfoDouble(s,SYMBOL_MARGIN_MAINTENANCE)));
            }
         }
      }
      FileFlush(file);
   }
   FileClose(file);
   ExportVenue();
   for(int i=0;i<2;i++) if(!selected_before[i]) SymbolSelect(symbols[i],false);
   Print("CENT_PROBE: completed 60-second calculation diagnostic; no orders sent");
}
