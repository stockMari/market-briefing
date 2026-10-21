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
