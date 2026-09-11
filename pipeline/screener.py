"""把指標套上篩選規則,產出每檔股票的逐項結果與入選判定。

每條規則都回報「過或沒過」以及一句人看得懂的理由,前端直接顯示這些理由,
使用者不必自己回推為什麼某檔被選上。
"""

from __future__ import annotations

import math

import pandas as pd

from . import config


def _ok(value) -> bool:
    return value is not None and not (isinstance(value, float) and math.isnan(value))


def _fmt(value, digits: int = 2, suffix: str = "") -> str:
    if not _ok(value):
        return "無資料"
    return f"{value:.{digits}f}{suffix}"


def _check(key: str, label: str, passed: bool | None, detail: str) -> dict:
    return {"key": key, "label": label, "passed": bool(passed), "detail": detail}


def _fundamental_checks(row) -> list[dict]:
    pe = row.get("pe")
    pe_pct = row.get("pe_percentile")
    pb_pct = row.get("pb_percentile")
    dy = row.get("yield_pct")
    growth = row.get("eps_growth")

    return [
        _check(
            "pe_percentile",
            f"本益比低於近三年第 {config.PE_PERCENTILE_MAX:.0f} 百分位",
            _ok(pe_pct) and pe_pct <= config.PE_PERCENTILE_MAX,
            f"本益比 {_fmt(pe)},位於近三年第 {_fmt(pe_pct, 0)} 百分位"
            if _ok(pe_pct)
            else "歷史本益比資料不足",
        ),
        _check(
            "pe_absolute",
            f"本益比不高於 {config.PE_ABSOLUTE_MAX:.0f} 倍",
            _ok(pe) and 0 < pe <= config.PE_ABSOLUTE_MAX,
            f"本益比 {_fmt(pe)} 倍",
        ),
        _check(
            "pb_percentile",
            "股價淨值比低於近三年中位數",
            _ok(pb_pct) and pb_pct <= config.PB_PERCENTILE_MAX,
            f"股價淨值比 {_fmt(row.get('pb'))},位於近三年第 {_fmt(pb_pct, 0)} 百分位"
            if _ok(pb_pct)
            else "歷史股價淨值比資料不足",
        ),
        _check(
            "dividend_yield",
            f"殖利率不低於 {config.MIN_DIVIDEND_YIELD:.0f}%",
            _ok(dy) and dy >= config.MIN_DIVIDEND_YIELD,
            f"殖利率 {_fmt(dy, 2, '%')}",
        ),
        _check(
            "earnings_trend",
            "近四季每股盈餘未較一年前衰退",
            _ok(growth) and growth >= 1.0,
            f"每股盈餘 {_fmt(row.get('eps'))},一年前 {_fmt(row.get('eps_prev'))}"
            + (f",變化 {(growth - 1) * 100:+.1f}%" if _ok(growth) else ""),
        ),
    ]


def _technical_checks(row) -> list[dict]:
    close = row.get("close")
    ma_short = row.get("ma_short")
    volume_ratio = row.get("volume_ratio")
    breakout_ratio = row.get("breakout_ratio")

    return [
        _check(
            "above_ma",
            f"股價站上 {config.MA_SHORT} 日均線",
            _ok(close) and _ok(ma_short) and close > ma_short,
            f"收盤 {_fmt(close)},{config.MA_SHORT} 日均線 {_fmt(ma_short)}",
        ),
        _check(
            "ma_rising",
            f"{config.MA_SHORT} 日均線走揚",
            bool(row.get("ma_short_rising")),
            f"均線 {_fmt(ma_short)},{config.MA_SLOPE_LOOKBACK} 日前 {_fmt(row.get('ma_short_prev'))}",
        ),
        _check(
            "volume_surge",
            f"成交量放大至近 {config.VOLUME_SURGE_WINDOW} 日均量 {config.VOLUME_SURGE_RATIO} 倍",
            _ok(volume_ratio) and volume_ratio >= config.VOLUME_SURGE_RATIO,
            f"今日 {_fmt(row.get('volume_lots'), 0)} 張,近 {config.VOLUME_SURGE_WINDOW} 日均量 "
            f"{_fmt(row.get('avg_volume_surge'), 0)} 張({_fmt(volume_ratio)} 倍)",
        ),
        _check(
            "breakout",
            f"逼近或突破近 {config.BREAKOUT_WINDOW} 日高點",
            _ok(breakout_ratio) and breakout_ratio >= config.BREAKOUT_TOLERANCE,
            f"收盤 {_fmt(close)},近 {config.BREAKOUT_WINDOW} 日高點 {_fmt(row.get('high_window'))}",
        ),
    ]


def _stars(total_passes: int) -> int:
    for threshold, stars in config.STAR_THRESHOLDS:
        if total_passes >= threshold:
            return stars
    return config.STAR_DEFAULT


def _liquidity_reason(row) -> str | None:
    avg_volume = row.get("avg_volume_liquidity")
    trading_days = row.get("trading_days")
    pe = row.get("pe")

    if not _ok(trading_days) or trading_days < config.MIN_TRADING_DAYS:
        return "上市櫃或交易天數不足"
    if not _ok(avg_volume) or avg_volume < config.MIN_AVG_VOLUME_LOTS:
        return f"近 20 日均量 {_fmt(avg_volume, 0)} 張,低於 {config.MIN_AVG_VOLUME_LOTS} 張"
    if not _ok(pe) or pe <= 0:
        return "無本益比資料(公司虧損或未公布)"
    return None


def screen(technical: pd.DataFrame, fundamental: pd.DataFrame) -> list[dict]:
    if technical.empty or fundamental.empty:
        return []

    merged = technical.join(
        fundamental[
            ["pe", "pb", "yield_pct", "eps", "eps_prev", "eps_growth",
             "pe_percentile", "pb_percentile", "valuation_days"]
        ],
        how="inner",
    )

    results = []
    for code, row in merged.iterrows():
        data = row.to_dict()
        excluded = _liquidity_reason(data)

        fundamental_checks = _fundamental_checks(data)
        technical_checks = _technical_checks(data)
        fundamental_passes = sum(c["passed"] for c in fundamental_checks)
        technical_passes = sum(c["passed"] for c in technical_checks)

        selected = (
            excluded is None
            and fundamental_passes >= config.MIN_FUNDAMENTAL_PASSES
            and technical_passes >= config.MIN_TECHNICAL_PASSES
        )

        results.append(
            {
                "code": code,
                "name": data.get("name"),
                "market": data.get("market"),
                "close": _round(data.get("close")),
                "pe": _round(data.get("pe")),
                "pb": _round(data.get("pb")),
                "yield_pct": _round(data.get("yield_pct")),
                "pe_percentile": _round(data.get("pe_percentile"), 0),
                "volume_lots": _round(data.get("volume_lots"), 0),
                "excluded_reason": excluded,
                "fundamental": fundamental_checks,
                "technical": technical_checks,
                "fundamental_passes": int(fundamental_passes),
                "technical_passes": int(technical_passes),
                "stars": _stars(fundamental_passes + technical_passes),
                "selected": bool(selected),
            }
        )

    results.sort(
        key=lambda r: (r["selected"], r["stars"], -(r["pe_percentile"] or 100)),
        reverse=True,
    )
    return results


def _round(value, digits: int = 2):
    if not _ok(value):
        return None
    return round(float(value), digits)
