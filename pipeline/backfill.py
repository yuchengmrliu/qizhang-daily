"""一次性歷史回補。可中斷後重跑,已快取的日期會自動跳過。

用法:
    python -m pipeline.backfill              # 估值三年 + 行情六個月
    python -m pipeline.backfill valuation    # 只補估值
    python -m pipeline.backfill quote        # 只補行情
"""

from __future__ import annotations

import sys
import time
from datetime import date, timedelta

from . import config, fetcher, store

SAVE_EVERY = 10


def _candidate_days(days_back: int) -> list[date]:
    today = date.today()
    days = []
    for offset in range(days_back + 1):
        day = today - timedelta(days=offset)
        if day.weekday() < 5:  # 週末必無交易
            days.append(day)
    return days


def _run(kind: str, days_back: int) -> None:
    if kind == "valuation":
        frame = store.load_valuations()
        fetch = fetcher.fetch_estimates
        save = store.save_valuations
        add = store.add_valuations
    else:
        frame = store.load_quotes()
        fetch = fetcher.fetch_quotes
        save = store.save_quotes
        add = store.add_quotes

    done = store.cached_dates(frame)
    targets = [d for d in _candidate_days(days_back) if d not in done]
    print(f"[{kind}] 待補 {len(targets)} 天(已快取 {len(done)} 天)", flush=True)

    pending: list[dict] = []
    holidays = 0
    for index, day in enumerate(targets, start=1):
        try:
            rows = fetch(day)
        except fetcher.FetchError as exc:
            print(f"  {day} 取得失敗,跳過: {exc}", flush=True)
            continue

        if not rows:
            holidays += 1
        else:
            pending.extend(rows)

        if index % SAVE_EVERY == 0 or index == len(targets):
            if pending:
                frame = add(pending)
                pending = []
            print(
                f"  進度 {index}/{len(targets)}  最近 {day}  "
                f"累積 {len(frame):,} 列  非交易日 {holidays}",
                flush=True,
            )
        time.sleep(config.REQUEST_DELAY_SEC)

    if pending:
        frame = add(pending)
    save(frame)
    print(f"[{kind}] 完成,共 {len(frame):,} 列", flush=True)


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in {"all", "valuation"}:
        _run("valuation", config.VALUATION_HISTORY_DAYS)
    if what in {"all", "quote"}:
        _run("quote", config.QUOTE_HISTORY_DAYS)


if __name__ == "__main__":
    main()
