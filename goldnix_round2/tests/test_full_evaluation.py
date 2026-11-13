import numpy as np
import pytest

from goldnix_round2.execution import run_managed
from goldnix_round2.full_evaluation import run_baseline, assemble_result
from goldnix_round2.tests.test_execution import config, frame
from goldnix_step6.baseline import schedule_is_valid


@pytest.mark.parametrize("mode", ["fixed", "break_even", "trail"])
def test_random_entries_share_eligibility_fills_counts_and_daily_envelope(mode):
    rng = np.random.default_rng(18)
    bars = frame(100 + rng.normal(size=250).cumsum(), signals=rng.choice([-1, 0, 1], size=250))
    bars["buy_eligible"] = np.arange(len(bars)) % 3 == 0
    bars["sell_eligible"] = np.arange(len(bars)) % 4 == 0
    settings = config(exit_management=mode)
    observed = run_managed(bars, settings)
    baseline, diagnostics = run_baseline(bars, settings, observed, draws=5, sweeps=4, seed=23)
    assert len(diagnostics) == 5
    assert baseline.signal_index.nunique() > observed.entry_ts.nunique()
    for _, draw in baseline.groupby("draw"):
        assert draw.dir.value_counts().to_dict() == observed.dir.value_counts().to_dict()
        assert schedule_is_valid(draw, daily_halt_r=settings["daily_halt_r"])
    for trade in baseline.itertuples():
        assert bars.loc[trade.signal_index, "buy_eligible" if trade.dir == "BUY" else "sell_eligible"]
        isolated = bars.copy()
        isolated["signal"] = 0
        isolated.loc[trade.signal_index, "signal"] = 1 if trade.dir == "BUY" else -1
        expected = run_managed(isolated, settings).iloc[0]
        assert trade.entry_ts == expected.entry_ts
        assert trade.exit_ts == expected.exit_ts
        assert trade.r_multiple == pytest.approx(expected.r_multiple)


def test_numerical_scenario_pass_cannot_become_real_account_approval():
    screen = {"id": "TEST", "candidate": {}, "baskets": 1200, "positive_eras": 4,
              "gap_risk_share": .01, "max_fill_delta_pp": 0., "G9": True,
              "p99_usd_at_verified_1oz": 100., "p99_usd_at_product_scenario_0_01oz": 1.,
              "bootstrap": {"selection_lower": -.04}}
    bootstrap = {"mean_lower": .02, "edge_point": .2, "edge_lower": .03}
    result = assemble_result(screen, bootstrap, {"A": {"mixing_warning": False}})
    assert result["product_scenario"]["numerical_verdict"] == "PASS"
    assert result["verified_exposure"]["numerical_verdict"] == "NOT_TRADEABLE_AT_THIS_ACCOUNT_SIZE"
    assert result["approval"] is False
    assert result["account_verified"] is False
    assert result["selection_adjusted_positive"] is False
