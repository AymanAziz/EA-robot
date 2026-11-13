"""Finite, disclosed in-sample screening; no independent approval claims."""

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from goldnix_research.candidates import prepare_candidate
from ingest.gaps import find_gaps
from sim.engine import run_engine
from ingest.ingest import load_bars
from params.config import load_yaml
from goldnix_step7.runner import preflight


def screen_statistics(trades, *, start, end, trials, resamples, seed):
    """Calendar-month bootstrap with the unchanged raw G1 and an extra search bound."""
    if trades.empty or trials < 1 or resamples < 2:
        raise ValueError("Nonempty trades and positive trial/resample counts required")
    months = pd.period_range(pd.Timestamp(start).strftime("%Y-%m"),
                             pd.Timestamp(end).strftime("%Y-%m"), freq="M").astype(str)
    labels = pd.to_datetime(trades.exit_ts, utc=True).dt.strftime("%Y-%m")
    if not labels.isin(months).all() or not np.isfinite(trades.r_multiple).all():
        raise ValueError("Trades must be finite and within the declared calendar")
    monthly = trades.groupby(labels).r_multiple.agg(["sum", "count"]).reindex(months, fill_value=0)
    sums, counts = monthly["sum"].to_numpy(), monthly["count"].to_numpy()
    rng = np.random.default_rng(seed)
    means, rejected = [], 0
    while len(means) < resamples:
        chosen = rng.integers(len(months), size=(min(1000, resamples - len(means)), len(months)))
        n = counts[chosen].sum(axis=1)
        accepted = n > 0
        rejected += int((~accepted).sum())
        if rejected > resamples * 100:
            raise ValueError("Too few populated calendar blocks")
        means.extend((sums[chosen[accepted]].sum(axis=1) / n[accepted]).tolist())
    return {
        "mean_r": float(trades.r_multiple.mean()), "mean_lower": float(np.quantile(means, .05)),
        "standard_error": float(np.std(means, ddof=1)),
        "selection_lower": float(np.quantile(means, .05 / trials)),
        "selection_alpha": .05 / trials, "months": len(months),
        "empty_months": int((counts == 0).sum()), "empty_resamples_rejected": rejected,
        "resamples": resamples,
    }


def screen_candidate(eras, candidate, config, protocol, *, prepare=prepare_candidate):
    """Run both fill policies and retain every candidate's screening failures."""
    config = {**config, "stop_atr": candidate["stop_atr"],
              "target_atr": candidate["stop_atr"] * candidate["reward_ratio"]}
    frames, era_results, starts, ends = [], {}, [], []
    for name, raw in eras.items():
        prepared = prepare(raw, candidate)
        prepared["signal"] = prepared.signal.where(np.isfinite(prepared.atr) & prepared.atr.gt(0), 0)
        start = raw.attrs.get("trade_start", raw.timestamp_utc.min())
        prepared = prepared.loc[prepared.timestamp_utc.ge(start)].reset_index(drop=True)
        starts.append(prepared.timestamp_utc.min())
        ends.append(prepared.timestamp_utc.max())
        gaps = find_gaps(prepared)
        trades = run_engine(prepared, config, gaps=gaps).trades
        alternative = run_engine(prepared, {**config, "fill_policy": "target_first"}, gaps=gaps).trades
        delta = (abs(float(trades.r_multiple.gt(0).mean())
                     - float(alternative.r_multiple.gt(0).mean())) * 100
                 if len(trades) and len(alternative) else None)
        era_results[name] = {"baskets": len(trades),
                            "mean_r": float(trades.r_multiple.mean()) if len(trades) else None,
                            "fill_delta_pp": delta}
        frames.append(trades)
    trades = pd.concat(frames, ignore_index=True)
    stats = (screen_statistics(trades, start=min(starts), end=max(ends),
                               trials=protocol["trial_count"], resamples=protocol["bootstrap_resamples"],
                               seed=protocol["bootstrap_seed"])
             if len(trades) else {"mean_r": None, "mean_lower": None, "selection_lower": None})
    positive = sum(r["mean_r"] is not None and r["mean_r"] > 0 for r in era_results.values())
    gap_share = float(trades["flags"].eq("gap_risk").mean()) if len(trades) else None
    deltas = [r["fill_delta_pp"] for r in era_results.values()]
    maximum_delta = max(deltas) if all(d is not None for d in deltas) else None
    gates = {
        "G1": stats["mean_lower"] is not None and stats["mean_lower"] > 0,
        "G4": positive >= 3, "G5": len(trades) >= 1000,
        "G6": gap_share is not None and gap_share <= .10,
        "G8": maximum_delta is not None and maximum_delta <= 8,
    }
    return {"id": candidate["id"], "candidate": candidate, "baskets": len(trades),
            "eras": era_results, "positive_eras": positive, "gap_risk_share": gap_share,
            "max_fill_delta_pp": maximum_delta, "bootstrap": stats, **gates,
            "eligible_for_full_evaluation": all(gates.values()),
            "approval": "EXPLORATORY_ONLY", "not_evaluated": ["G2", "G3", "G7", "G9"]}, trades


@lru_cache(maxsize=1)
def _historical_bars(path):
    return load_bars(path)


def candidate_eras(root, candidate, protocol):
    """Apply the historical era boundaries and a causal warm-up, never 2026 data."""
    root = Path(root)
    bars = _historical_bars(str(root / protocol["data_path"]))
    windows = load_yaml(root / "goldnix/data/eras.yaml")["eras"]
    times = pd.DatetimeIndex(bars.timestamp_utc)
    eras = {}
    for name, window in windows.items():
        start, end = pd.Timestamp(window["start_utc"]), pd.Timestamp(window["end_utc"])
        first, last = times.searchsorted(start), times.searchsorted(end, side="right")
        frame = bars.iloc[max(0, first - candidate["warmup_bars"]):last].copy()
        frame["era"] = name
        frame.attrs["trade_start"] = start
        eras[name] = frame
    return eras


def _worker(root, candidate, protocol):
    eras = candidate_eras(root, candidate, protocol)
    config = load_yaml(Path(root) / "goldnix/params/decision.yaml")
    return screen_candidate(eras, candidate, config, protocol)


def main():
    root = Path(__file__).resolve().parents[1]
    preflight(root)
    directory = root / "goldnix_research"
    protocol = json.loads((directory / "protocol.json").read_text())
    if protocol["holdout_access"] or protocol["trial_count"] != len(protocol["candidate_configs"]):
        raise ValueError("Invalid finite-search protocol")
    data_path = root / protocol["data_path"]
    if hashlib.sha256(data_path.read_bytes()).hexdigest() != protocol["data_sha256"]:
        raise PermissionError("Historical data hash mismatch")
    output = directory / "out/screen"
    output.mkdir(parents=True, exist_ok=False)
    source = {name: (directory / name).read_bytes() for name in ("screen.py", "candidates.py", "protocol.json")}
    (output / "source").mkdir()
    for name, payload in source.items():
        (output / "source" / name).write_bytes(payload)
    manifest = {name: hashlib.sha256(payload).hexdigest() for name, payload in source.items()}
    started = datetime.now(UTC).isoformat()
    (output / "STARTED.json").write_text(json.dumps({"started_utc": started, "source_sha256": manifest}, indent=2))
    results = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_worker, str(root), c, protocol): c["id"] for c in protocol["candidate_configs"]}
        for future in as_completed(futures):
            result, trades = future.result()
            run = output / result["id"]
            run.mkdir()
            trades.to_csv(run / "trades.csv", index=False)
            (run / "metrics.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
            # The unchanged Aroon control must reproduce the frozen V1 trades exactly.
            c = result["candidate"]
            if c["family"] == "aroon" and c["period"] == 70 and c["threshold"] == 50 and c["stop_atr"] == 1:
                expected = pd.read_csv(root / "goldnix_step6/out/V1_4b823fa2ca89/trades.csv",
                                       parse_dates=["entry_ts", "exit_ts"])
                columns = ["entry_ts", "exit_ts", "dir", "r_multiple"]
                pd.testing.assert_frame_equal(trades[columns].reset_index(drop=True), expected[columns],
                                              check_dtype=False, atol=1e-10, rtol=1e-10)
            results.append(result)
            stats = result["bootstrap"]
            print(json.dumps({"finished": len(results), "of": protocol["trial_count"],
                              "id": result["id"], "baskets": result["baskets"],
                              "mean_r": stats["mean_r"], "lower": stats["mean_lower"],
                              "positive_eras": result["positive_eras"],
                              "qualifies": result["eligible_for_full_evaluation"]}), flush=True)
    preflight(root)
    for name, digest in manifest.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise PermissionError("Screening source changed during execution")
    if hashlib.sha256(data_path.read_bytes()).hexdigest() != protocol["data_sha256"]:
        raise PermissionError("Historical data changed during execution")
    results.sort(key=lambda r: r["id"])
    qualified = [r for r in results if r["eligible_for_full_evaluation"]]
    selected = max(qualified, key=lambda r: (r["bootstrap"]["selection_lower"], r["id"])) if qualified else None
    summary = {"status": "SCREEN_COMPLETE", "approval": "EXPLORATORY_ONLY",
               "started_utc": started, "completed_utc": datetime.now(UTC).isoformat(),
               "source_sha256": manifest, "data_sha256": protocol["data_sha256"],
               "trial_count": len(results), "qualified": [r["id"] for r in qualified],
               "selected": selected["id"] if selected else None, "results": results}
    (output / "SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"status": summary["status"], "qualified": summary["qualified"],
                      "selected": summary["selected"]}), flush=True)


if __name__ == "__main__":
    main()
