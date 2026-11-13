import pytest

from goldnix_venue.qualification import qualify_snapshot


def snapshot(**changes):
    return {
        "status": "OK", "currency": "USC", "profit_currency": "USD",
        "base_currency": "XAU", "symbol": "XAUUSDc", "server": "TEST-DEMO",
        "equity": 2000., "margin_free": 2000., "account_trade_mode": 0,
        "margin_mode": 2, "connected": 1, "symbol_trade_mode": 4,
        "volume_min": .01, "volume_step": .01, "contract_size": 1.,
        "bid": 4000., "ask": 4000.4, "point": .01, "stops_level": 0,
        "loss_buy_one_unit": 1., "loss_sell_one_unit": 2., "price_move": 1.,
        "margin_buy": 35., "margin_sell": 40., "quote_age_seconds": 0,
        "captured_utc_epoch": 2000000000, "is_custom_symbol": 0,
        **changes,
    }


def test_cent_contract_uses_worse_direction_and_keeps_approval_separate():
    result = qualify_snapshot(snapshot(), reference_p99_per_oz=100., now_epoch=2000000001)
    assert result["equity_usd"] == 20.
    assert result["exposure_usd_per_price_unit"] == .02
    assert result["minimum_margin_usd"] == .4
    assert result["conditional_p99_usd"] == 2.
    assert result["contract_screen_pass"] is True
    assert result["step6_approved"] is False


@pytest.mark.parametrize("changes", [
    {"status": "CALCULATION_FAILED"}, {"profit_currency": "USC"},
    {"base_currency": "USD"}, {"currency": "EUR"}, {"account_trade_mode": 2},
    {"connected": 0}, {"is_custom_symbol": 1}, {"symbol_trade_mode": 3},
    {"margin_mode": 0}, {"loss_sell_one_unit": 0}, {"loss_buy_one_unit": float("nan")},
    {"margin_sell": -1}, {"price_move": 0}, {"volume_min": 0},
    {"volume_step": 0}, {"contract_size": float("inf")}, {"equity": -1},
    {"margin_free": float("nan")}, {"ask": 3999},
])
def test_unverified_or_invalid_evidence_is_explicitly_rejected(changes):
    with pytest.raises(ValueError):
        qualify_snapshot(snapshot(**changes), reference_p99_per_oz=100., now_epoch=2000000001)


@pytest.mark.parametrize("changes", [
    {"captured_utc_epoch": 1999999000}, {"captured_utc_epoch": 2000001000},
    {"quote_age_seconds": 301}, {"quote_age_seconds": -1},
])
def test_stale_or_future_evidence_cannot_qualify(changes):
    with pytest.raises(ValueError):
        qualify_snapshot(snapshot(**changes), reference_p99_per_oz=100., now_epoch=2000000001)


def test_broker_stop_minimum_must_allow_the_frozen_half_dollar_floor():
    result = qualify_snapshot(snapshot(stops_level=100), reference_p99_per_oz=100., now_epoch=2000000001)
    assert result["broker_min_stop_price"] == 1.
    assert result["contract_screen_pass"] is False


def test_a_large_demo_balance_does_not_inflate_the_study_budget():
    result = qualify_snapshot(snapshot(currency="USD", equity=10000., margin_free=10000.,
                                       loss_buy_one_unit=1., loss_sell_one_unit=1.,
                                       margin_buy=39.8, margin_sell=39.79),
                              reference_p99_per_oz=100., now_epoch=2000000001)
    assert result["study_budget_usd"] == 20.
    assert result["drawdown_limit_usd"] == 2.4
    assert result["margin_fits"] is False
    assert result["conditional_g7_fits"] is False


def test_export_import_retains_unknown_currency_and_bad_calculation_rows(tmp_path):
    import csv
    from goldnix_venue.qualification import qualify_file

    path = tmp_path / "actual_export.csv"
    row = snapshot()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=row)
        writer.writeheader()
        writer.writerows([row, snapshot(symbol="XAUCENT", profit_currency="USC"),
                          snapshot(symbol="XAUFAIL", status="CALCULATION_FAILED")])
    result = qualify_file(path, reference_p99_per_oz=100., now_epoch=2000000001)
    assert len(result["symbols"]) == 1
    assert [x["symbol"] for x in result["rejected"]] == ["XAUCENT", "XAUFAIL"]
    assert result["step6_approved"] is False
