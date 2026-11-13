#ifndef GOLDNIX_AUTO_M1_POLICY
#define GOLDNIX_AUTO_M1_POLICY

const long AUTO_MAGIC_BASE=930000000000;
const int AUTO_BAR_SECONDS=60;
const int AUTO_MAX_ATTEMPTS=7;
const double AUTO_LOSS_USC=10.0;

struct AutoState
{
   long owner,sequence,day,last_signal,last_exit_bar,pending_magic,pending_server;
   int attempts,pending_direction;
   double base_equity,realized_r,pending_atr,pending_distance;
   bool daily_halt,fatal,recover;
   ulong position_id;
   string fatal_reason;
};
struct QuoteBar {datetime server; double bo,bh,bl,bc,ao,ah,al,ac; int ticks;};

long MalaysiaDay(const datetime utc) {return ((long)utc+8*3600)/86400;}
bool AutoOwnedMagic(const long magic) {return magic>AUTO_MAGIC_BASE && magic<AUTO_MAGIC_BASE+10000000;}
double MidHigh(const QuoteBar &b) {return (b.bh+b.ah)/2;}
double MidLow(const QuoteBar &b) {return (b.bl+b.al)/2;}
double MidClose(const QuoteBar &b) {return (b.bc+b.ac)/2;}

bool SignalStats(const QuoteBar &window_bars[],int &direction,double &atr,double &distance,double &spread,double &nominal)
{
   int n=ArraySize(window_bars); if(n<100) return false;
   atr=0; double hi=-DBL_MAX,lo=DBL_MAX;
   for(int j=n-14;j<n;j++) atr+=MathMax(MidHigh(window_bars[j])-MidLow(window_bars[j]),
      MathMax(MathAbs(MidHigh(window_bars[j])-MidClose(window_bars[j-1])),MathAbs(MidLow(window_bars[j])-MidClose(window_bars[j-1]))));
   atr/=14;
   for(int j=n-21;j<n-1;j++) {hi=MathMax(hi,MidHigh(window_bars[j]));lo=MathMin(lo,MidLow(window_bars[j]));}
   direction=MidClose(window_bars[n-1])>hi ? 1 : MidClose(window_bars[n-1])<lo ? -1 : 0;
   distance=MathMax(2*atr,.5);spread=window_bars[n-1].ac-window_bars[n-1].bc;nominal=(distance+spread)*.01;
   return MathIsValidNumber(atr) && atr>0 && spread>=0;
}
bool ResetDayIfFlat(AutoState &s,const long day,const double equity,const int positions,const int orders)
{
   if(day<=s.day || s.pending_magic!=0 || positions!=0 || orders!=0 || equity<=0 || !MathIsValidNumber(equity)) return false;
   s.day=day;s.attempts=0;s.base_equity=equity;s.realized_r=0;s.daily_halt=false;
   return true;
}
string RiskReason(const AutoState &s,const double equity)
{
   if(s.fatal) return "audit_halt";
   if(s.daily_halt || s.base_equity-equity>=AUTO_LOSS_USC) return "daily_loss_limit";
   if(s.realized_r<=-2) return "daily_r_limit";
   if(s.attempts>=AUTO_MAX_ATTEMPTS) return "daily_attempt_limit";
   return "";
}
bool FreshSignal(const AutoState &s,const long signal_utc,const long now_utc,const bool resynchronizing)
{
   return !resynchronizing && signal_utc>s.last_signal && now_utc>=signal_utc+AUTO_BAR_SECONDS && now_utc<signal_utc+AUTO_BAR_SECONDS+10;
}
// An explicitly requested demo execution check expires and can be claimed once.
bool ExecutionCheckAvailable(const long request_utc,const long now_utc,const bool consumed)
{
   return request_utc>0 && now_utc>=request_utc && now_utc-request_utc<3600 && !consumed;
}
int ExecutionCheckDirection(const QuoteBar &bar)
{
   double open=(bar.bo+bar.ao)/2,close=MidClose(bar);
   return close>open ? 1 : close<open ? -1 : 0;
}
bool ExecutionCheckSizing(const double atr,const double spread,double &distance,double &nominal)
{
   // Operational check only: leave 1 USC headroom below the 5 USC hard cap.
   if(!MathIsValidNumber(atr) || !MathIsValidNumber(spread) || atr<=0 || spread<0 || 4.0-spread<.5) return false;
   distance=MathMin(MathMax(2*atr,.5),4.0-spread);nominal=(distance+spread)*.01;
   return true;
}
bool ClaimExecutionCheck(const string path,const long request_utc,const long now_utc)
{
   if(!ExecutionCheckAvailable(request_utc,now_utc,FileIsExist(path,0))) return false;
   int f=FileOpen(path,FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   if(f==INVALID_HANDLE) return false;
   bool wrote=FileWrite(f,"request_utc",request_utc)>0 && FileWrite(f,"claimed_utc",now_utc)>0 && FileWrite(f,"commit","GNC1")>0;
   FileFlush(f);FileClose(f);
   if(!wrote) return false;
   f=FileOpen(path,FILE_READ|FILE_CSV|FILE_ANSI,',');
   if(f==INVALID_HANDLE) return false;
   string k1=FileReadString(f),v1=FileReadString(f),k2=FileReadString(f),v2=FileReadString(f),k3=FileReadString(f),v3=FileReadString(f);
   bool valid=k1=="request_utc" && v1==(string)request_utc && k2=="claimed_utc" && v2==(string)now_utc && k3=="commit" && v3=="GNC1" && FileIsEnding(f);
   FileClose(f);return valid;
}
uint StateChecksum(const string text)
{
   uint result=2166136261;
   for(int i=0;i<StringLen(text);i++) {result^=(uint)StringGetCharacter(text,i);result*=16777619;}
   return result;
}
string StatePayload(const AutoState &s)
{
   return "1|"+(string)s.owner+"|"+(string)s.sequence+"|"+(string)s.day+"|"+(string)s.attempts+"|"+
      DoubleToString(s.base_equity,12)+"|"+DoubleToString(s.realized_r,12)+"|"+(string)(int)s.daily_halt+"|"+
      (string)(int)s.fatal+"|"+(string)(int)s.recover+"|"+(string)s.last_signal+"|"+(string)s.last_exit_bar+"|"+
      (string)s.pending_magic+"|"+(string)s.pending_server+"|"+(string)s.pending_direction+"|"+
      DoubleToString(s.pending_atr,12)+"|"+DoubleToString(s.pending_distance,12)+"|"+(string)s.position_id+"|"+s.fatal_reason;
}
bool NumberText(const string text)
{
   if(StringLen(text)==0) return false;
   bool digit=false;
   for(int j=0;j<StringLen(text);j++)
   {
      ushort c=StringGetCharacter(text,j);
      if(c>='0' && c<='9') digit=true;
      else if(c!='.' && !(j==0 && c=='-')) return false;
   }
   return digit && MathIsValidNumber(StringToDouble(text));
}
bool ParseState(const string payload,const long owner,AutoState &s)
{
   string a[];if(StringSplit(payload,'|',a)!=19 || a[0]!="1") return false;
   for(int j=1;j<18;j++) if(!NumberText(a[j])) return false;
   s.owner=StringToInteger(a[1]);s.sequence=StringToInteger(a[2]);s.day=StringToInteger(a[3]);s.attempts=(int)StringToInteger(a[4]);
   s.base_equity=StringToDouble(a[5]);s.realized_r=StringToDouble(a[6]);
   for(int j=7;j<=9;j++) if(a[j]!="0" && a[j]!="1") return false;
   s.daily_halt=a[7]=="1";s.fatal=a[8]=="1";s.recover=a[9]=="1";
   s.last_signal=StringToInteger(a[10]);s.last_exit_bar=StringToInteger(a[11]);
   s.pending_magic=StringToInteger(a[12]);s.pending_server=StringToInteger(a[13]);s.pending_direction=(int)StringToInteger(a[14]);
   s.pending_atr=StringToDouble(a[15]);s.pending_distance=StringToDouble(a[16]);s.position_id=(ulong)StringToInteger(a[17]);s.fatal_reason=a[18];
   if(s.owner!=owner || s.sequence<1 || s.day<19000 || s.day>100000 || s.attempts<0 || s.attempts>AUTO_MAX_ATTEMPTS ||
      s.base_equity<=0 || s.last_signal<0 || s.last_exit_bar<0 || StringLen(s.fatal_reason)>100) return false;
   if(!s.fatal && s.fatal_reason!="") return false;
   if(s.pending_magic!=0 && (!AutoOwnedMagic(s.pending_magic) || s.pending_server<=0 || s.pending_atr<=0 ||
      s.pending_distance<.5 || (s.pending_direction!=1 && s.pending_direction!=-1))) return false;
   // Re-serialization rejects malformed numbers, fractional integers and noncanonical records.
   return StatePayload(s)==payload;
}
#endif
