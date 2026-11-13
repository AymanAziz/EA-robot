// Included after the preserved account, risk, reconciliation and profit manager.
bool SaveFakeout()
{
   return SaveFakeoutRecord(ROOT+"\\mtf_fakeout.csv",fakeout);
}
void ManageFakeout()
{
   if(state.pending_magic==0 || state.recover || state.fatal || !fakeout.exit_intent) return;
   if(fakeout.magic!=state.pending_magic) {Fatal("fakeout_intent_mismatch");CloseOwned();return;}
   MqlTick quote={};
   if(TimeGMT()-last_fakeout_request<2 || !CanTrade() || !SymbolInfoTick(_Symbol,quote) ||
      MathAbs((double)(TimeGMT()-ToUTC(quote.time)))>3 || quote.bid<=0 || quote.ask<quote.bid) return;
   last_fakeout_request=TimeGMT();Event("FAKEOUT_EXIT_REQUEST","confirmed M15 failure plus next M5; current executable quote");
   CloseOwned();Reconcile();
}
bool AddMtfBar(const QuoteBar &bar,const bool manage)
{
   if(!mtf.Push(bar)) {Event("MTF_DATA_REJECTED",(string)(long)bar.server);return false;}
   if(FileWrite(barfile,(long)bar.server,DoubleToString(bar.bo,8),DoubleToString(bar.bh,8),DoubleToString(bar.bl,8),DoubleToString(bar.bc,8),
      DoubleToString(bar.ao,8),DoubleToString(bar.ah,8),DoubleToString(bar.al,8),DoubleToString(bar.ac,8),bar.ticks)==0) return false;
   int dir=0;double atr=0,distance=0,spread=0,nominal=0,level=0,buffer=0;
   bool available=mtf.Signal(dir,atr,distance,spread,nominal,level,buffer);
   if(FileWrite(contextfile,(long)bar.server+300,mtf.HigherCount(),mtf.HigherClose(),DoubleToString(mtf.Average(),12),
      mtf.TrendReady((long)bar.server+300),mtf.Trend((long)bar.server+300),mtf.LastHour(),available,dir,
      DoubleToString(atr,12),DoubleToString(level,12),DoubleToString(buffer,12))==0) return false;
   if(manage && state.pending_magic!=0 && !state.recover && !state.fatal)
   {
      if(fakeout.magic!=state.pending_magic) {Fatal("missing_frozen_fakeout_geometry");CloseOwned();return false;}
      int action=FakeoutStep(fakeout,(long)bar.server,MidClose(bar));
      if(action<0 || !SaveFakeout()) {Fatal("fakeout_state_not_confirmed");CloseOwned();return false;}
      if(action==1) Event("FAKEOUT_WARNING","complete post-entry M15 closed inside frozen H1 level");
      if(action==2) Event("FAKEOUT_CONFIRMED","next consecutive M5 failed to reclaim; durable exit intent");
   }
   return true;
}
// Copy up to 64 existing M5 intervals in one tick-history request. Validate the
// complete batch before advancing the context, so retries cannot duplicate bars.
bool AppendMtfChunk(const MqlRates &rates[],const int first,const int count,const bool manage)
{
   if(count<=0 || count>64) return false;
   MqlTick ticks[];ResetLastError();
   int n=CopyTicksRange(_Symbol,ticks,COPY_TICKS_ALL,(ulong)rates[first].time*1000,(ulong)(rates[first+count-1].time+300)*1000-1);
   int error=GetLastError();
   if(n<=0 || error!=0) {Event("MTF_HISTORY_WAIT",StringFormat("count=%d;error=%d",n,error));return false;}
   QuoteBar chunk[64];int cursor=0;
   for(int j=0;j<count;j++)
   {
      QuoteBar b={};b.server=rates[first+j].time;b.bh=-DBL_MAX;b.ah=-DBL_MAX;b.bl=DBL_MAX;b.al=DBL_MAX;
      while(cursor<n && ticks[cursor].time<b.server) cursor++;
      while(cursor<n && ticks[cursor].time<b.server+300)
      {
         MqlTick q=ticks[cursor++];
         if(q.bid<=0 || q.ask<q.bid || !MathIsValidNumber(q.bid+q.ask)) return false;
         if(b.ticks==0) {b.bo=q.bid;b.ao=q.ask;}
         b.bh=MathMax(b.bh,q.bid);b.bl=MathMin(b.bl,q.bid);b.bc=q.bid;
         b.ah=MathMax(b.ah,q.ask);b.al=MathMin(b.al,q.ask);b.ac=q.ask;b.ticks++;
      }
      if(b.ticks==0) {Event("MTF_HISTORY_WAIT","missing tick interval");return false;}chunk[j]=b;
   }
   for(int j=0;j<count;j++) if(!AddMtfBar(chunk[j],manage)) {Fatal("mtf_archive_or_context_failed");return false;}
   FileFlush(barfile);FileFlush(contextfile);return true;
}
bool SyncMtf(const bool allow_entry,const bool reconciled)
{
   datetime latest=iTime(_Symbol,PERIOD_M5,0);
   if(latest<=0 || latest<current_bar) return false;
   if(latest==current_bar) return true;
   MqlRates next_rates[];
   int n=CopyRates(_Symbol,PERIOD_M5,current_bar,latest-1,next_rates);
   if(n<=0) return false;
   int batch=MathMin(n,64);
   if(!AppendMtfChunk(next_rates,0,batch,allow_entry)) return false;
   current_bar=next_rates[batch-1].time+300;
   if(current_bar<latest) return false;
   ManageFakeout();
   long stamp=(long)ToUTC((datetime)mtf.LastHour());
   if(allow_entry && stamp>state.last_signal)
   {
      bool fresh=TimeGMT()>=stamp+3600 && TimeGMT()<stamp+3610 && n==1;
      state.last_signal=stamp;if(Persist()) Evaluate(fresh && reconciled,"new_h1");
   }
   return true;
}
bool WarmupStep()
{
   if(warm_index<0)
   {
      if(state.pending_magic!=0) {state.recover=true;Persist();CloseOwned();return false;}
      if(CopyRates(_Symbol,PERIOD_M5,1,7200,warm_rates)!=7200) return false;
      mtf.Reset();warm_index=0;Event("WARMUP","7200 completed M5 bars; broker candle boundaries; actual Bid/Ask ticks");
   }
   if(warm_index<7200)
   {
      int n=MathMin(64,7200-warm_index);
      if(!AppendMtfChunk(warm_rates,warm_index,n,false)) return false;
      warm_index+=n;current_bar=warm_rates[warm_index-1].time+300;
      return false;
   }
   if(!SyncMtf(false,false)) return false;
   if(mtf.HigherCount()<100 || mtf.HourCount()<100) {Event("MTF_HISTORY_WAIT","not enough complete H4/H1 intervals");return false;}
   state.last_signal=MathMax(state.last_signal,(long)ToUTC((datetime)mtf.LastHour()));
   if(!Persist()) return false;
   Evaluate(false,"startup_or_resync");ready=true;
   Event("READY","D01 experimental MTF active; wait for next fresh H1 setup");return true;
}
