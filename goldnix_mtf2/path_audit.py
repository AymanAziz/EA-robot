"""Descriptive future-path labels for the fixed 788 U01 entries, not new signals."""

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from goldnix_mtf.data import CACHE, ROOT, digest


def main():
    directory = ROOT / "goldnix_mtf2/out/path_audit"
    directory.mkdir(parents=True, exist_ok=False)
    horizons = [5, 15, 30, 60, 180]
    source = ROOT / "goldnix_mtf/out/U01_step6_exit_day_corrected/trades.csv"
    manifest = json.loads((CACHE / "MANIFEST.json").read_text())
    if digest(CACHE / "validated.pkl") != manifest["validated_sha256"]:
        raise PermissionError("Historical input changed")
    registration = {"started_utc": datetime.now(UTC).isoformat(), "horizons_minutes": horizons,
        "trades_sha256": digest(source), "data_sha256": manifest["validated_sha256"],
        "source_sha256": digest(__file__), "scope": "Future labels only for existing U01 entries; no strategy replacement, no new execution, no optimization, no 2026 performance",
        "definitions": "Return at exact future executable-side open, ignoring stops and original time exit only for diagnostic labels. Missing quotes and any intervening gap mark the path incomplete. Favorable/adverse excursions use full bars and have unknown intrabar order. A profitable later quote after a stop does not imply a feasible profitable wider-stop strategy."}
    (directory / "REGISTERED.json").write_text(json.dumps(registration, indent=2) + "\n")
    bars = pd.read_pickle(CACHE / "validated.pkl")
    trades = pd.read_csv(source, keep_default_na=False)
    epochs = bars.epoch_seconds.to_numpy()
    records = []
    for trade in trades.itertuples():
        d = 1 if trade.dir == "BUY" else -1
        side = "bid" if d == 1 else "ask"
        i = trade.entry_index
        for minutes in horizons:
            target = epochs[i] + minutes * 60
            j = int(np.searchsorted(epochs, target))
            complete = j < len(bars) and epochs[j] == target and np.all(np.diff(epochs[i:j + 1]) == 300)
            item = {"entry_index": i, "era": trade.era, "dir": trade.dir, "original_exit": trade.exit_reason,
                    "minutes": minutes, "complete": bool(complete)}
            if complete:
                path = bars.iloc[i:j]
                favorable = path[f"{side}_{'high' if d == 1 else 'low'}"].to_numpy()
                adverse = path[f"{side}_{'low' if d == 1 else 'high'}"].to_numpy()
                item.update(quote_return_r=float(d * (bars[f"{side}_open"].iloc[j] - trade.entry)),
                    mfe_r=float(max(0., np.max(d * (favorable - trade.entry)))),
                    mae_r=float(min(0., np.min(d * (adverse - trade.entry)))))
            records.append(item)
    labels = pd.DataFrame(records)
    labels.to_csv(directory / "labels.csv", index=False)
    summaries = {}
    for minutes, frame in labels.groupby("minutes"):
        valid = frame.loc[frame.complete]
        stopped = valid.loc[valid.original_exit.eq("stop")]
        summaries[str(minutes)] = {"complete": len(valid), "missing_or_gap_paths": len(frame) - len(valid),
            "mean_quote_return_r_ignoring_stops": float(valid.quote_return_r.mean()),
            "positive_quote_share": float(valid.quote_return_r.gt(0).mean()),
            "median_mfe_r": float(valid.mfe_r.median()), "median_mae_r": float(valid.mae_r.median()),
            "originally_stopped_count": len(stopped),
            "stopped_then_positive_quote_share": float(stopped.quote_return_r.gt(0).mean()),
            "stopped_mean_quote_return_r": float(stopped.quote_return_r.mean())}
    result = {"completed_utc": datetime.now(UTC).isoformat(), "registration": registration,
              "horizons": summaries, "interpretation": "Descriptive future labels on previously studied entries; not a backtest of longer holds or proof that original stops were wrong."}
    (directory / "RESULT.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
