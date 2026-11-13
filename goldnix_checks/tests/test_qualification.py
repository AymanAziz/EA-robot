import pytest

from goldnix_checks.qualification import qualify_file, qualify_snapshot


def snapshot(**overrides):
    return {
        "status": "OK",
        "currency": "USD",
        "base_currency": "XAU",
        "equity": 20.0,
        "margin_free": 20.0,
        "symbol": "XAUUSD",
        "volume_min": 0.01,
        "volume_step": 0.01,
        "contract_size": 100.0,
        "loss_one_price_unit": 1.0,
        "margin_buy": 30.0,
        "margin_sell": 30.0,
        "bid": 3000.0,
        "ask": 3000.4,
        **overrides,
    }


def test_standard_minimum_lot_fails_margin_and_historical_risk_envelope():
    result = qualify_snapshot(snapshot(), reference_p99_per_oz=90.0)

    assert result["equity_usd"] == 20.0
    assert result["minimum_move_loss_usd"] == 1.0
    assert result["conditional_p99_usd"] == 90.0
    assert result["margin_fits"] is False
    assert result["conditional_g7_fits"] is False
    assert result["step6_approved"] is False


def test_cent_account_converts_both_equity_and_order_calculations_to_dollars():
    result = qualify_snapshot(
        snapshot(currency="USC", equity=2000, margin_free=2000,
                 loss_one_price_unit=1, margin_buy=30, margin_sell=30),
        reference_p99_per_oz=90.0,
    )

    assert result["equity_usd"] == 20.0
    assert result["minimum_move_loss_usd"] == 0.01
    assert result["minimum_margin_usd"] == 0.30
    assert result["conditional_p99_usd"] == pytest.approx(0.90)
    assert result["margin_fits"] is True
    assert result["conditional_g7_fits"] is True
    assert result["step6_approved"] is False


@pytest.mark.parametrize("overrides", [
    {"status": "CALCULATION_FAILED"}, {"currency": "EUR"},
    {"loss_one_price_unit": 0}, {"loss_one_price_unit": float("nan")},
    {"equity": -20}, {"volume_min": 0}, {"ask": 2999},
    {"base_currency": "USD", "symbol": "GOLD"},
])
def test_missing_or_invalid_broker_evidence_cannot_qualify(overrides):
    with pytest.raises(ValueError):
        qualify_snapshot(snapshot(**overrides), reference_p99_per_oz=90.0)


def test_exported_csv_reports_invalid_rows_without_approving_them(tmp_path):
    import csv

    path = tmp_path / "snapshot.csv"
    first = snapshot()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=first)
        writer.writeheader()
        writer.writerow(first)
        writer.writerow(snapshot(status="CALCULATION_FAILED", symbol="GOLDmicro"))

    report = qualify_file(path, reference_p99_per_oz=90.0)

    assert len(report["symbols"]) == 1
    assert report["rejected"][0]["symbol"] == "GOLDmicro"
    assert report["step6_approved"] is False
