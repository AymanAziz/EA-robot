#property strict
void OnStart()
{
   long chart=ChartOpen("XAUUSD.c",PERIOD_M5);
   if(chart==0) {Print("PERSIST_CHART_FAILED");return;}
   ChartSetInteger(chart,CHART_BRING_TO_TOP,true);
   ChartSetInteger(chart,CHART_SHOW_TRADE_HISTORY,false);
   ChartSetInteger(chart,CHART_SHOW_ONE_CLICK,false);
   ChartRedraw(chart);
   int f=FileOpen("goldnix_persistent_chart.csv",FILE_WRITE|FILE_CSV|FILE_COMMON|FILE_ANSI,',');
   FileWrite(f,"chart_id","symbol","timeframe");FileWrite(f,chart,"XAUUSD.c","M5");FileClose(f);
}
