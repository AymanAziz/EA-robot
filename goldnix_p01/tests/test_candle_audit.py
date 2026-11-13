import lzma
import struct
import pytest

from goldnix_p01.candle_audit import pair


def payload(rows):
    return lzma.compress(b"".join(struct.pack(">IIIIIf", *r) for r in rows))


def test_placeholder_requires_flat_prices_matching_previous_close_on_both_sides():
    bid = payload(
        [
            (0, 100000, 100000, 100000, 100000, 1),
            (60, 100000, 100000, 100000, 100000, 0),
            (120, 100000, 100200, 100000, 100200, 0),
        ]
    )
    ask = payload(
        [
            (0, 100300, 100300, 100300, 100300, 1),
            (60, 100300, 100300, 100300, 100300, 0),
            (120, 100300, 100500, 100300, 100500, 0),
        ]
    )
    frame = pair(bid, ask, "2005-06-01")
    assert frame.classification.tolist() == ["observed", "placeholder", "unexplained_zero_volume"]
    assert frame.bid_close.iloc[2] == pytest.approx(100.2)
