import lzma
import struct

import pytest

from goldnix_p01.download_candles import collect, decode


def test_daily_binary_prices_and_zero_volume_are_preserved():
    raw = struct.pack(">IIIIIf", 60, 400000, 400200, 399900, 400300, 0.0)
    data = decode(lzma.compress(raw))
    assert data[0]["open"] == 400000
    assert data[0]["volume"] == 0


@pytest.mark.parametrize(
    "raw", [b"truncated", struct.pack(">IIIIIf", 86400, 400000, 400200, 399900, 400300, 1.0)]
)
def test_bad_daily_records_rejected(raw):
    with pytest.raises(ValueError):
        decode(lzma.compress(raw))


def test_holdout_request_refused_before_network_access():
    from datetime import date

    with pytest.raises(ValueError):
        collect(date(2026, 1, 1), date(2026, 1, 2))
