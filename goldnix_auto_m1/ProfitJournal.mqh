#ifndef GOLDNIX_PROFIT_JOURNAL
#define GOLDNIX_PROFIT_JOURNAL
#include "AutoM1Policy.mqh"
#include "ProfitPolicy.mqh"
struct ProfitRecord
{
   long owner,magic;ulong position;int direction;
   double entry,initial_sl,tp,peak,accepted_sl;
   bool close_requested;
};
string ProfitPayload(const ProfitRecord &p)
{
   return "1|"+(string)p.owner+"|"+(string)p.magic+"|"+(string)p.position+"|"+(string)p.direction+"|"+
      DoubleToString(p.entry,12)+"|"+DoubleToString(p.initial_sl,12)+"|"+DoubleToString(p.tp,12)+"|"+
      DoubleToString(p.peak,12)+"|"+DoubleToString(p.accepted_sl,12)+"|"+(string)(int)p.close_requested;
}
bool ParseProfit(const string payload,const long owner,const long magic,ProfitRecord &p)
{
   string a[];if(StringSplit(payload,'|',a)!=11 || a[0]!="1") return false;
   for(int j=1;j<11;j++) if(!NumberText(a[j])) return false;
   p.owner=StringToInteger(a[1]);p.magic=StringToInteger(a[2]);p.position=(ulong)StringToInteger(a[3]);p.direction=(int)StringToInteger(a[4]);
   p.entry=StringToDouble(a[5]);p.initial_sl=StringToDouble(a[6]);p.tp=StringToDouble(a[7]);
   p.peak=StringToDouble(a[8]);p.accepted_sl=StringToDouble(a[9]);p.close_requested=a[10]=="1";
   return p.owner==owner && p.owner>0 && p.magic==magic && p.magic>0 && p.position>0 && (p.direction==1 || p.direction==-1) &&
      p.entry>0 && p.initial_sl>0 && p.tp>0 && p.peak>0 && p.accepted_sl>0 &&
      p.direction*(p.entry-p.initial_sl)>0 && p.direction*(p.tp-p.entry)>0 && p.direction*(p.peak-p.entry)>=0 &&
      p.direction*(p.accepted_sl-p.initial_sl)>=0 && p.direction*(p.tp-p.accepted_sl)>0 &&
      (a[10]=="0" || a[10]=="1") && ProfitPayload(p)==payload;
}
bool ReadProfit(const string path,const long owner,const long magic,ProfitRecord &p)
{
   int f=FileOpen(path,FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ,',');if(f==INVALID_HANDLE) return false;
   string k=FileReadString(f),payload=FileReadString(f),ck=FileReadString(f),sum=FileReadString(f),end=FileReadString(f),commit=FileReadString(f);
   bool ended=FileIsEnding(f);FileClose(f);
   return k=="payload" && ck=="checksum" && end=="commit" && commit=="GNP1" && ended &&
      sum==(string)(long)StateChecksum(payload) && ParseProfit(payload,owner,magic,p);
}
bool SaveProfit(const string path,const ProfitRecord &p)
{
   string payload=ProfitPayload(p),temp=path+".next";ProfitRecord check={};
   if(!ParseProfit(payload,p.owner,p.magic,check)) return false;
   int f=FileOpen(temp,FILE_WRITE|FILE_CSV|FILE_ANSI,',');if(f==INVALID_HANDLE) return false;
   bool wrote=FileWrite(f,"payload",payload)>0 && FileWrite(f,"checksum",(long)StateChecksum(payload))>0 && FileWrite(f,"commit","GNP1")>0;
   FileFlush(f);FileClose(f);
   return wrote && ReadProfit(temp,p.owner,p.magic,check) && ProfitPayload(check)==payload &&
      FileMove(temp,0,path,0|FILE_REWRITE) && ReadProfit(path,p.owner,p.magic,check) && ProfitPayload(check)==payload;
}
#endif
