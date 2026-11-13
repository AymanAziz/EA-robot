import pytest

from goldnix_step7.collapse import collapse_check


def test_collapse_accepts_equality_using_both_standard_errors_and_sample_sd():
    # R=[-4,4] has sample SE=4; combined with SE_in=3 gives SE=5.
    result = collapse_check([-4, 4], in_sample_mean=10, in_sample_se=3)
    assert result["holdout_se"] == pytest.approx(4)
    assert result["threshold_r"] == pytest.approx(0)
    assert result["verdict"] == "PASS"


@pytest.mark.parametrize("returns", [[], [1]])
def test_fewer_than_two_baskets_cannot_pass(returns):
    result = collapse_check(returns, in_sample_mean=0, in_sample_se=0.1)
    assert result["verdict"] == "INSUFFICIENT_DATA"
    assert result["holdout_se"] is None
    assert result["threshold_r"] is None


@pytest.mark.parametrize("returns,mean,se", [
    ([float("nan"), 1], 0, 0.1), ([1, float("inf")], 0, 0.1),
    ([1, 2], float("nan"), 0.1), ([1, 2], 0, -0.1),
    ([[1, 2]], 0, 0.1), ([1, 2], 0, float("inf")),
])
def test_invalid_statistics_cannot_produce_a_verdict(returns, mean, se):
    with pytest.raises(ValueError):
        collapse_check(returns, in_sample_mean=mean, in_sample_se=se)


def test_result_below_the_threshold_requires_discard_without_rounding_to_a_pass():
    result = collapse_check([-4.01, 3.99], in_sample_mean=10, in_sample_se=3)
    assert result["verdict"] == "FAIL_DISCARD"
