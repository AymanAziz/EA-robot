"""Generate a guarded tester copy; production signal/protection logic stays unchanged."""

from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "goldnix_auto_m1"


def generate(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    original = (SOURCE / "GoldnixAutoM1.mq5").read_text()
    code = original
    substitutions = []

    def replace(old, new):
        nonlocal code
        if code.count(old) != 1:
            raise ValueError("Production adapter anchor changed: " + old[:80])
        code = code.replace(old, new)
        substitutions.append({"old": old, "new": new})

    identity = re.search(r"bool Identity\(\)\n\{.*?\n\}", code, re.S).group()
    replace(
        identity,
        'bool Identity()\n{\n   return MQLInfoInteger(MQL_TESTER) && ExpectedLogin==1 && _Symbol=="XAUUSD.c";\n}',
    )
    replace(
        "bool Connected() {return Identity() && TerminalInfoInteger(TERMINAL_CONNECTED);}",
        "bool Connected() {return Identity();}",
    )
    replace(
        "bool CanTrade() {return Connected() && EnableDemoTrading && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED);}",
        "bool CanTrade() {return Identity() && EnableDemoTrading;}",
    )
    replace('const string ROOT="GoldnixAutoM5Demo";', 'string ROOT="P01Replay_"+ReplayRunId;')
    replace(
        "if(MQLInfoInteger(MQL_TESTER) || ExpectedLogin<=0",
        "if(!MQLInfoInteger(MQL_TESTER) || ExpectedLogin!=1",
    )
    for old, new in (
        ("void OnTimer()", "void CoreTimer()"),
        ("int OnInit()", "int CoreInit()"),
        ("void OnDeinit(const int reason)", "void CoreDeinit(const int reason)"),
    ):
        replace(old, new)
    generated = '#include "ReplayEnvironment.mqh"\n' + code + '\n#include "ReplayCallbacks.mqh"\n'
    (destination / "P01NativeReplay.mq5").write_text(generated)
    manifest = {
        "production_source_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "generated_source_sha256": hashlib.sha256(generated.encode()).hexdigest(),
        "changes": substitutions,
        "tester_only": True,
        "money_model": "USD tester account exposed as USC to production code",
    }
    for path in list(SOURCE.glob("*.mqh")) + [HERE / "ReplayEnvironment.mqh", HERE / "ReplayCallbacks.mqh"]:
        (destination / path.name).write_bytes(path.read_bytes())
    (destination / "ADAPTER_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
