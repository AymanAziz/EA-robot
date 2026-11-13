import numpy as np
import pandas as pd

from goldnix_h02.method import prepare_context


def bars(count):
    result = pd.DataFrame({"epoch_seconds": 1704067200 + np.arange(count) * 300})
    result["timestamp_utc"] = pd.to_datetime(result.epoch_seconds, unit="s", utc=True)
    for side, spread in [("bid", 0), ("ask", .2)]:
        for kind, shift in [("open", 0), ("high", .2), ("low", -.2), ("close", .1)]:
            result[f"{side}_{kind}"] = 100 + np.arange(count) * .01 + spread + shift
    return result


def test_higher_context_becomes_available_at_close_not_inside_its_candle():
    data = bars(4810)
    result = prepare_context(data)
    assert not result["h4_ready"][4799]
    assert result["h4_ready"][4800]
    assert result["h4_direction"][4800] == 1
    assert result["h4_available_at"][4800] == data.epoch_seconds.iloc[4800]


def test_context_is_causal_mirrored_and_missing_higher_bucket_expires():
    data = bars(4950)
    full = prepare_context(data)
    prefix = prepare_context(data.iloc[:4820])
    np.testing.assert_array_equal(full["h4_direction"][:4820], prefix["h4_direction"])
    reflected = data.copy()
    for side, other in [("bid", "ask"), ("ask", "bid")]:
        for kind, inverse in [("open", "open"), ("high", "low"), ("low", "high"), ("close", "close")]:
            reflected[f"{side}_{kind}"] = 500 - data[f"{other}_{inverse}"]
    np.testing.assert_array_equal(prepare_context(reflected)["h4_direction"], -full["h4_direction"])
    missing = data.drop(index=4810).reset_index(drop=True)
    result = prepare_context(missing)
    states = dict(zip(missing.epoch_seconds, result["h4_ready"]))
    assert states[data.epoch_seconds.iloc[4800]]
    assert not states[data.epoch_seconds.iloc[4848]]
    assert states[data.epoch_seconds.iloc[4896]]


def test_duplicate_or_off_grid_input_is_rejected():
    import pytest
    data = bars(60)
    with pytest.raises(ValueError, match="grid"):
        prepare_context(pd.concat([data, data.iloc[-1:]], ignore_index=True))
    data.loc[3, "epoch_seconds"] += 1
    with pytest.raises(ValueError, match="grid"):
        prepare_context(data)
