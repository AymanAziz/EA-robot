import pandas as pd

from goldnix_mtf2.replay import choose, material_gap


def test_material_gap_must_be_crossed_while_held():
    gaps = pd.DataFrame({"gap_start": pd.to_datetime(["2024-02-05T10:00Z"]),
                         "gap_end": pd.to_datetime(["2024-02-05T15:00Z"])})
    assert material_gap(gaps, "2024-02-05T09:00Z", "2024-02-05T15:00Z")
    assert not material_gap(gaps, "2024-02-05T09:00Z", "2024-02-05T10:00Z")
    assert not material_gap(gaps, "2024-02-05T15:00Z", "2024-02-05T16:00Z")


def test_signal_selection_preserves_direction_and_loss_halt():
    pool = pd.DataFrame({"h1_signal_index": [0, 0, 1, 2], "dir": ["BUY", "SELL", "BUY", "SELL"],
                         "entry_index": [1, 1, 4, 7], "exit_index": [3, 2, 6, 8],
                         "entry_day": [1] * 4, "exit_day": [1] * 4,
                         "r_multiple": [-1.1, 1.0, -1.1, 2.]})
    selected, indices = choose(pool, {0: 1, 1: 1, 2: -1}, -2.)
    assert indices == [0, 2]
    assert selected.dir.tolist() == ["BUY", "BUY"]
