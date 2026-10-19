"""한국거래소(KRX) 데이터 가져오기 — pykrx 를 감싼 얇은 층.

- 실패하면 몇 번 다시 시도합니다 (거래소 서버가 가끔 느림).
- 하루치 전 종목 시세는 cache/ 폴더에 저장해 두고 다시 받지 않습니다.
  (52주 신고가 계산에 1년치가 필요하기 때문)
"""
import re
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from pykrx import stock

from .config import ROOT

CACHE = ROOT / "cache" / "daily"
INDEX_CODE = {"KOSPI": "1001", "KOSDAQ": "2001"}


def ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def call(fn, *args, tries: int = 4, **kwargs):
    for i in range(tries):
        try:
            time.sleep(0.25)  # 거래소 서버에 부담을 주지 않도록 살짝 쉬기
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise RuntimeError(f"KRX 조회 실패: {fn.__name__}{args} → {e}") from e
            time.sleep(2 * (i + 1))


def norm(name: str) -> str:
    """업종 이름 비교용: 공백·가운뎃점 제거, '코스피/코스닥' 접두어 제거."""
    s = re.sub(r"[^\w]", "", str(name))
    return re.sub(r"^(코스피|코스닥)", "", s)


# ── 거래일 달력 ─────────────────────────────────────────
def index_daily(code: str, start: date, end: date) -> pd.DataFrame:
    """지수 일별 시세. code: 1001=KOSPI, 2001=KOSDAQ"""
    df = call(stock.get_index_ohlcv, ymd(start), ymd(end), code)
    df.index = pd.to_datetime(df.index).date
    return df[df["종가"] > 0]


def trading_days(start: date, end: date) -> list[date]:
    return list(index_daily(INDEX_CODE["KOSPI"], start, end).index)


# ── 전 종목 하루치 시세 (캐시) ──────────────────────────
def snapshot(d: date) -> pd.DataFrame:
    """그날 KOSPI+KOSDAQ 전 종목: 시장, 고가, 저가, 종가, 시가총액, 상장주식수."""
    path = CACHE / f"{ymd(d)}.csv.gz"
    if path.exists():
        return pd.read_csv(path, dtype={"티커": str}).set_index("티커")
    parts = []
    for m in ("KOSPI", "KOSDAQ"):
        df = call(stock.get_market_ohlcv, ymd(d), market=m)
        if df.empty or (df["종가"] == 0).all():
            raise RuntimeError(f"{d} {m} 시세가 비어 있습니다 (휴장일?)")
        df = df[["고가", "저가", "종가", "시가총액"]].copy()
        df["시장"] = m
        parts.append(df)
    df = pd.concat(parts)
    df.index.name = "티커"
    df["주식수"] = (df["시가총액"] / df["종가"].where(df["종가"] > 0)).round()
    CACHE.mkdir(parents=True, exist_ok=True)
    df.reset_index().to_csv(path, index=False)
    return df


def price_panel(days: list[date], log=print) -> dict[str, pd.DataFrame]:
    """여러 날의 시세를 (날짜 × 종목) 표로 모으고, 액면분할·병합을 보정합니다."""
    missing = [d for d in days if not (CACHE / f"{ymd(d)}.csv.gz").exists()]
    if missing:
        log(f"  · 전 종목 시세 {len(missing)}일치 새로 받는 중 (처음 한 번은 몇 분 걸립니다)")
    snaps = {}
    for i, d in enumerate(days):
        snaps[d] = snapshot(d)
        if missing and (i + 1) % 50 == 0:
            log(f"    {i + 1}/{len(days)}")
    close = pd.DataFrame({d: s["종가"] for d, s in snaps.items()}).T.sort_index()
    high = pd.DataFrame({d: s["고가"] for d, s in snaps.items()}).T.sort_index()
    low = pd.DataFrame({d: s["저가"] for d, s in snaps.items()}).T.sort_index()
    shares = pd.DataFrame({d: s["주식수"] for d, s in snaps.items()}).T.sort_index()
    last = snaps[days[-1]]

    # 분할/병합 보정: 주식 수가 k배로 늘고 주가가 1/k로 줄었으면 그 이전 가격을 1/k 로 맞춤
    ratio = shares / shares.shift(1)
    pratio = close / close.shift(1)
    split = (ratio.gt(1.4) | ratio.lt(0.7)) & ((pratio * ratio).sub(1).abs() < 0.35)
    factor = pd.DataFrame(1.0, index=close.index, columns=close.columns)
    for t in split.columns[split.any()]:
        for d in split.index[split[t]]:
            factor.loc[factor.index < d, t] /= ratio.loc[d, t]
    close = close.where(close > 0) * factor
    high = high.where(high > 0) * factor
    low = low.where(low > 0) * factor
    return {"close": close, "high": high, "low": low, "market": last["시장"], "mktcap": last["시가총액"]}


# ── 업종 ───────────────────────────────────────────────
def sector_members(d: date) -> pd.DataFrame:
    """종목별 소속 업종 (KRX 업종 분류)."""
    parts = []
    for m in ("KOSPI", "KOSDAQ"):
        df = call(stock.get_market_sector_classifications, ymd(d), m)
        df = df[["종목명", "업종명"]].copy()
        df["시장"] = m
        parts.append(df)
    out = pd.concat(parts)
    out.index = out.index.astype(str).str.zfill(6)
    return out


def index_closes(d: date, market: str) -> pd.Series:
    df = call(stock.get_index_ohlcv, ymd(d), market=market)
    return df["종가"]


# ── 수급 ───────────────────────────────────────────────
def flows_by_date(start: date, end: date, market: str) -> pd.DataFrame:
    """날짜별 투자자 순매수 금액(원): 외국인, 기관, 개인."""
    df = call(stock.get_market_trading_value_by_date, ymd(start), ymd(end), market)
    df.index = pd.to_datetime(df.index).date
    return df.rename(columns={"외국인합계": "외국인", "기관합계": "기관"})[["외국인", "기관", "개인"]]


def net_buy_ranking(start: date, end: date, market: str, investor: str) -> pd.DataFrame:
    """기간 중 투자자별 순매수 상위 종목 (순매수거래대금, 원)."""
    df = call(stock.get_market_net_purchases_of_equities, ymd(start), ymd(end), market, investor)
    df.index = df.index.astype(str).str.zfill(6)
    return df
