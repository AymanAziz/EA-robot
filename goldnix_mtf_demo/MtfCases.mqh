QuoteBar FixtureBar(const long stamp,const double price)
{
   QuoteBar b={};b.server=(datetime)stamp;b.bo=price;b.bc=price;b.bh=price+.1;b.bl=price-.1;
   b.ao=price+.2;b.ac=price+.2;b.ah=price+.3;b.al=price+.1;b.ticks=2;return b;
}
void RunMtfCases()
{
   MtfContext c;c.Reset();
   for(int j=0;j<4800-1;j++) Check(c.Push(FixtureBar((long)j*300,100+j*.01)),"chronological quote accepted");
   Check(!c.TrendReady(4800*300),"forming 100th H4 candle is unavailable");
   Check(c.Push(FixtureBar(4799*300,147.99)),"last closed M5 accepted");
   Check(c.TrendReady(4800*300) && c.Trend(4800*300)==1,"100 completed rising H4 candles allow BUY");
   Check(!c.TrendReady(4800*300+14400),"stale H4 context blocks entries");
   Check(!c.Push(FixtureBar(4799*300,147.99)),"duplicate closed candle rejected");
   FakeoutState f={};f.direction=1;f.entry=0;f.level=100;f.buffer=.2;
   Check(FakeoutStep(f,0,99)==0 && FakeoutStep(f,300,99)==0,"M5 weakness alone cannot warn");
   Check(FakeoutStep(f,600,99)==1 && !f.exit_intent,"complete M15 starts warning only");
   Check(FakeoutStep(f,900,99)==2 && f.exit_intent,"next consecutive adverse M5 confirms exit");
   Check(FakeoutStep(f,1800,102)==2,"confirmed exit survives later reclaim and missing quote");
   FakeoutState reclaim={};reclaim.direction=1;reclaim.level=100;reclaim.buffer=.2;
   FakeoutStep(reclaim,0,99);FakeoutStep(reclaim,300,99);FakeoutStep(reclaim,600,99);
   Check(FakeoutStep(reclaim,900,100)==0 && !reclaim.exit_intent,"reclaim cancels unconfirmed warning");
   FakeoutState gap={};gap.direction=1;gap.level=100;gap.buffer=.2;
   FakeoutStep(gap,0,99);FakeoutStep(gap,300,99);FakeoutStep(gap,600,99);
   Check(FakeoutStep(gap,1200,99)==0 && !gap.exit_intent,"missing confirmation candle cancels warning");
   FakeoutState sell={};sell.direction=-1;sell.level=100;sell.buffer=.2;
   FakeoutStep(sell,0,101);FakeoutStep(sell,300,101);
   Check(FakeoutStep(sell,600,101)==1 && FakeoutStep(sell,900,101)==2,"SELL fakeout mirrors BUY");
   FakeoutState partial={};partial.direction=1;partial.entry=1;partial.level=100;partial.buffer=.2;
   FakeoutStep(partial,0,99);FakeoutStep(partial,300,99);
   Check(FakeoutStep(partial,600,99)==0,"M15 containing pre-entry prices cannot warn");
   c.Reset();
   for(int j=0;j<4800;j++) if(j!=5) c.Push(FixtureBar((long)j*300,200-j*.01));
   Check(c.HigherCount()==99 && !c.TrendReady(4800*300),"missing M5 excludes entire H4 bucket");
   for(int j=4800;j<4848;j++) c.Push(FixtureBar((long)j*300,200-j*.01));
   Check(c.Trend(4848*300)==-1,"100 complete falling H4 candles allow SELL");
}
