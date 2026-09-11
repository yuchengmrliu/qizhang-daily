"""把篩選結果與圖表資料寫成前端讀取的靜態檔案。

產出:
    site/                      前端頁面(由 web/ 複製而來)
    site/data/index.json       今日結果 + 全市場清單(供搜尋)
    site/data/stocks/XXXX.json 個股的逐項理由、K 線與估值序列
"""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime

import pandas as pd

from . import config

WEB_DIR = config.ROOT / "web"


def _isoformat(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    return value.isoformat()


def _clean(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return round(float(value), 2)


def _candles(quotes: pd.DataFrame) -> list[list]:
    rows = quotes.sort_values("date")
    return [
        [
            _isoformat(row.date),
            _clean(row.open),
            _clean(row.high),
            _clean(row.low),
            _clean(row.close),
            _clean(row.volume_lots),
        ]
        for row in rows.itertuples()
    ]


def _valuation_series(valuations: pd.DataFrame) -> list[list]:
    rows = valuations.sort_values("date")
    return [
        [_isoformat(row.date), _clean(row.pe), _clean(row.pb), _clean(row.yield_pct)]
        for row in rows.itertuples()
    ]


def _write_json(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def build(
    results: list[dict],
    quotes: pd.DataFrame,
    valuations: pd.DataFrame,
    data_date: date,
    stale: bool = False,
) -> dict:
    site = config.SITE_DIR
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(WEB_DIR, site)

    quote_groups = dict(tuple(quotes.groupby("code")))
    valuation_groups = dict(tuple(valuations.groupby("code")))

    for result in results:
        code = result["code"]
        payload = {
            "code": code,
            "name": result["name"],
            "market": result["market"],
            "result": result,
            "candles": _candles(quote_groups[code]) if code in quote_groups else [],
            "valuation": (
                _valuation_series(valuation_groups[code]) if code in valuation_groups else []
            ),
        }
        _write_json(site / "data" / "stocks" / f"{code}.json", payload)

    selected = [r for r in results if r["selected"]]
    universe = [
        {
            "code": r["code"],
            "name": r["name"],
            "market": r["market"],
            "close": r["close"],
            "pe": r["pe"],
            "pe_percentile": r["pe_percentile"],
            "stars": r["stars"],
            "fundamental_passes": r["fundamental_passes"],
            "technical_passes": r["technical_passes"],
            "selected": r["selected"],
        }
        for r in results
    ]

    index = {
        "data_date": data_date.isoformat(),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "stale": stale,
        "counts": {
            "universe": len(results),
            "selected": len(selected),
            "fundamental_only": sum(
                1
                for r in results
                if r["excluded_reason"] is None
                and r["fundamental_passes"] >= config.MIN_FUNDAMENTAL_PASSES
            ),
            "technical_only": sum(
                1
                for r in results
                if r["excluded_reason"] is None
                and r["technical_passes"] >= config.MIN_TECHNICAL_PASSES
            ),
        },
        "thresholds": {
            "fundamental_total": config.FUNDAMENTAL_TOTAL,
            "technical_total": config.TECHNICAL_TOTAL,
            "min_fundamental": config.MIN_FUNDAMENTAL_PASSES,
            "min_technical": config.MIN_TECHNICAL_PASSES,
        },
        "selected": selected,
        "universe": universe,
    }
    _write_json(site / "data" / "index.json", index)
    return index
