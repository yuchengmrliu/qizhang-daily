"""每日流程:補當日資料 -> 算指標 -> 篩選 -> 產出網站。

抓不到當日資料時(假日、來源異常)不會讓網站空白,而是沿用快取中最後一個
交易日的資料並標記為過期,由前端顯示「資料日期」讓使用者自行判斷。
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from . import builder, fetcher, indicators, screener, store

LOOKBACK_DAYS = 5


def _refresh_recent() -> bool:
    """補最近幾天的資料。回傳是否有抓到任何新資料。"""
    today = date.today()
    quotes = store.load_quotes()
    valuations = store.load_valuations()
    known_quotes = store.cached_dates(quotes)
    known_valuations = store.cached_dates(valuations)

    fetched_any = False
    for offset in range(LOOKBACK_DAYS):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:
            continue

        if day not in known_valuations:
            try:
                rows = fetcher.fetch_estimates(day)
            except fetcher.FetchError as exc:
                print(f"  估值 {day} 取得失敗: {exc}", flush=True)
                rows = []
            if rows:
                store.add_valuations(rows)
                fetched_any = True
                print(f"  估值 {day} 新增 {len(rows):,} 列", flush=True)

        if day not in known_quotes:
            try:
                rows = fetcher.fetch_quotes(day)
            except fetcher.FetchError as exc:
                print(f"  行情 {day} 取得失敗: {exc}", flush=True)
                rows = []
            if rows:
                store.add_quotes(rows)
                fetched_any = True
                print(f"  行情 {day} 新增 {len(rows):,} 列", flush=True)

    return fetched_any


def main() -> int:
    print("更新最近交易日資料", flush=True)
    _refresh_recent()

    quotes = store.load_quotes()
    valuations = store.load_valuations()
    if quotes.empty or valuations.empty:
        print("快取為空,請先執行 python -m pipeline.backfill", file=sys.stderr)
        return 1

    data_date = max(quotes["date"])
    stale = (date.today() - data_date) > timedelta(days=4)

    print(f"計算指標(資料日期 {data_date})", flush=True)
    technical = indicators.compute_technical(quotes)
    fundamental = indicators.compute_fundamental(valuations)

    print("套用篩選規則", flush=True)
    results = screener.screen(technical, fundamental)

    print("產出網站", flush=True)
    index = builder.build(results, quotes, valuations, data_date, stale=stale)

    counts = index["counts"]
    print(
        f"完成:掃描 {counts['universe']:,} 檔,入選 {counts['selected']} 檔"
        + (" (資料過期)" if stale else ""),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
