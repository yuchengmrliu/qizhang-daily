"""由快取資料算出每檔股票的最新指標。

輸出一律是「一檔股票一列」的 DataFrame,索引為股票代號,供 screener 直接套規則。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def _latest_per_code(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values("date").groupby("code").tail(1).set_index("code")


def percentile_of(series: pd.Series, value: float | None) -> float | None:
    """value 在 series 裡的百分位。越小代表越便宜。"""
    if value is None or not np.isfinite(value):
        return None
    valid = series.dropna()
    valid = valid[np.isfinite(valid)]
    if len(valid) < 2:
        return None
    return float((valid < value).mean() * 100.0)


def compute_technical(quotes: pd.DataFrame) -> pd.DataFrame:
    """均線、量能、前高。輸入需為六個月日線。"""
    if quotes.empty:
        return pd.DataFrame()

    data = quotes.sort_values(["code", "date"]).copy()
    grouped = data.groupby("code", sort=False)

    data["ma_short"] = grouped["close"].transform(
        lambda s: s.rolling(config.MA_SHORT, min_periods=config.MA_SHORT).mean()
    )
    data["ma_long"] = grouped["close"].transform(
        lambda s: s.rolling(config.MA_LONG, min_periods=config.MA_LONG).mean()
    )
    data["ma_short_prev"] = grouped["ma_short"].transform(
        lambda s: s.shift(config.MA_SLOPE_LOOKBACK)
    )
    # 量能比較的是「今天 vs 之前幾天」,因此均量不含今天
    data["avg_volume_surge"] = grouped["volume_lots"].transform(
        lambda s: s.shift(1).rolling(config.VOLUME_SURGE_WINDOW, min_periods=1).mean()
    )
    data["avg_volume_liquidity"] = grouped["volume_lots"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )
    # 前高同樣不含今天,否則今天必然等於自己
    data["high_window"] = grouped["high"].transform(
        lambda s: s.shift(1).rolling(config.BREAKOUT_WINDOW, min_periods=20).max()
    )
    data["trading_days"] = grouped["close"].transform("count")

    latest = _latest_per_code(data)
    latest["volume_ratio"] = latest["volume_lots"] / latest["avg_volume_surge"].replace(0, np.nan)
    latest["breakout_ratio"] = latest["close"] / latest["high_window"].replace(0, np.nan)
    latest["ma_short_rising"] = latest["ma_short"] > latest["ma_short_prev"]
    return latest


def compute_fundamental(valuations: pd.DataFrame) -> pd.DataFrame:
    """本益比與股價淨值比的歷年位階,以及獲利趨勢。輸入需為三年序列。"""
    if valuations.empty:
        return pd.DataFrame()

    data = valuations.sort_values(["code", "date"]).copy()
    data["timestamp"] = pd.to_datetime(data["date"])
    # 近四季 EPS 由估值反推,不需要額外的財報資料源
    data["eps"] = data["close"] / data["pe"].replace(0, np.nan)

    latest = _latest_per_code(data)

    pe_rank: dict[str, float | None] = {}
    pb_rank: dict[str, float | None] = {}
    eps_prev: dict[str, float | None] = {}
    history_days: dict[str, int] = {}

    one_year_ago = data["timestamp"].max() - pd.Timedelta(days=365)

    for code, group in data.groupby("code", sort=False):
        current = latest.loc[code]
        pe_rank[code] = percentile_of(group["pe"], current["pe"])
        pb_rank[code] = percentile_of(group["pb"], current["pb"])
        history_days[code] = int(len(group))

        older = group[group["timestamp"] <= one_year_ago]
        eps_series = older["eps"].dropna()
        eps_prev[code] = float(eps_series.iloc[-1]) if len(eps_series) else None

    latest["pe_percentile"] = pd.Series(pe_rank)
    latest["pb_percentile"] = pd.Series(pb_rank)
    latest["eps_prev"] = pd.Series(eps_prev)
    latest["valuation_days"] = pd.Series(history_days)
    latest["eps_growth"] = latest["eps"] / latest["eps_prev"].replace(0, np.nan)
    return latest
