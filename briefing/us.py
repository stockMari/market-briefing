"""나스닥 52주 신고가 · 급등주 (yfinance).

- 대상: 나스닥 상장 보통주 (config.yaml 의 us.markets, 기본 Global Select)
- 잡주 제외: 주가 us.min_price 달러 이상, 최근 20일 평균 거래대금 us.min_dollar_volume_m 백만 달러 이상
- 기간은 한국 리포트와 같은 규칙: Daily = 직전 미국 거래일, Weekly = 지난주 금요일 → 이번 주 금요일
"""
import json
import re
import time
from datetime import date, timedelta

import pandas as pd
import requests
import yfinance as yf

from .config import ROOT

NASDAQ_LIST = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
INFO_CACHE = ROOT / "cache" / "us_info.json"
SKIP_WORDS = ("Warrant", "Right", "Unit", "Preferred", "Notes", "Debenture", "Subordinated", "Trust Preferred")
SECTOR_KO = {
    "Technology": "기술", "Healthcare": "헬스케어", "Financial Services": "금융",
    "Consumer Cyclical": "경기소비재", "Communication Services": "커뮤니케이션", "Industrials": "산업재",
    "Consumer Defensive": "필수소비재", "Energy": "에너지", "Basic Materials": "소재",
    "Real Estate": "부동산", "Utilities": "유틸리티",
}


def universe(markets: list[str]) -> dict[str, str]:
    """나스닥 상장 보통주 목록 {티커: 회사명}."""
    text = requests.get(NASDAQ_LIST, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).text
    lines = [l.split("|") for l in text.strip().splitlines()]
    head = {h: i for i, h in enumerate(lines[0])}
    out = {}
    for r in lines[1:]:
        if len(r) != len(head):  # 마지막 'File Creation Time' 줄
            continue
        sym, name = r[head["Symbol"]], r[head["Security Name"]]
        if (r[head["Test Issue"]] == "Y" or r[head["ETF"]] == "Y"
                or r[head["Market Category"]] not in markets
                or r[head["Financial Status"]] not in ("N", "")
                or any(w in name for w in SKIP_WORDS)
                or not re.fullmatch(r"[A-Z]{1,5}", sym)):
            continue
        out[sym] = name.split(" - ")[0].strip()
    return out


def history(tickers: list[str], start: date, end: date, log, chunk: int = 200) -> dict[str, pd.DataFrame]:
    """여러 종목 일봉 (수정주가). 반환: {'Close': 표, 'High': 표, 'Volume': 표} (날짜 × 티커)"""
    parts = {"Close": [], "High": [], "Volume": []}
    for i in range(0, len(tickers), chunk):
        group = tickers[i:i + chunk]
        df = None
        for attempt in range(3):
            try:
                df = yf.download(group, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                                 interval="1d", auto_adjust=True, group_by="column",
                                 threads=True, progress=False)
                if not df.empty:
                    break
            except Exception as e:  # noqa: BLE001
                log(f"    ! 다운로드 재시도 ({i // chunk + 1}): {e}")
            time.sleep(5 * (attempt + 1))
        if df is None or df.empty:
            log(f"    ! {len(group)}종목 묶음을 받지 못해 건너뜀")
            continue
        for k in parts:
            parts[k].append(df[k])
        log(f"    {min(i + chunk, len(tickers))}/{len(tickers)}")
        time.sleep(1)
    out = {}
    for k, frames in parts.items():
        t = pd.concat(frames, axis=1)
        t = t.loc[:, ~t.columns.duplicated()]
        t.index = pd.to_datetime(t.index).date
        out[k] = t.sort_index()
    return out


def company_info(tickers: list[str], log) -> dict[str, dict]:
    """섹터·업종·상장주식수. 한 번 받은 건 cache/us_info.json 에 30일간 보관."""
    cache = json.loads(INFO_CACHE.read_text()) if INFO_CACHE.exists() else {}
    today = date.today().isoformat()
    stale = [t for t in tickers if t not in cache
             or (date.today() - date.fromisoformat(cache[t].get("ts", "2000-01-01"))).days > 30]
    for t in stale:
        try:
            i = yf.Ticker(t).info or {}
            cache[t] = {"sector": i.get("sector", ""), "industry": i.get("industry", ""),
                        "name": i.get("shortName") or "", "shares": i.get("sharesOutstanding"), "ts": today}
        except Exception as e:  # noqa: BLE001
            log(f"    · {t} 회사 정보 실패: {e}")
        time.sleep(0.3)
    INFO_CACHE.parent.mkdir(parents=True, exist_ok=True)
    INFO_CACHE.write_text(json.dumps(cache, ensure_ascii=False))
    return cache


def _r(x, n=2):
    return None if x is None or pd.isna(x) else round(float(x), n)


def collect_us(per, run_date: date, cfg: dict, log=print) -> dict | None:
    u = cfg.get("us", {})
    if not u.get("enabled", True):
        return None
    names = universe(u.get("markets", ["Q"]))
    log(f"  · 나스닥 대상 {len(names)}종목 1년치 시세 받는 중")
    data = history(sorted(names), per.target_base - timedelta(days=400), run_date, log)
    close, high, vol = data["Close"], data["High"], data["Volume"]

    # 기간: Daily = 실행 전날까지 마감된 마지막 거래일, Weekly = 이번 주 금요일까지
    days = [d for d in close.index if d < run_date] if per.mode == "daily" \
        else [d for d in close.index if d <= per.target_end]
    end = days[-1]
    base = days[-2] if per.mode == "daily" else max(d for d in days if d <= per.target_base)
    during = [d for d in days if base < d <= end]
    prior = [d for d in days if d < during[0]][-252:]

    # 잡주 거르기
    last20 = [d for d in days if d <= end][-20:]
    dollar_vol = (close.loc[last20] * vol.loc[last20]).mean()
    px = close.loc[end]
    history_len = close.loc[prior].notna().sum()
    liquid = [t for t in close.columns
              if px.get(t, 0) >= u.get("min_price", 5)
              and dollar_vol.get(t, 0) >= u.get("min_dollar_volume_m", 10) * 1e6
              and history_len.get(t, 0) >= 200]
    chg = (close.loc[end, liquid] / close.loc[base, liquid] - 1) * 100

    src = high if cfg["judgment"].get("high_basis") == "high" else close
    prior_max = src.loc[prior, liquid].max()
    now_max = src.loc[during, liquid].max()
    is_high = now_max > prior_max
    highs_all = [t for t in liquid if is_high.get(t, False)]
    # 너무 많으면 거래대금이 큰 순으로 자르기
    highs = sorted(highs_all, key=lambda t: -dollar_vol[t])[:u.get("max_highs", 60)]
    gainers = chg.sort_values(ascending=False).head(u.get("top_gainers", 15)).index.tolist()

    info = company_info(sorted(set(highs) | set(gainers)), log)
    spark_days = [d for d in days if d <= end][-u.get("spark_days", 60):]

    def row(t):
        i = info.get(t, {})
        shares = i.get("shares")
        return {
            "ticker": t, "name": i.get("name") or names.get(t, t),
            "sector": SECTOR_KO.get(i.get("sector", ""), i.get("sector") or "기타"),
            "industry": i.get("industry", ""),
            "change_pct": _r(chg[t]), "close": _r(close.at[end, t]),
            "mcap_b": _r(shares * close.at[end, t] / 1e9, 1) if shares else None,
            "is_high": bool(is_high.get(t, False)),
            "spark": [_r(v) for v in close.loc[spark_days, t].tolist()],
        }

    high_rows = sorted((row(t) for t in highs), key=lambda r: -r["change_pct"])
    sectors = {}
    for r in high_rows:
        sectors[r["sector"]] = sectors.get(r["sector"], 0) + 1
    log(f"  · 거래 활발 {len(liquid)}종목 → 신고가 {len(highs_all)}, 급등 상위 {len(gainers)}")
    return {
        "as_of": end.isoformat(), "base": base.isoformat(), "universe": len(liquid),
        "filters": {"min_price": u.get("min_price", 5), "min_dollar_volume_m": u.get("min_dollar_volume_m", 10),
                    "small_cap_b": u.get("small_cap_b", 20)},
        "gainers": [row(t) for t in gainers],
        "highs": high_rows, "highs_total": len(highs_all),
        "high_sectors": sorted(sectors.items(), key=lambda kv: -kv[1]),
    }
