"""向證交所與櫃買中心取得單一交易日的原始資料。

四個來源、兩種內容:
  estimate  估值(本益比/股價淨值比/殖利率) —— 每日約 136 KB,用於三年序列
  quote     行情(開高低收量)                —— 每日約 6.2 MB,用於六個月序列

非交易日一律回傳空 list,由呼叫端決定跳過。
"""

from __future__ import annotations

import re
import time
from datetime import date

import requests

from . import config

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# 個股代號為四碼且首碼 1-9。00 開頭者為 ETF / ETN,不在選股範圍。
_STOCK_CODE = re.compile(r"[1-9]\d{3}")

_session = requests.Session()
_session.headers.update({"User-Agent": _UA, "Accept": "application/json, */*"})


class FetchError(RuntimeError):
    pass


def _get_json(url: str) -> dict | list:
    last: Exception | None = None
    for attempt in range(config.REQUEST_RETRIES):
        try:
            resp = _session.get(url, timeout=config.REQUEST_TIMEOUT_SEC)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # noqa: BLE001 - 重試涵蓋連線與解析兩類失敗
            last = exc
            time.sleep(config.REQUEST_DELAY_SEC * (2**attempt))
    raise FetchError(f"{url} 連續 {config.REQUEST_RETRIES} 次失敗: {last}")


def _num(raw) -> float | None:
    """把報表裡的數字欄轉成 float。'-'、'--'、空字串代表沒有資料。"""
    if raw is None:
        return None
    text = str(raw).replace(",", "").replace("%", "").strip()
    if text in {"", "-", "--", "---", "N/A"}:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value


def _is_stock(code: str) -> bool:
    return bool(_STOCK_CODE.fullmatch(code.strip()))


def _rows_by_field(table: dict) -> list[dict]:
    fields = [f.strip() for f in table.get("fields") or []]
    return [dict(zip(fields, row)) for row in table.get("data") or []]


def _pick_table(payload: dict, *required: str) -> dict | None:
    for table in payload.get("tables") or []:
        fields = [f.strip() for f in table.get("fields") or []]
        if all(any(req in f for f in fields) for req in required):
            return table
    return None


# --------------------------------------------------------------------------
# 估值
# --------------------------------------------------------------------------


def fetch_twse_estimates(day: date) -> list[dict]:
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d"
        f"?date={day:%Y%m%d}&selectType=ALL&response=json"
    )
    payload = _get_json(url)
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        return []

    table = payload if payload.get("fields") else _pick_table(payload, "證券代號", "本益比")
    if not table:
        return []

    out = []
    for row in _rows_by_field(table):
        code = str(row.get("證券代號", "")).strip()
        if not _is_stock(code):
            continue
        out.append(
            {
                "date": day,
                "code": code,
                "name": str(row.get("證券名稱", "")).strip(),
                "market": "TWSE",
                "close": _num(row.get("收盤價")),
                "pe": _num(row.get("本益比")),
                "pb": _num(row.get("股價淨值比")),
                "yield_pct": _num(row.get("殖利率(%)")),
            }
        )
    return out


def fetch_tpex_estimates(day: date) -> list[dict]:
    url = (
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate"
        f"?date={day:%Y/%m/%d}&response=json"
    )
    payload = _get_json(url)
    if not isinstance(payload, dict):
        return []

    table = _pick_table(payload, "股票代號", "本益比")
    if not table:
        return []

    out = []
    for row in _rows_by_field(table):
        code = str(row.get("股票代號", "")).strip()
        if not _is_stock(code):
            continue
        out.append(
            {
                "date": day,
                "code": code,
                "name": str(row.get("公司名稱", "")).strip(),
                "market": "TPEX",
                "close": None,  # 櫃買估值報表不含收盤價,由行情資料補上
                "pe": _num(row.get("本益比")),
                "pb": _num(row.get("股價淨值比")),
                "yield_pct": _num(row.get("殖利率(%)")),
            }
        )
    return out


def fetch_estimates(day: date) -> list[dict]:
    rows = fetch_twse_estimates(day)
    time.sleep(config.REQUEST_DELAY_SEC)
    rows += fetch_tpex_estimates(day)
    return rows


# --------------------------------------------------------------------------
# 行情
# --------------------------------------------------------------------------


def fetch_twse_quotes(day: date) -> list[dict]:
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
        f"?date={day:%Y%m%d}&type=ALL&response=json"
    )
    payload = _get_json(url)
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        return []

    table = _pick_table(payload, "證券代號", "收盤價")
    if not table:
        return []

    out = []
    for row in _rows_by_field(table):
        code = str(row.get("證券代號", "")).strip()
        if not _is_stock(code):
            continue
        close = _num(row.get("收盤價"))
        if close is None:
            continue
        shares = _num(row.get("成交股數")) or 0.0
        out.append(
            {
                "date": day,
                "code": code,
                "name": str(row.get("證券名稱", "")).strip(),
                "market": "TWSE",
                "open": _num(row.get("開盤價")),
                "high": _num(row.get("最高價")),
                "low": _num(row.get("最低價")),
                "close": close,
                "volume_lots": shares / 1000.0,
            }
        )
    return out


def fetch_tpex_quotes(day: date) -> list[dict]:
    url = (
        "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"
        f"?date={day:%Y/%m/%d}&type=EW&response=json"
    )
    payload = _get_json(url)
    if not isinstance(payload, dict):
        return []

    table = _pick_table(payload, "代號", "收盤")
    if not table:
        return []

    out = []
    for row in _rows_by_field(table):
        code = str(row.get("代號", "")).strip()
        if not _is_stock(code):
            continue
        close = _num(row.get("收盤"))
        if close is None:
            continue
        shares = _num(row.get("成交股數")) or 0.0
        out.append(
            {
                "date": day,
                "code": code,
                "name": str(row.get("名稱", "")).strip(),
                "market": "TPEX",
                "open": _num(row.get("開盤")),
                "high": _num(row.get("最高")),
                "low": _num(row.get("最低")),
                "close": close,
                "volume_lots": shares / 1000.0,
            }
        )
    return out


def fetch_quotes(day: date) -> list[dict]:
    rows = fetch_twse_quotes(day)
    time.sleep(config.REQUEST_DELAY_SEC)
    rows += fetch_tpex_quotes(day)
    return rows
