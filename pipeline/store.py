"""歷史資料的本機快取。

兩份 parquet:行情(六個月)與估值(三年)。兩者都以 (date, code) 為唯一鍵,
重複寫入同一天會覆蓋而非累加,因此重跑當天流程是安全的。
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import config

QUOTE_COLUMNS = ["date", "code", "name", "market", "open", "high", "low", "close", "volume_lots"]
VALUATION_COLUMNS = ["date", "code", "name", "market", "close", "pe", "pb", "yield_pct"]


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in columns})


def _load(path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return _empty(columns)
    frame = pd.read_parquet(path)
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame


def load_quotes() -> pd.DataFrame:
    return _load(config.QUOTE_CACHE, QUOTE_COLUMNS)


def load_valuations() -> pd.DataFrame:
    return _load(config.VALUATION_CACHE, VALUATION_COLUMNS)


def _merge(existing: pd.DataFrame, incoming: list[dict], columns: list[str]) -> pd.DataFrame:
    if not incoming:
        return existing
    fresh = pd.DataFrame(incoming)
    for column in columns:
        if column not in fresh:
            fresh[column] = None
    fresh = fresh[columns]

    combined = pd.concat([existing, fresh], ignore_index=True) if len(existing) else fresh
    combined = combined.drop_duplicates(subset=["date", "code"], keep="last")
    return combined.sort_values(["code", "date"], ignore_index=True)


def _trim(frame: pd.DataFrame, days: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    cutoff = max(frame["date"]) - timedelta(days=days)
    return frame[frame["date"] >= cutoff].reset_index(drop=True)


def save_quotes(frame: pd.DataFrame) -> None:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _trim(frame, config.QUOTE_HISTORY_DAYS).to_parquet(config.QUOTE_CACHE, index=False)


def save_valuations(frame: pd.DataFrame) -> None:
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _trim(frame, config.VALUATION_HISTORY_DAYS).to_parquet(config.VALUATION_CACHE, index=False)


def add_quotes(rows: list[dict]) -> pd.DataFrame:
    merged = _merge(load_quotes(), rows, QUOTE_COLUMNS)
    save_quotes(merged)
    return merged


def add_valuations(rows: list[dict]) -> pd.DataFrame:
    merged = _merge(load_valuations(), rows, VALUATION_COLUMNS)
    save_valuations(merged)
    return merged


def cached_dates(frame: pd.DataFrame) -> set[date]:
    return set() if frame.empty else set(frame["date"])
