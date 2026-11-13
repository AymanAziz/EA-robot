"""Independent journal reconciliation and preservation checks for a completed run."""

import hashlib
import json
import re
from pathlib import Path

import pandas as pd

from goldnix_mtf.evaluate import preserved_freezes
from goldnix_venue.demo_session import Terminal

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main():
    output = Path(json.loads((HERE / "LATEST.json").read_text())["output"])
    if (output / "FROZEN.json").exists():
        raise PermissionError("Run already frozen")
    config = json.loads((output / "decision.json").read_text())
    deals = {}
    pattern = re.compile(r"(\d{4}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2})\s+deal #(\d+) (buy|sell) 0\.01 XAUUSD\.c at ([\d.]+) done")
    for match in pattern.finditer((output / "tester_journal.txt").read_text()):
        stamp, ticket, side, price = match.groups()
        epoch = int(pd.Timestamp(stamp, tz="UTC").timestamp())-config["operational_inputs"]["ServerOffsetSeconds"]
        value = {"utc": epoch, "side": side.upper(), "price": float(price)}
        if ticket in deals and deals[ticket] != value:
            raise ValueError("Contradictory duplicate journal event")
        deals[ticket] = value
    native = pd.read_csv(output / "trades.csv")
    if len(deals) != 2*len(native):
        raise ValueError("Journal has extra or missing trade events")
    for trade in native.itertuples(index=False):
        entry, exit_ = deals[str(trade.entry_deal)], deals[str(trade.exit_deal)]
        assert entry["utc"] == trade.entry_utc and exit_["utc"] == trade.exit_utc
        assert entry["side"] == trade.dir and exit_["side"] != trade.dir
        assert abs(entry["price"]-trade.entry) < 1e-8 and abs(exit_["price"]-trade.exit) < 1e-8
    preserved_freezes()
    original = ROOT / "goldnix_mtf2/out/H01_S11_M5_REPLAY"
    frozen = json.loads((original / "FROZEN.json").read_text())["artifact_sha256"]
    for name, expected in frozen.items():
        if hashlib.sha256((original / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Frozen H01 artifact changed: {name}")
    prior = HERE / "out/S8_20261112T152435Z"
    prior_hashes = json.loads((prior / "FROZEN.json").read_text())["artifact_sha256"]
    for name, expected in prior_hashes.items():
        if hashlib.sha256((prior / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Previous Step8 result changed: {name}")
    terminal = Terminal()
    old = ROOT / "goldnix_venue/out/demo_session_M5_20261112T114339Z/source"
    for name in ("DemoRoundTrip", "DemoSession", "VerifyDemoBatch"):
        for suffix in ("mq5", "ex5"):
            filename = f"{name}.{suffix}"
            assert (old / filename).read_bytes() == (terminal.root / "MQL5/Scripts/Goldnix" / filename).read_bytes()
    compared = pd.read_csv(output / "trade_comparison.csv")
    summary = {"journal_deals": len(deals), "journal_reconciled_trades": len(native),
        "v1_v2_freezes_intact": True, "h01_frozen_artifacts_verified": len(frozen),
        "prior_step8_frozen_artifacts_verified": len(prior_hashes), "installed_demo_files_unchanged": 6,
        "entry_price_max_abs_difference": float((compared.entry_ea-compared.entry_python).abs().max()),
        "exit_price_max_abs_difference": float((compared.exit_ea-compared.exit_python).abs().max()),
        "native_price_pnl_usd_before_fees_and_currency_rounding": float(((native.exit-native.entry)*native.dir.map({"BUY": 1, "SELL": -1})*.01).sum())}
    (output / "VERIFICATION.json").write_text(json.dumps(summary, indent=2)+"\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
