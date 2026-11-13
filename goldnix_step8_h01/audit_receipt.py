"""Fail fast when a native deal export contains missing or impossible timestamps."""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def audit(trades, operation):
    start = pd.Timestamp(datetime.strptime(operation["TradeFromUTC"], "%Y.%m.%d %H:%M:%S"), tz="UTC").value // 10**9
    end = pd.Timestamp(datetime.strptime(operation["WindowEndUTC"], "%Y.%m.%d %H:%M:%S"), tz="UTC").value // 10**9
    invalid = (trades.entry_utc.lt(start) | trades.entry_utc.ge(end)
               | trades.exit_utc.lt(trades.entry_utc) | trades.exit_utc.gt(end))
    if invalid.any():
        raise ValueError(f"Native deal timestamps outside the registered window: {int(invalid.sum())} rows")
    return {"trade_timestamps_valid": True, "native_trades": len(trades)}


def main():
    here = Path(__file__).resolve().parent
    output = Path(json.loads((here / "LATEST.json").read_text())["output"])
    decision = json.loads((output / "decision.json").read_text())
    result = audit(pd.read_csv(output / "trades.csv"), decision["operational_inputs"])
    print(json.dumps(result))


if __name__ == "__main__":
    main()
