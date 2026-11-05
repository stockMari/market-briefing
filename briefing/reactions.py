"""실적 발표 후 주가 반응 (미국).

- 대상: 그 주(월~금, 미국 동부시간)에 실적을 발표한 시가총액 기준 이상 종목 (실제 EPS 가 나온 것만)
- 반응일: 장전(BMO) 발표 → 발표 당일 종가 / 장후(AMC) 발표 → 다음 거래일 종가
          시간 미정 → 발표 전날 종가 ~ 다음 거래일 종가 (2거래일)
- 시장 대비: 나스닥 상장 → QQQ, 그 밖(뉴욕거래소 등) → SPY 같은 기간 수익률을 뺀 값
- 업종·선행 PER 은 야후 파이낸스 종목 정보 (cache/us_info.json 에 저장해 다시 묻지 않음)
"""
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from .config import ROOT
from .earnings import fetch_earnings, listed_exchange

INFO_CACHE = ROOT / "cache" / "us_info.json"
INFO_MAX_AGE_DAYS = 60
SECTOR_KO = {
    "Technology": "기술", "Communication Services": "커뮤니케이션", "Consumer Cyclical": "경기소비재",
    "Consumer Defensive": "필수소비재", "Healthcare": "헬스케어", "Financial Services": "금융",
    "Industrials": "산업재", "Energy": "에너지", "Utilities": "유틸리티", "Real Estate": "부동산",
    "Basic Materials": "소재",
}
BENCH = {"nasdaq": "QQQ", "other": "SPY"}
SPARK_DAYS = 45


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def target_weeks(run_date: date) -> list[date]:
    """어제(미국 날짜) 가 속한 주 + 지난주 (지난주 금요일 장후 발표 반응이 아직 덜 찼을 수 있어서)."""
    return sorted({monday(run_date - timedelta(days=1)), monday(run_date - timedelta(days=4))})


def _load_info() -> dict:
    try:
        return json.loads(INFO_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def fetch_info(tickers: list[str], log, budget_s: float = 360) -> dict:
    """업종·산업·선행 PER·회사 소개. 오래되지 않은 값은 캐시에서."""
    cache = _load_info()
    today = date.today()
    need = [t for t in tickers if t not in cache or
            (today - date.fromisoformat(cache[t].get("at", "2000-01-01"))).days > INFO_MAX_AGE_DAYS]
    t0, done = time.time(), 0
    for t in need:
        if time.time() - t0 > budget_s:
            log(f"  · 종목 정보 시간 초과: {len(need) - done}개는 다음 실행에")
            break
        try:
            i = yf.Ticker(t).info or {}
            cache[t] = {"sector": i.get("sector"), "industry": i.get("industry"),
                        "fpe": i.get("forwardPE"), "name": i.get("shortName"),
                        "about": (i.get("longBusinessSummary") or "")[:400], "at": today.isoformat()}
        except Exception as e:  # noqa: BLE001
            log(f"  ! 종목 정보 실패 {t}: {e}")
        done += 1
    if need:
        log(f"  · 종목 정보 새로 {done}개 (캐시 {len(cache)}개)")
        INFO_CACHE.parent.mkdir(parents=True, exist_ok=True)
        INFO_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


def fetch_closes(tickers: list[str], start: date, end: date, log) -> pd.DataFrame:
    frames = []
    for i in range(0, len(tickers), 200):
        chunk = tickers[i:i + 200]
        try:
            df = yf.download(chunk, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                             progress=False, auto_adjust=True, threads=True, group_by="column")
            close = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": chunk[0]})
            frames.append(close)
        except Exception as e:  # noqa: BLE001
            log(f"  ! 주가 내려받기 실패 ({i}~): {e}")
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1)
    out.index = pd.to_datetime(out.index).date
    return out


def _window(sessions: list[date], d: date, slot: str):
    """(기준 종가 날짜, 반응 종가 날짜). 아직 반응일 장이 안 끝났으면 반응일 None."""
    before = [s for s in sessions if s < d]
    on_after = [s for s in sessions if s >= d]
    after = [s for s in sessions if s > d]
    if not before:
        return None, None
    if slot == "bmo":
        return before[-1], (on_after[0] if on_after and on_after[0] == d else None)
    if d not in sessions:  # 발표일이 휴장일
        return before[-1], (after[0] if after else None)
    return (d if slot == "amc" else before[-1]), (after[0] if after else None)


def _ret(series: pd.Series, a: date, b: date):
    try:
        x, y = float(series.loc[a]), float(series.loc[b])
    except (KeyError, TypeError, ValueError):
        return None
    if pd.isna(x) or pd.isna(y) or x == 0:
        return None
    return round((y / x - 1) * 100, 2)


def build_reactions(mon: date, cfg: dict, log=print) -> dict:
    rc = cfg.get("earnings_reactions", {})
    min_cap = rc.get("min_mcap_b", 1)
    fri = mon + timedelta(days=4)
    iso = mon.isocalendar()
    rows = [r for r in fetch_earnings(mon, fri, log, market_cap=min_cap * 1e9)
            if r["eps_act"] is not None and (r["mcap_b"] or 0) >= min_cap]
    log(f"  · 실적 반응 대상 {len(rows)}건 ({mon}~{fri}, 시총 ${min_cap}B 이상)")

    tickers = sorted({r["ticker"] for r in rows})
    closes = fetch_closes(tickers + list(BENCH.values()), mon - timedelta(days=SPARK_DAYS * 1.6),
                          fri + timedelta(days=7), log)
    sessions = sorted(closes["SPY"].dropna().index) if "SPY" in closes else []
    info = fetch_info(tickers, log, budget_s=rc.get("info_budget_s", 360)) if tickers else {}

    items = []
    for r in rows:
        d = date.fromisoformat(r["date"])
        exch = listed_exchange(r["ticker"])
        bench = BENCH["nasdaq" if exch == "nasdaq" else "other"]
        a, b = _window(sessions, d, r["slot"])
        s = closes[r["ticker"]] if r["ticker"] in closes else None
        react = _ret(s, a, b) if s is not None and a and b else None
        bret = _ret(closes[bench], a, b) if bench in closes and a and b else None
        inf = info.get(r["ticker"], {})
        spark = []
        if s is not None:
            ss = s.dropna()
            ss = ss[[x <= (b or ss.index[-1]) for x in ss.index]] if len(ss) else ss
            spark = [[x.isoformat(), round(float(v), 2)] for x, v in ss.tail(SPARK_DAYS).items()]
        items.append({
            **{k: r[k] for k in ("ticker", "company", "date", "slot", "mcap_b", "eps_est", "eps_act", "surprise")},
            "company": inf.get("name") or r["company"],
            "sector": SECTOR_KO.get(inf.get("sector"), inf.get("sector") or "기타"),
            "industry": inf.get("industry"), "fpe": round(inf["fpe"], 1) if inf.get("fpe") else None,
            "about": inf.get("about") or "",
            "exchange": "NASDAQ" if exch == "nasdaq" else ("NYSE 등" if exch else "-"),
            "bench": bench, "base_date": a.isoformat() if a else None, "react_date": b.isoformat() if b else None,
            "react": react, "bench_ret": bret,
            "excess": round(react - bret, 2) if react is not None and bret is not None else None,
            "spark": spark,
        })
    items.sort(key=lambda x: -(x["mcap_b"] or 0))
    done = [x for x in items if x["react"] is not None]
    wk = [x for x in sessions if mon <= x <= fri]
    prev = [x for x in sessions if x < mon]
    spy = _ret(closes["SPY"], prev[-1], wk[-1]) if wk and prev else None
    return {"label": f"{iso.year}-W{iso.week:02d}", "start": mon.isoformat(), "end": fri.isoformat(),
            "market": "US", "total": len(items), "done": len(done), "pending": len(items) - len(done),
            "spy_week": spy, "min_mcap_b": min_cap, "items": items,
            "generated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="minutes")}
