"""Read-only verification of the installed D01 instance; export sanitized evidence."""

import csv
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

from goldnix_auto_m1.ops import status, truth
from goldnix_venue.demo_session import Terminal
from .ops import OUT, public, write
from .build_source import HERE, generate
from .verify import compare


def verify_active():
    t = Terminal()
    latest = json.loads((OUT / "LATEST.json").read_text())
    output, private = Path(latest["output"]), Path(latest["private"])
    current = status()
    if time.time() - int(current.get("captured_utc", 0)) > 15:
        raise ValueError("Stale terminal status")
    if current.get("program") != "GoldnixMTFDemo" or not all(
        truth(current.get(k))
        for k in (
            "identity_matches",
            "connected",
            "data_ready",
            "trade_permission",
            "exclusive_lock_verified",
        )
    ):
        raise ValueError("D01 has not completed operational readiness")
    if any(truth(current.get(k)) for k in ("audit_halt", "state_broken")):
        raise ValueError("Audit/checkpoint halt")

    # Verify semantic risk fields, allowing only sequence and signal cursor advancement.
    def checkpoint(path):
        with path.open() as file:
            rows = dict(csv.reader(file))
        return rows["payload"].split("|")

    before = checkpoint(private / "state_at_handoff.csv")
    after = checkpoint(t.root / "MQL5/Files/GoldnixAutoM5Demo/state.csv")
    preserved = all(a == b for n, (a, b) in enumerate(zip(before, after, strict=True)) if n not in (2, 10))
    if not preserved:
        raise ValueError("Risk state changed: inspect actual fills or normal day rollover before approval")
    baseline = json.loads((output / "BEFORE.json").read_text())
    if current["balance_usc"] != baseline["balance_usc"]:
        raise ValueError("Balance changed during handoff")
    folder = t.root / "MQL5/Files" / current["run_folder"].replace("\\", "/")
    bars = pd.read_csv(folder / "m5_server.csv")
    actual = pd.read_csv(folder / "context.csv")
    n = min(len(bars), len(actual))
    if n < 7200:
        raise ValueError("Full bootstrap not exported")
    features = compare(bars.iloc[:n], actual.iloc[:n])
    write(output / "BROKER_FEATURES.json", features)
    entries = pd.read_csv(folder / "entries.csv")
    if len(entries):
        raise ValueError("New strategy entries occurred; review rather than assert no orders")
    installed = t.root / "MQL5/Experts/GoldnixD01"
    expected = json.loads((OUT / "COMPILED.json").read_text())
    if (
        hashlib.sha256((installed / "GoldnixMTFDemo.ex5").read_bytes()).hexdigest()
        != expected["GoldnixMTFDemo"]
    ):
        raise ValueError("Installed binary differs from compiled source")
    generated = OUT / "review_source"
    generate(generated)
    hashes = {}
    for source in generated.iterdir():
        if source.suffix not in (".mq5", ".mqh"):
            continue
        if (installed / source.name).read_bytes() != source.read_bytes():
            raise ValueError("Installed source differs: " + source.name)
        hashes[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    charts = []
    for chart in (t.root / "MQL5/Profiles/Charts/Default").glob("*.chr"):
        text = chart.read_text(encoding="utf-16")
        if "<expert>" in text:
            charts.append(text)
    if len(charts) != 1 or not all(
        s in charts[0]
        for s in ("GoldnixMTFDemo", "symbol=XAUUSD.c", "period_size=1\n", "EnableDemoTrading=true")
    ):
        raise ValueError("Persistent chart differs from verified deployment")
    report = {
        "verified_utc_epoch": int(time.time()),
        "status": public(current),
        "normal_application_reopen": True,
        "saved_m1_chart_verified": True,
        "risk_state_preserved": preserved,
        "balance_preserved": True,
        "new_orders_in_activation_run": 0,
        "native_policy": json.loads((output / "NATIVE_POLICY.json").read_text()),
        "native_reference": json.loads((output / "NATIVE_FEATURES.json").read_text()),
        "broker_reference": features,
        "source_sha256": hashes,
        "ex5_sha256": expected["GoldnixMTFDemo"],
        "step6": "D01 NOT QUALIFIED; H03 parent failed G1 and G5",
        "step7": "NOT RUN: no untouched frozen holdout",
        "limitations": [
            "Broker clock and P01 profit protection differ from H03 research",
            "Native checks verify policy and integration data, not full trade-path profitability",
            "No forced demo order; current daily risk limit is retained",
        ],
    }
    write(output / "VERIFIED.json", report)
    write(HERE / "evidence/DEPLOYMENT.json", report)
    # Preserve the actual reviewable generated EA, alongside its reproducible builder.
    (HERE / "GoldnixMTFDemo.mq5").write_bytes((generated / "GoldnixMTFDemo.mq5").read_bytes())
    print(
        json.dumps(
            {
                "verified": True,
                "broker_feature_rows": n,
                "risk_state_preserved": True,
                "status": public(current),
            }
        )
    )


if __name__ == "__main__":
    verify_active()
