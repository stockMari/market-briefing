"""해외 지수 종가 (yfinance)."""
from datetime import date, timedelta

import pandas as pd
import yfinance as yf


def _close_series(df: pd.DataFrame) -> pd.Series:
    s = df["Close"]
    if isinstance(s, pd.DataFrame):  # 최신 yfinance 는 열이 2단으로 나옴
        s = s.iloc[:, 0]
    return s.dropna()


def closes(ticker: str, start: date, end: date) -> pd.Series:
    """start~end 사이 일별 종가. 날짜는 그 시장의 현지 날짜입니다."""
    for attempt in range(3):
        df = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                         progress=False, auto_adjust=False, threads=False)
        if not df.empty:
            break
    if df.empty:
        raise RuntimeError(f"yfinance 에서 {ticker} 데이터를 받지 못했습니다")
    s = _close_series(df)
    s.index = pd.to_datetime(s.index).date

    # 아시아 지수는 전날 일봉이 야후에 늦게 올라오는 경우가 있어,
    # 일봉에 없는 날은 1시간봉의 그날 마지막 값으로 채웁니다.
    try:
        hourly = _close_series(yf.download(ticker, period="7d", interval="60m",
                                           progress=False, auto_adjust=False, threads=False))
        days = pd.Series(hourly.values, index=[t.date() for t in hourly.index])
        last_of_day = days.groupby(level=0).last()
        missing = last_of_day[[d not in s.index and start <= d <= end for d in last_of_day.index]]
        if not missing.empty:
            s = pd.concat([s, missing]).sort_index()
    except Exception:  # noqa: BLE001  1시간봉은 보조용이라 실패해도 일봉으로 진행
        pass
    return s


TZ_LABEL = {"Asia/Seoul": "한국 시간", "America/New_York": "뉴욕 시간", "Asia/Tokyo": "도쿄 시간",
            "Asia/Shanghai": "상하이 시간", "Asia/Taipei": "타이베이 시간"}


def intraday(ticker: str, days: list[date], interval: str) -> dict | None:
    """그 기간의 장중 봉 (현지 시간). 반환: {interval, tz, bars: [['10/23 09:00', 시, 고, 저, 종], ...]}"""
    # 시간대 차이로 첫날·마지막날이 잘리지 않게 앞뒤로 넉넉히 받고, 현지 날짜로 걸러냄
    df = yf.download(ticker, start=(min(days) - timedelta(days=1)).isoformat(),
                     end=(max(days) + timedelta(days=2)).isoformat(),
                     interval=interval, auto_adjust=False, prepost=False, progress=False, threads=False)
    if df.empty:
        return None
    cols = {k: _col(df, k) for k in ("Open", "High", "Low", "Close")}
    idx = pd.to_datetime(df.index)
    tz = str(idx.tz) if idx.tz is not None else ""
    keep = set(days)
    bars = []
    for i, t in enumerate(idx):
        if t.date() not in keep:
            continue
        o, h, l, c = (cols[k].iloc[i] for k in ("Open", "High", "Low", "Close"))
        if pd.isna(c):
            continue
        bars.append([f"{t.month}/{t.day} {t:%H:%M}",
                     round(float(o), 2), round(float(h), 2), round(float(l), 2), round(float(c), 2)])
    return {"interval": interval, "tz": TZ_LABEL.get(tz, tz), "bars": bars} if bars else None


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    s = df[name]
    return s.iloc[:, 0] if isinstance(s, pd.DataFrame) else s
