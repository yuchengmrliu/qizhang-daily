"""以手算得出的固定資料驗證指標計算。"""

from datetime import date, timedelta

import pandas as pd

from pipeline import config, indicators


def _quotes(closes, volumes, highs=None):
    start = date(2026, 1, 1)
    highs = highs if highs is not None else closes
    return pd.DataFrame(
        {
            "date": [start + timedelta(days=i) for i in range(len(closes))],
            "code": ["1234"] * len(closes),
            "name": ["測試股"] * len(closes),
            "market": ["TWSE"] * len(closes),
            "open": closes,
            "high": highs,
            "low": closes,
            "close": closes,
            "volume_lots": volumes,
        }
    )


def test_moving_average_and_breakout():
    # 前 60 天都是 100,最後一天跳到 110、量放大三倍
    closes = [100.0] * 60 + [110.0]
    volumes = [1000.0] * 60 + [3000.0]
    result = indicators.compute_technical(_quotes(closes, volumes))
    row = result.loc["1234"]

    # 最後 20 天均價 = (19 * 100 + 110) / 20
    assert row["ma_short"] == 100.5
    assert row["close"] > row["ma_short"]
    assert bool(row["ma_short_rising"]) is True
    assert row["volume_ratio"] == 3.0
    # 不含今天的近 60 日最高價為 100,故突破比 = 110 / 100
    assert round(row["breakout_ratio"], 4) == 1.1


def test_flat_market_is_not_a_breakout():
    closes = [100.0] * 61
    volumes = [1000.0] * 61
    row = indicators.compute_technical(_quotes(closes, volumes)).loc["1234"]

    assert row["close"] == row["ma_short"]
    assert bool(row["ma_short_rising"]) is False
    assert row["volume_ratio"] == 1.0
    assert row["breakout_ratio"] == 1.0


def test_volume_average_excludes_today():
    # 若均量含今天,爆量那天的比值會被自己稀釋而失真
    closes = [100.0] * 61
    volumes = [1000.0] * 60 + [6000.0]
    row = indicators.compute_technical(_quotes(closes, volumes)).loc["1234"]

    assert row["avg_volume_surge"] == 1000.0
    assert row["volume_ratio"] == 6.0


def _valuations(pes, closes=None):
    start = date(2023, 1, 1)
    closes = closes if closes is not None else [100.0] * len(pes)
    return pd.DataFrame(
        {
            "date": [start + timedelta(days=i) for i in range(len(pes))],
            "code": ["1234"] * len(pes),
            "name": ["測試股"] * len(pes),
            "market": ["TWSE"] * len(pes),
            "close": closes,
            "pe": pes,
            "pb": [1.0] * len(pes),
            "yield_pct": [3.0] * len(pes),
        }
    )


def test_percentile_of_cheapest_value_is_zero():
    # 目前本益比比過去每一天都低 -> 位階 0
    pes = [20.0] * 100 + [5.0]
    row = indicators.compute_fundamental(_valuations(pes)).loc["1234"]
    assert row["pe_percentile"] == 0.0


def test_percentile_of_most_expensive_value_is_high():
    pes = [10.0] * 100 + [50.0]
    row = indicators.compute_fundamental(_valuations(pes)).loc["1234"]
    # 101 個樣本中有 100 個低於目前值
    assert round(row["pe_percentile"], 2) == round(100 / 101 * 100, 2)


def test_eps_growth_uses_value_from_one_year_ago():
    # 兩年資料:第一年 EPS = 100/20 = 5,最後一天 EPS = 100/10 = 10
    days = 800
    pes = [20.0] * (days - 1) + [10.0]
    frame = indicators.compute_fundamental(_valuations(pes))
    row = frame.loc["1234"]

    assert row["eps"] == 10.0
    assert row["eps_prev"] == 5.0
    assert row["eps_growth"] == 2.0


def test_percentile_needs_enough_history():
    assert indicators.percentile_of(pd.Series([10.0]), 5.0) is None
    assert indicators.percentile_of(pd.Series([], dtype="float64"), 5.0) is None
