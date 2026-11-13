#ifndef GOLDNIX_AUTO_POLICY
#define GOLDNIX_AUTO_POLICY

const long AUTO_MAGIC_BASE=930000000000;
const int AUTO_BAR_SECONDS=300;
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
   return !resynchronizing && signal_utc>s.last_signal && now_utc>=signal_utc+300 && now_utc<signal_utc+310;
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
