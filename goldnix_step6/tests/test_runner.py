import pandas as pd
import pytest

from goldnix_step6.runner import evaluate_study


def test_end_to_end_reports_failed_gates_and_all_era_metrics_without_retuning():
    eras = {}
    for name, start in zip("ABCD", ["2005-06-06", "2011-09-05", "2016-01-04", "2021-01-04"]):
        eras[name] = pd.DataFrame({
            "timestamp_utc": pd.date_range(start, periods=48, freq="h", tz="UTC"),
            "era": name, "atr": 1., "signal": [1, -1] * 24,
            "bid_open": 100., "bid_high": 103., "bid_low": 97., "bid_close": 100.,
            "ask_open": 100.1, "ask_high": 103.1, "ask_low": 97.1, "ask_close": 100.1,
        })
    config = dict(vol_ceiling_atr=.3, stop_atr=1., target_atr=2., min_distance_usd=.5,
                  daily_halt_r=-2., friday_no_entry_from_utc="19:00", friday_flat_utc="20:00",
                  holiday_exclusion=True, fill_policy="stop_first",
                  gap_policy="adverse_at_open_favourable_at_target")
    protocol = dict(account_usd=20., baseline_draws=3, baseline_sweeps=5,
                    baseline_seed=7, bootstrap_resamples=100, bootstrap_seed=7,
                    monte_carlo_paths=100, monte_carlo_seed=8, usd_per_price_unit=1.,
                    sampler_retention_excess_warning=.05, sampler_midpoint_difference_se_warning=3.)
    result, trades, baseline, diagnostics = evaluate_study(
        eras, config, protocol, gaps=None, atr_parity=True)
    assert result["gate_inputs"]["baskets"] == 16
    assert result["gate_inputs"]["positive_eras"] == 0
    assert not result["gates"]["G1"]["passed"]
    assert not result["gates"]["G5"]["passed"]
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert set(result["eras"]) == set("ABCD")
    assert len(baseline) == 48
    assert result["pooled"]["reference_break_even_win_rate"] == pytest.approx(0.3666666667)
