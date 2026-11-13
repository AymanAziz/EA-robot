#property strict
#property script_show_inputs
#include "AutoM1Policy.mqh"
#include "MtfPolicy.mqh"
#include "MtfJournal.mqh"
int passed=0,failed=0;
void Check(const bool ok,const string name) {if(ok) passed++;else {failed++;Print("FAIL: ",name);}}
#include "MtfCases.mqh"
void OnStart()
{
   RunMtfCases();
   AutoState risk={};risk.base_equity=2000;risk.realized_r=-2;
   Check(RiskReason(risk,2000)=="daily_r_limit","minus two R blocks entries on the shared policy");
   risk.realized_r=0;risk.attempts=7;
   Check(RiskReason(risk,2000)=="daily_attempt_limit","seventh daily attempt exhausts quota");
   risk.attempts=0;
   Check(RiskReason(risk,1990)=="daily_loss_limit","ten USC equity loss blocks entries");
   risk.day=20000;risk.pending_magic=AUTO_MAGIC_BASE+2000001;
   Check(!ResetDayIfFlat(risk,20001,2000,0,0),"pending position intent prevents day reset");
   FakeoutState record={};record.magic=AUTO_MAGIC_BASE+2000001;record.entry=1700000000;
   record.direction=-1;record.level=2000;record.buffer=.3;record.exit_intent=true;
   FolderCreate("D01Probe",0);
   string journal="D01Probe\\fakeout.csv";
   Check(SaveFakeoutRecord(journal,record),"durable frozen geometry and exit intent read back exactly");
   record.level+=1;
   Check(!ConfirmFakeoutRecord(journal,record),"changed frozen level does not validate against receipt");
   FileDelete(journal,0);
   Check(!ConfirmFakeoutRecord(journal,record),"missing receipt cannot validate");
   // Same real-history fixture as the independent pandas reference, no orders.
   int fixture_file=FileOpen("goldnix_d01_fixture.csv",FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   int output=FileOpen("goldnix_d01_features.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   Check(fixture_file!=INVALID_HANDLE && output!=INVALID_HANDLE,"feature fixture files available");
   if(fixture_file!=INVALID_HANDLE && output!=INVALID_HANDLE)
   {
      MtfContext c;c.Reset();
      FileWrite(output,"decision_server","h4_count","h4_available_server","ema50","h4_ready","h4_direction","h1_open_server","h1_ready","direction","atr","level","buffer");
      while(!FileIsEnding(fixture_file))
      {
         QuoteBar b={};b.server=(datetime)StringToInteger(FileReadString(fixture_file));
         b.bo=FileReadNumber(fixture_file);b.bh=FileReadNumber(fixture_file);b.bl=FileReadNumber(fixture_file);b.bc=FileReadNumber(fixture_file);
         b.ao=FileReadNumber(fixture_file);b.ah=FileReadNumber(fixture_file);b.al=FileReadNumber(fixture_file);b.ac=FileReadNumber(fixture_file);b.ticks=(int)FileReadNumber(fixture_file);
         if(!c.Push(b)) {Check(false,"native feature fixture accepted");break;}
         int dir=0;double atr=0,d=0,spread=0,nom=0,level=0,buffer=0;
         bool available=c.Signal(dir,atr,d,spread,nom,level,buffer);
         FileWrite(output,(long)b.server+300,c.HigherCount(),c.HigherClose(),DoubleToString(c.Average(),12),
            c.TrendReady((long)b.server+300),c.Trend((long)b.server+300),c.LastHour(),available,dir,
            DoubleToString(atr,12),DoubleToString(level,12),DoubleToString(buffer,12));
      }
   }
   if(fixture_file!=INVALID_HANDLE) FileClose(fixture_file);if(output!=INVALID_HANDLE) FileClose(output);
   int f=FileOpen("goldnix_d01_policy.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(f!=INVALID_HANDLE) {FileWrite(f,"passed","failed");FileWrite(f,passed,failed);FileClose(f);}
}
