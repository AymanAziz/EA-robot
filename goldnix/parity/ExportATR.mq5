#property script_show_inputs

input int    ATRPeriod   = 14;
input int    WarmupBars  = 300;
input int    CompareBars = 200;
input string OutputFile = "goldnix_atr_parity.csv";

void OnStart()
{
   if(ATRPeriod < 2 || WarmupBars < ATRPeriod || CompareBars < 1)
   {
      Print("Invalid inputs: require ATRPeriod >= 2, WarmupBars >= ATRPeriod, CompareBars >= 1");
      return;
   }

   const int total_bars = WarmupBars + CompareBars;
   const int handle = iATR(_Symbol, PERIOD_H1, ATRPeriod);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("iATR handle creation failed: %d", GetLastError());
      return;
   }

   const int required_bars = total_bars + ATRPeriod;
   for(int attempt = 0; attempt < 120 && BarsCalculated(handle) < required_bars; ++attempt)
      Sleep(500);

   if(BarsCalculated(handle) < required_bars)
   {
      PrintFormat("Not enough calculated ATR bars: have %d, need at least %d",
                  BarsCalculated(handle), required_bars);
      IndicatorRelease(handle);
      return;
   }

   const int file = FileOpen(OutputFile, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(file == INVALID_HANDLE)
   {
      PrintFormat("Cannot open %s: %d", OutputFile, GetLastError());
      IndicatorRelease(handle);
      return;
   }

   FileWrite(file,
             "account_server",
             "symbol",
             "server_time",
             "server_utc_offset_seconds",
             "high",
             "low",
             "close",
             "mt5_atr",
             "compare");

   const string account_server = AccountInfoString(ACCOUNT_SERVER);
   const int observed_offset = (int)(TimeTradeServer() - TimeGMT());
   int written = 0;

   for(int shift = total_bars; shift >= 1; --shift)
   {
      double atr_value[1];
      if(CopyBuffer(handle, 0, shift, 1, atr_value) != 1)
      {
         PrintFormat("CopyBuffer failed at shift %d: %d", shift, GetLastError());
         continue;
      }

      const datetime bar_time = iTime(_Symbol, PERIOD_H1, shift);
      if(bar_time <= 0)
      {
         PrintFormat("Missing H1 bar time at shift %d: %d", shift, GetLastError());
         continue;
      }

      FileWrite(file,
                account_server,
                _Symbol,
                TimeToString(bar_time, TIME_DATE | TIME_SECONDS),
                observed_offset,
                DoubleToString(iHigh(_Symbol, PERIOD_H1, shift), _Digits),
                DoubleToString(iLow(_Symbol, PERIOD_H1, shift), _Digits),
                DoubleToString(iClose(_Symbol, PERIOD_H1, shift), _Digits),
                DoubleToString(atr_value[0], 8),
                shift <= CompareBars ? 1 : 0);
      ++written;
   }

   FileFlush(file);
   FileClose(file);
   IndicatorRelease(handle);
   PrintFormat("ATR parity export complete: %d rows written to Common/Files/%s",
               written, OutputFile);
}
