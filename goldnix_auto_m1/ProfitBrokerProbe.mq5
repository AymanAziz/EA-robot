#property strict
#include "ProfitManager.mqh"
input string RunId="";
CTrade test_broker;
ProfitManager manager;
datetime last_second=0,opened=0,last_entry=0;
int passed=0,failed=0,attempts=0,buy_modifications=0,sell_modifications=0,restarts=0,injected_rejections=0,closed_by_floor=0;
bool injected_buy=false,injected_sell=false;
double fixture_tp=0,last_sl=0;
string fixture_root;
int out=INVALID_HANDLE;
void Assert(const bool ok,const string name)
{
   if(ok) passed++;else {failed++;Print("PROFIT_BROKER_FAIL "+name);}
}
int OnInit()
{
   if(!MQLInfoInteger(MQL_TESTER) || RunId=="" || _Symbol!="XAUUSD.c") return INIT_PARAMETERS_INCORRECT;
   fixture_root="GoldnixProfitProbe_"+RunId;FolderCreate(fixture_root,0);
   out=FileOpen(fixture_root+"_events.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   if(out==INVALID_HANDLE) return INIT_FAILED;
   FileWrite(out,"server_time","event","side","sl","tp","detail");
   test_broker.SetAsyncMode(false);test_broker.SetTypeFillingBySymbol(_Symbol);
   return INIT_SUCCEEDED;
}
void OnTick()
{
   datetime now=TimeCurrent();if(now==last_second || failed>0) return;last_second=now;
   MqlTick q={};if(!SymbolInfoTick(_Symbol,q) || q.bid<=0 || q.ask<q.bid) return;
   if(PositionsTotal()==0)
   {
      if(attempts>=40 || now-last_entry<60) return;
      attempts++;last_entry=now;
      int side=attempts%2==1 ? 1 : -1;
      double entry=side>0 ? q.ask : q.bid,sl=NormalizeDouble(entry-side*4,_Digits),tp=NormalizeDouble(entry+side*12,_Digits);
      test_broker.SetExpertMagicNumber(940000000000+attempts);
      bool sent=side>0 ? test_broker.Buy(.01,_Symbol,0,sl,tp,"tester profit protection") : test_broker.Sell(.01,_Symbol,0,sl,tp,"tester profit protection");
      Assert(sent && test_broker.ResultRetcode()==TRADE_RETCODE_DONE,"simulated entry accepted");
      if(PositionsTotal()==0) return;
      ulong ticket=PositionGetTicket(0);long magic=PositionGetInteger(POSITION_MAGIC);
      Assert(manager.Observe(ticket,1,magic,fixture_root),"new position initializes original-risk journal");
      fixture_tp=PositionGetDouble(POSITION_TP);last_sl=PositionGetDouble(POSITION_SL);opened=now;
      return;
   }
   ulong ticket=PositionGetTicket(0);long magic=PositionGetInteger(POSITION_MAGIC);
   int side=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY ? 1 : -1;
   int action=manager.Manage(test_broker,ticket,1,magic,fixture_root,now,q,true,true);
   Assert(action>=0,"production manager handles tester position");
   if(action==2) closed_by_floor++;
   if(!PositionSelectByTicket(ticket)) return;
   double sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
   Assert(side*(sl-last_sl)>=-1e-8,"server stop never loosens");
   Assert(MathAbs(tp-fixture_tp)<1e-8,"server TP preserved");last_sl=sl;
   if(action==1)
   {
      if(side>0) buy_modifications++;else sell_modifications++;
      Assert(side*(sl-PositionGetDouble(POSITION_PRICE_OPEN))>0,"confirmed server SL is profitable before costs");
      Assert(manager.Observe(ticket,1,magic,fixture_root),"profitable server SL survives reconciliation");
      ProfitManager restarted;
      Assert(restarted.Observe(ticket,1,magic,fixture_root) && MathAbs(restarted.AcceptedSL()-sl)<1e-8 && MathAbs(restarted.Peak()-manager.Peak())<1e-8,
         "fresh manager recovers peak and confirmed profitable SL");restarts++;
      FileWrite(out,(long)now,"confirmed_modify",side,sl,tp,manager.status);FileFlush(out);
   }
   // Test rejected broker requests using a deliberately stale/artificial quote AFTER a real protected SL.
   // This is fault injection, never a performance backtest or the production quote source.
   bool injected=side>0 ? injected_buy : injected_sell;
   if(!injected && side*(sl-PositionGetDouble(POSITION_PRICE_OPEN))>0 && now-opened>3 && action==0)
   {
      MqlTick artificial=q;artificial.bid+=side*6;artificial.ask+=side*6;
      int rejected=manager.Manage(test_broker,ticket,1,magic,fixture_root,now+2,artificial,true,true);
      Assert(rejected==0 && StringFind(manager.status,"profit_stop_unconfirmed_")==0,"broker rejection is not reported as protection success");
      Assert(PositionSelectByTicket(ticket) && MathAbs(PositionGetDouble(POSITION_SL)-sl)<1e-8 && MathAbs(PositionGetDouble(POSITION_TP)-tp)<1e-8,
         "rejected request retains actual server SL and TP");
      if(side>0) injected_buy=true;else injected_sell=true;injected_rejections++;
      FileWrite(out,(long)now,"injected_broker_rejection",side,sl,tp,manager.status);FileFlush(out);
   }
   if(now-opened>=900 && PositionSelectByTicket(ticket))
      Assert(test_broker.PositionClose(ticket) && test_broker.ResultRetcode()==TRADE_RETCODE_DONE,"fixture time exit accepted");
}
void OnDeinit(const int reason)
{
   if(out!=INVALID_HANDLE) FileClose(out);
   if(!MQLInfoInteger(MQL_TESTER) || RunId=="") return;
   int f=FileOpen(fixture_root+"_result.csv",FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_COMMON,',');
   FileWrite(f,"passed","failed","attempts","buy_modifications","sell_modifications","restart_checks","injected_rejections","floor_closes","currency");
   FileWrite(f,passed,failed,attempts,buy_modifications,sell_modifications,restarts,injected_rejections,closed_by_floor,AccountInfoString(ACCOUNT_CURRENCY));FileClose(f);
}
