"""해외 지수 종가 (yfinance)."""
from datetime import date, timedelta

import pandas as pd
import yfinance as yf


def closes(ticker: str, start: date, end: date) -> pd.Series:
    """start~end 사이 일별 종가. 날짜는 그 시장의 현지 날짜입니다."""
    for attempt in range(3):
        df = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                         progress=False, auto_adjust=False, threads=False)
        if not df.empty:
            break
    if df.empty:
        raise RuntimeError(f"yfinance 에서 {ticker} 데이터를 받지 못했습니다")
    s = df["Close"]
    if isinstance(s, pd.DataFrame):  # 최신 yfinance 는 열이 2단으로 나옴
        s = s.iloc[:, 0]
    s.index = pd.to_datetime(s.index).date
    return s.dropna()
