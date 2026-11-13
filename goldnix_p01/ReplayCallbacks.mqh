int replay_ticks=INVALID_HANDLE,replay_timers=INVALID_HANDLE;
long replay_tick_count=0,replay_timer_count=0;
datetime replay_start=0;
int OnInit()
{
   if(!MQLInfoInteger(MQL_TESTER) || ReplayRunId=="" || StringFind(ReplayRunId,".")>=0 || StringFind(ReplayRunId,"\\")>=0 || StringFind(ReplayRunId,"/")>=0)
      return INIT_PARAMETERS_INCORRECT;
   int result=CoreInit();if(result!=INIT_SUCCEEDED) return result;
   replay_start=TimeCurrent();
   replay_ticks=FileOpen(ROOT+"\\all_ticks.bin",FILE_WRITE|FILE_BIN);
   replay_timers=FileOpen(ROOT+"\\timers.bin",FILE_WRITE|FILE_BIN);
   int f=FileOpen(ROOT+"\\symbol.csv",FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   FileWrite(f,"key","value");FileWrite(f,"digits",_Digits);FileWrite(f,"tick_size",SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE));
   FileWrite(f,"point",_Point);FileWrite(f,"stops_level",SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL));
   FileWrite(f,"freeze_level",SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL));FileWrite(f,"contract_size",SymbolInfoDouble(_Symbol,SYMBOL_TRADE_CONTRACT_SIZE));
   FileWrite(f,"initial_equity_usc",AccountInfoDouble(ACCOUNT_EQUITY));FileWrite(f,"offset_seconds",ReplayOffsetSeconds);
   FileWrite(f,"leverage",AccountInfoInteger(ACCOUNT_LEVERAGE));FileWrite(f,"tester",MQLInfoInteger(MQL_TESTER));FileClose(f);
   f=FileOpen(ROOT+"\\sessions.csv",FILE_WRITE|FILE_CSV|FILE_ANSI,',');FileWrite(f,"weekday","number","from","to");
   for(int day=0;day<7;day++) for(uint k=0;k<20;k++)
   {
      datetime begin=0,end=0;if(!SymbolInfoSessionTrade(_Symbol,(ENUM_DAY_OF_WEEK)day,k,begin,end)) break;
      FileWrite(f,day,k,(long)begin,(long)end);
   }
   FileClose(f);
   return replay_ticks==INVALID_HANDLE || replay_timers==INVALID_HANDLE ? INIT_FAILED : INIT_SUCCEEDED;
}
void OnTick()
{
   MqlTick q={};if(replay_ticks==INVALID_HANDLE || !SymbolInfoTick(_Symbol,q)) return;
   FileWriteLong(replay_ticks,q.time_msc);FileWriteDouble(replay_ticks,q.bid);FileWriteDouble(replay_ticks,q.ask);replay_tick_count++;
}
void OnTimer()
{
   if(replay_timers==INVALID_HANDLE) return;
   MqlTick q={};SymbolInfoTick(_Symbol,q);
   long flags=ready ? 1 : 0;datetime stamp=TimeGMT();
   CoreTimer();if(ready) flags|=2;if(state.recover) flags|=4;if(state.fatal) flags|=8;
   FileWriteLong(replay_timers,(long)stamp);FileWriteLong(replay_timers,q.time_msc);
   FileWriteDouble(replay_timers,q.bid);FileWriteDouble(replay_timers,q.ask);
   FileWriteLong(replay_timers,(long)MarketEndUTC(stamp));FileWriteLong(replay_timers,flags);replay_timer_count++;
   if(replay_timer_count%1000==0) {FileFlush(replay_timers);FileFlush(replay_ticks);}
}
void OnDeinit(const int reason)
{
   if(!MQLInfoInteger(MQL_TESTER) || ReplayRunId=="") return;
   bool censored=OwnPositions()>0;
   if(censored) {Event("REPLAY_END_CLOSE","right-censored test boundary, not a strategy exit");CloseOwned();Reconcile();}
   int f=FileOpen(ROOT+"\\broker_deals.csv",FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   FileWrite(f,"deal","position","magic","server_time_msc","side","reason","price","profit_usc","commission_usc","swap_usc","fee_usc");
   if(HistorySelect(replay_start-60,TimeCurrent()+60)) for(int j=0;j<HistoryDealsTotal();j++)
   {
      ulong deal=HistoryDealGetTicket(j);long position=0,magic=0,stamp=0,side=0,why=0;double price=0,profit=0,commission=0,swap=0,fee=0;
      if(deal==0 || !HistoryDealGetInteger(deal,DEAL_POSITION_ID,position) || !HistoryDealGetInteger(deal,DEAL_MAGIC,magic) ||
         !HistoryDealGetInteger(deal,DEAL_TIME_MSC,stamp) || !HistoryDealGetInteger(deal,DEAL_ENTRY,side) || !HistoryDealGetInteger(deal,DEAL_REASON,why) ||
         !HistoryDealGetDouble(deal,DEAL_PRICE,price) || !HistoryDealGetDouble(deal,DEAL_PROFIT,profit) || !HistoryDealGetDouble(deal,DEAL_COMMISSION,commission) ||
         !HistoryDealGetDouble(deal,DEAL_SWAP,swap) || !HistoryDealGetDouble(deal,DEAL_FEE,fee)) continue;
      if(AutoOwnedMagic(magic)) FileWrite(f,deal,position,magic,stamp,side,why,DoubleToString(price,8),DoubleToString(profit,8),
         DoubleToString(commission,8),DoubleToString(swap,8),DoubleToString(fee,8));
   }
   FileClose(f);
   f=FileOpen(ROOT+"\\receipt.csv",FILE_WRITE|FILE_CSV|FILE_ANSI,',');
   FileWrite(f,"key","value");FileWrite(f,"completed",1);FileWrite(f,"tester",MQLInfoInteger(MQL_TESTER));
   FileWrite(f,"ticks",replay_tick_count);FileWrite(f,"timers",replay_timer_count);FileWrite(f,"audit_halt",state.fatal);
   FileWrite(f,"audit_reason",state.fatal_reason);FileWrite(f,"state_broken",state_broken);FileWrite(f,"censored_boundary_position",censored);
   FileWrite(f,"run_folder",run_folder);FileWrite(f,"balance_usc",AccountInfoDouble(ACCOUNT_BALANCE));FileClose(f);
   if(replay_ticks!=INVALID_HANDLE) FileClose(replay_ticks);if(replay_timers!=INVALID_HANDLE) FileClose(replay_timers);
   CoreDeinit(reason);
}
