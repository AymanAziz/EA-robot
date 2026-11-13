import pandas as pd

from goldnix_p01.parity import compare


def test_extra_or_missing_trade_counts_against_parity_and_m1_is_not_m5():
    native = pd.DataFrame([dict(entry_utc=120, exit_utc=181, side=1, entry=100, exit=101, exit_reason="sl")])
    reference = pd.DataFrame(
        [
            dict(entry_utc=120, exit_utc=241, side=1, entry=100, exit=101, exit_reason="sl"),
            dict(entry_utc=360, exit_utc=420, side=-1, entry=100, exit=99, exit_reason="tp"),
        ]
    )
    result, _ = compare(native, reference)
    assert result["matching_trades"] == 0
    assert result["comparison_rows"] == 2
    assert result["status"] == "FAIL"
