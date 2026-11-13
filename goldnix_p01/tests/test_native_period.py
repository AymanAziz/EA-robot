import pytest

from goldnix_p01.native_run import validate_period


def test_fixed_winter_offset_cannot_be_used_for_summer_or_dst_crossing():
    validate_period("2024.01.01", "2024.03.01")
    for start, end in [("2024.07.01", "2024.08.01"), ("2024.03.01", "2024.04.02")]:
        with pytest.raises(ValueError, match="offset"):
            validate_period(start, end)
