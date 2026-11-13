"""Derive the demo EA from the unchanged P01 operational shell, with checked anchors."""

from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "goldnix_auto_m1"


def generate(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    original = (BASE / "GoldnixAutoM1.mq5").read_text()
    code = original
    changes = []

    def replace(old, new):
        nonlocal code
        if code.count(old) != 1:
            raise ValueError("Source anchor changed: " + old[:100])
        code = code.replace(old, new)
        changes.append({"old": old, "new": new})

    def function(name, new):
        match = re.search(r"^(?:bool|void|string) " + name + r"\([^\n]*\)\n\{.*?^\}", code, re.M | re.S)
        if match is None:
            raise ValueError(name)
        replace(match[0], new)

    replace('#property version "1.20"', '#property version "2.00"')
    replace(
        '#property description "Automatic M1 capture and bounded DEMO trading while MT5 is open."',
        '#property description "D01 EXPERIMENTAL DEMO: H4 trend, H1 entry, M15/M5 fakeout, P01 profit protection. NOT QUALIFIED."',
    )
    replace(
        '#include "ProfitManager.mqh"',
        '#include "ProfitManager.mqh"\n#include "MtfPolicy.mqh"\n#include "MtfJournal.mqh"',
    )
    replace(
        "input long ExecutionCheckRequestUtc=0; // Explicit one-time DEMO check; expires after one hour.", ""
    )
    replace(
        "QuoteBar bars[];",
        "MtfContext mtf;\nFakeoutState fakeout={};\nint contextfile=INVALID_HANDLE;\ndatetime last_fakeout_request=0;\nbool SaveFakeout();",
    )
    function("AppendBar", "")
    replace(
        'string ExecutionReceipt() {return ROOT+"\\\\execution_check_"+(string)ExecutionCheckRequestUtc+".csv";}',
        "",
    )
    a = code.index(
        "   int direction=0;double atr=0,distance=0,spread=0,nominal=0;", code.index("void Evaluate")
    )
    b = code.index("   MqlDateTime t;", a)
    replace(
        code[a:b],
        """   int direction=0;double atr=0,distance=0,spread=0,nominal=0,level=0,buffer=0;
   if(!mtf.Signal(direction,atr,distance,spread,nominal,level,buffer)) {last_decision="warming_h1";return;}
   datetime now=TimeGMT();long signal_utc=(long)ToUTC((datetime)mtf.LastHour());
   string signal_context=context;
""",
    )
    replace(
        'else if(direction==0) reason=execution_check ? "execution_check_doji" : "no_breakout";\n      else if(!check_sizing_ok) reason="execution_check_cost_exceeds_budget";',
        'else if(!mtf.TrendReady((long)TimeTradeServer())) reason="h4_not_ready_or_stale";\n      else if(direction==0) reason="no_breakout";\n      else if(mtf.Trend((long)TimeTradeServer())!=direction) reason="h4_trend_disagrees";',
    )
    # Both pre-send freshness guards now refer to the H1 signal close.
    if code.count("signal_utc+(AUTO_BAR_SECONDS+10)") != 2:
        raise ValueError("Freshness guards changed")
    code = code.replace("signal_utc+(AUTO_BAR_SECONDS+10)", "signal_utc+3610")
    a = code.index("   if(execution_check)\n", code.index("void Evaluate"))
    b = code.index("   state.attempts++;", a)
    replace(code[a:b], "")
    replace(
        "   if(!Persist()) return;\n   if(!CanTrade()",
        """   if(!Persist()) return;
   ZeroMemory(fakeout);fakeout.magic=state.pending_magic;fakeout.entry=state.pending_server;
   fakeout.direction=direction;fakeout.level=level;fakeout.buffer=buffer;
   if(!SaveFakeout()) {Fatal("fakeout_entry_geometry_not_durable");return;}
   if(!CanTrade()""",
    )
    replace(
        'string order_comment=execution_check ? "Goldnix M1 execution check" : "Goldnix auto M1 demo";',
        'string order_comment="Goldnix D01 MTF demo";',
    )
    replace("execution_check ? ExecutionCheckRequestUtc : 0", "0")
    replace(
        '   if(!sent || trade.ResultRetcode()!=TRADE_RETCODE_DONE) {Fatal("order_not_fully_confirmed");CloseOwned();return;}',
        """   if(!sent || trade.ResultRetcode()!=TRADE_RETCODE_DONE) {Fatal("order_not_fully_confirmed");CloseOwned();return;}
   // A warning must use an entire interval after the confirmed fill.
   fakeout.entry=(long)TimeTradeServer();
   if(!SaveFakeout()) {Fatal("fakeout_fill_time_not_durable");CloseOwned();return;}""",
    )
    function("WarmupStep", "")
    replace("void OnTimer()", '#include "MtfRuntime.mqh"\n\nvoid OnTimer()')
    replace("   bool captured=CaptureTicks();", "   ManageFakeout();\n   bool captured=CaptureTicks();")
    replace(
        'display_state="Capturing / warming completed M1 bars";',
        'display_state="Warming M5 "+(string)MathMax(warm_index,0)+"/7200 | H4 "+(string)mtf.HigherCount()+"/100";',
    )
    replace("WarmupStep();Status();return;", "WarmupStep();last_timer=TimeGMT();Status();return;")
    a = code.index("   datetime next=iTime(_Symbol,PERIOD_M1,0);")
    b = code.index("   string risk=RiskReason", a)
    replace(
        code[a:b],
        """   if(!SyncMtf(true,reconciled))
   {ready=false;warm_index=-1;Event("RESYNC","history gap; no catch-up entries");}
""",
    )
    replace(
        'else display_state="CAPTURING | M1 analysis active";',
        'else display_state="CAPTURING | H4/H1/M15/M5 experimental analysis active";',
    )
    a = code.index("   Comment(")
    b = code.index("   if(TimeGMT()-last_status", a)
    replace(
        code[a:b],
        """   Comment("GOLDNIX D01 MTF | EXPERIMENTAL DEMO | NOT QUALIFIED\\n",display_state,
      "\\nChart M1 | H4 trend -> H1 entry -> M15 warning -> M5 confirmation\\n",permission,
      "\\nBroker candle clock | BUY and SELL | 0.01 lot | 5 USC max planned risk",
      "\\nAttempts ",state.attempts,"/7 | daily R ",DoubleToString(state.realized_r,4)," | limit -2R",
      "\\nLast decision: ",last_decision," | direction ",last_direction,
      "\\nProfit protection ON | original TP retained | H4 complete: ",mtf.HigherCount(),
      "\\nStep 6: FAIL / incomplete | Step 7: no untouched holdout",
      "\\nCaptured ticks: ",captured_ticks," | Open positions: ",OwnPositions(),
      "\\nMalaysia: ",TimeToString(TimeGMT()+8*3600,TIME_DATE|TIME_SECONDS));
""",
    )
    replace('FileWrite(f,"program","GoldnixAutoM1");', 'FileWrite(f,"program","GoldnixMTFDemo");')
    replace(
        'FileWrite(f,"version","1.20");FileWrite(f,"execution_check_request_utc",ExecutionCheckRequestUtc);',
        """FileWrite(f,"version","2.00");FileWrite(f,"variant","D01_EXPERIMENTAL");
   FileWrite(f,"signal_timeframe","H1");FileWrite(f,"context_timeframes","H4 > H1 > M15 > M5");
   FileWrite(f,"candle_clock","broker_server");FileWrite(f,"qualification","NOT_QUALIFIED");
   FileWrite(f,"step6","FAIL_INCOMPLETE");FileWrite(f,"step7","NO_UNTOUCHED_HOLDOUT");
   FileWrite(f,"h4_complete_bars",mtf.HigherCount());FileWrite(f,"h4_direction",mtf.Trend((long)TimeTradeServer()));
   FileWrite(f,"h4_ready",mtf.TrendReady((long)TimeTradeServer()));FileWrite(f,"warmup_m5_bars",warm_index);
   FileWrite(f,"fakeout_warning_server",fakeout.warning);FileWrite(f,"fakeout_exit_intent",fakeout.exit_intent);""",
    )
    replace(
        '   FileWrite(f,"execution_check_consumed",ExecutionCheckRequestUtc>0 && FileIsExist(ExecutionReceipt(),0));\n   FileWrite(f,"execution_check_pending",ExecutionCheckAvailable(ExecutionCheckRequestUtc,(long)TimeGMT(),FileIsExist(ExecutionReceipt(),0)));\n',
        "",
    )
    replace(
        "   if(events!=INVALID_HANDLE) FileClose(events);if(barfile!=INVALID_HANDLE) FileClose(barfile);",
        "   if(contextfile!=INVALID_HANDLE) FileClose(contextfile);contextfile=INVALID_HANDLE;\n   if(events!=INVALID_HANDLE) FileClose(events);if(barfile!=INVALID_HANDLE) FileClose(barfile);",
    )
    replace(" || ExecutionCheckRequestUtc<0", "")
    replace("M1_AUTO_", "D01_MTF_")
    replace("\\\\m1.csv", "\\\\m5_server.csv")
    replace(
        "   int flags=FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ;",
        """   mtf.Reset();
   int flags=FILE_WRITE|FILE_CSV|FILE_ANSI|FILE_SHARE_READ;
   contextfile=FileOpen(run_folder+"\\\\context.csv",flags,',');
   if(contextfile==INVALID_HANDLE) {CloseFiles();return INIT_FAILED;}
   FileWrite(contextfile,"decision_server","h4_count","h4_available_server","ema50","h4_ready","h4_direction","h1_open_server","h1_ready","direction","atr","level","buffer");""",
    )
    replace('FileWrite(barfile,"epoch_seconds"', 'FileWrite(barfile,"server_seconds"')
    if "execution_check" in code.lower() and "execution_check_request_utc" not in code:
        raise ValueError("Unexpected execution check path")
    (destination / "GoldnixMTFDemo.mq5").write_text(code)
    for source in [
        *(
            BASE / n
            for n in ("AutoM1Policy.mqh", "ProfitPolicy.mqh", "ProfitJournal.mqh", "ProfitManager.mqh")
        ),
        *HERE.glob("*.mqh"),
    ]:
        (destination / source.name).write_bytes(source.read_bytes())
    manifest = {
        "base_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "generated_sha256": hashlib.sha256(code.encode()).hexdigest(),
        "changes": changes,
    }
    (destination / "SOURCE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    generate(HERE / "out" / "source")
