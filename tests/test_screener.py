"""驗證每條篩選規則的邊界:剛好通過與剛好不通過。"""

import pandas as pd

from pipeline import config, screener


def _technical(**overrides):
    row = {
        "name": "測試股",
        "market": "TWSE",
        "close": 110.0,
        "ma_short": 100.0,
        "ma_short_prev": 95.0,
        "ma_short_rising": True,
        "volume_lots": 3000.0,
        "avg_volume_surge": 1000.0,
        "volume_ratio": 3.0,
        "high_window": 100.0,
        "breakout_ratio": 1.10,
        "avg_volume_liquidity": 2000.0,
        "trading_days": 120,
    }
    row.update(overrides)
    return pd.DataFrame([row], index=pd.Index(["1234"], name="code"))


def _fundamental(**overrides):
    row = {
        "pe": 12.0,
        "pb": 1.0,
        "yield_pct": 4.0,
        "eps": 9.0,
        "eps_prev": 8.0,
        "eps_growth": 1.125,
        "pe_percentile": 20.0,
        "pb_percentile": 30.0,
        "valuation_days": 600,
    }
    row.update(overrides)
    return pd.DataFrame([row], index=pd.Index(["1234"], name="code"))


def _run(technical=None, fundamental=None):
    if technical is None:
        technical = _technical()
    if fundamental is None:
        fundamental = _fundamental()
    results = screener.screen(technical, fundamental)
    assert len(results) == 1
    return results[0]


def _check(result, section, key):
    return next(c for c in result[section] if c["key"] == key)


def test_all_conditions_passing_is_selected():
    result = _run()
    assert result["fundamental_passes"] == config.FUNDAMENTAL_TOTAL
    assert result["technical_passes"] == config.TECHNICAL_TOTAL
    assert result["selected"] is True
    assert result["stars"] == 5
    assert result["excluded_reason"] is None


def test_pe_percentile_boundary():
    at_limit = _run(fundamental=_fundamental(pe_percentile=config.PE_PERCENTILE_MAX))
    assert _check(at_limit, "fundamental", "pe_percentile")["passed"] is True

    above = _run(fundamental=_fundamental(pe_percentile=config.PE_PERCENTILE_MAX + 0.1))
    assert _check(above, "fundamental", "pe_percentile")["passed"] is False


def test_dividend_yield_boundary():
    at_limit = _run(fundamental=_fundamental(yield_pct=config.MIN_DIVIDEND_YIELD))
    assert _check(at_limit, "fundamental", "dividend_yield")["passed"] is True

    below = _run(fundamental=_fundamental(yield_pct=config.MIN_DIVIDEND_YIELD - 0.01))
    assert _check(below, "fundamental", "dividend_yield")["passed"] is False


def test_flat_earnings_still_passes_but_shrinking_does_not():
    flat = _run(fundamental=_fundamental(eps_growth=1.0))
    assert _check(flat, "fundamental", "earnings_trend")["passed"] is True

    shrinking = _run(fundamental=_fundamental(eps_growth=0.99))
    assert _check(shrinking, "fundamental", "earnings_trend")["passed"] is False


def test_volume_surge_boundary():
    at_limit = _run(technical=_technical(volume_ratio=config.VOLUME_SURGE_RATIO))
    assert _check(at_limit, "technical", "volume_surge")["passed"] is True

    below = _run(technical=_technical(volume_ratio=config.VOLUME_SURGE_RATIO - 0.01))
    assert _check(below, "technical", "volume_surge")["passed"] is False


def test_breakout_tolerance_allows_just_below_prior_high():
    at_limit = _run(technical=_technical(breakout_ratio=config.BREAKOUT_TOLERANCE))
    assert _check(at_limit, "technical", "breakout")["passed"] is True

    below = _run(technical=_technical(breakout_ratio=config.BREAKOUT_TOLERANCE - 0.01))
    assert _check(below, "technical", "breakout")["passed"] is False


def test_price_must_be_above_moving_average():
    equal = _run(technical=_technical(close=100.0, ma_short=100.0))
    assert _check(equal, "technical", "above_ma")["passed"] is False


def test_missing_history_fails_gracefully():
    result = _run(fundamental=_fundamental(pe_percentile=None, pb_percentile=None))
    pe_check = _check(result, "fundamental", "pe_percentile")
    assert pe_check["passed"] is False
    assert pe_check["detail"] == "歷史本益比資料不足"


def test_thin_volume_is_excluded_even_when_conditions_pass():
    result = _run(
        technical=_technical(avg_volume_liquidity=config.MIN_AVG_VOLUME_LOTS - 1)
    )
    assert result["excluded_reason"] is not None
    assert result["selected"] is False


def test_loss_making_company_is_excluded():
    result = _run(fundamental=_fundamental(pe=None))
    assert result["excluded_reason"] == "無本益比資料(公司虧損或未公布)"
    assert result["selected"] is False


def test_selection_needs_both_sides():
    # 基本面全過但技術面只過兩項 -> 不入選
    weak_technical = _technical(volume_ratio=1.0, breakout_ratio=0.5)
    result = _run(technical=weak_technical)
    assert result["technical_passes"] == 2
    assert result["selected"] is False
