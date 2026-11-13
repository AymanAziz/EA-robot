#ifndef GOLDNIX_MTF_JOURNAL
#define GOLDNIX_MTF_JOURNAL
string FakeoutPayload(const FakeoutState &s)
{
   return (string)s.magic+"|"+(string)s.entry+"|"+(string)s.direction+"|"+
      DoubleToString(s.level,12)+"|"+DoubleToString(s.buffer,12)+"|"+(string)s.last+"|"+
      (string)s.previous+"|"+(string)s.seen+"|"+(string)s.warning+"|"+(string)(int)s.exit_intent;
}
bool ConfirmFakeoutRecord(const string path,const FakeoutState &s)
{
   int f=FileOpen(path,FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ,',');if(f==INVALID_HANDLE) return false;
   string version=FileReadString(f),read=FileReadString(f),sum=FileReadString(f),payload=FakeoutPayload(s);
   bool ok=version=="D01" && read==payload && sum==(string)(long)StateChecksum(payload) && FileIsEnding(f);
   FileClose(f);return ok;
}
bool SaveFakeoutRecord(const string path,const FakeoutState &s)
{
   if(!AutoOwnedMagic(s.magic) || s.entry<=0 || (s.direction!=1 && s.direction!=-1) ||
      !MathIsValidNumber(s.level+s.buffer) || s.level<=0 || s.buffer<0) return false;
   string payload=FakeoutPayload(s),temp=path+".next";
   int f=FileOpen(temp,FILE_WRITE|FILE_CSV|FILE_ANSI,',');if(f==INVALID_HANDLE) return false;
   bool ok=FileWrite(f,"D01",payload,(long)StateChecksum(payload))>0;FileFlush(f);FileClose(f);
   return ok && ConfirmFakeoutRecord(temp,s) && FileMove(temp,0,path,FILE_REWRITE) && ConfirmFakeoutRecord(path,s);
}
#endif
