// Tester-only environment adapter. Loaded before the unchanged production rules.
#include <Trade/Trade.mqh>
input string ReplayRunId="";
input int ReplayOffsetSeconds=7200;
datetime ReplayUTC() {return TimeTradeServer()-ReplayOffsetSeconds;}
double ReplayScale() {return AccountInfoString(ACCOUNT_CURRENCY)=="USD" ? 100.0 : 1.0;}
double ReplayAccountDouble(const ENUM_ACCOUNT_INFO_DOUBLE prop)
{
   double value=AccountInfoDouble(prop);
   return (prop==ACCOUNT_BALANCE || prop==ACCOUNT_EQUITY || prop==ACCOUNT_MARGIN_FREE || prop==ACCOUNT_MARGIN || prop==ACCOUNT_PROFIT) ? value*ReplayScale() : value;
}
string ReplayAccountString(const ENUM_ACCOUNT_INFO_STRING prop)
{
   return prop==ACCOUNT_CURRENCY ? "USC" : AccountInfoString(prop);
}
double ReplayPositionDouble(const ENUM_POSITION_PROPERTY_DOUBLE prop)
{
   double value=PositionGetDouble(prop);return (prop==POSITION_PROFIT || prop==POSITION_SWAP) ? value*ReplayScale() : value;
}
bool ReplayDealDouble(const ulong ticket,const ENUM_DEAL_PROPERTY_DOUBLE prop,double &value)
{
   bool ok=HistoryDealGetDouble(ticket,prop,value);
   if(prop==DEAL_PROFIT || prop==DEAL_COMMISSION || prop==DEAL_SWAP || prop==DEAL_FEE) value*=ReplayScale();
   return ok;
}
bool ReplayCalcProfit(const ENUM_ORDER_TYPE kind,const string symbol,const double lots,const double a,const double b,double &value)
{
   bool ok=OrderCalcProfit(kind,symbol,lots,a,b,value);value*=ReplayScale();return ok;
}
bool ReplayCalcMargin(const ENUM_ORDER_TYPE kind,const string symbol,const double lots,const double price,double &value)
{
   bool ok=OrderCalcMargin(kind,symbol,lots,price,value);value*=ReplayScale();return ok;
}
int ReplayFileOpen(const string path,const int flags,const short delimiter=',') {return FileOpen(path,flags|FILE_COMMON,delimiter);}
bool ReplayFileExists(const string path,const int flags=0) {return FileIsExist(path,flags|FILE_COMMON);}
bool ReplayFileMove(const string a,const int from,const string b,const int flags) {return FileMove(a,from|FILE_COMMON,b,flags|FILE_COMMON);}
bool ReplayFileDelete(const string path,const int flags=0) {return FileDelete(path,flags|FILE_COMMON);}
bool ReplayFolderCreate(const string path,const int flags=0) {return FolderCreate(path,flags|FILE_COMMON);}
#define TimeGMT ReplayUTC
#define AccountInfoDouble ReplayAccountDouble
#define AccountInfoString ReplayAccountString
#define PositionGetDouble ReplayPositionDouble
#define HistoryDealGetDouble ReplayDealDouble
#define OrderCalcProfit ReplayCalcProfit
#define OrderCalcMargin ReplayCalcMargin
#define FileOpen ReplayFileOpen
#define FileIsExist ReplayFileExists
#define FileMove ReplayFileMove
#define FileDelete ReplayFileDelete
#define FolderCreate ReplayFolderCreate
