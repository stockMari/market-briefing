"""주간 실적 캘린더 (미국 동부시간 기준).

- 실적 일정: 야후 파이낸스 실적 캘린더 (장전 BMO / 장후 AMC / 시간 미정)
- 경제지표: 야후 경제 캘린더(미국) + calendar.yaml (금리 결정 등)
- 관심기업과 체크포인트 문구, 표시 기준은 config.yaml 의 earnings_calendar 에서 바꿉니다.
"""
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from .events import _load_yaml

ET, KST = ZoneInfo("America/New_York"), ZoneInfo("Asia/Seoul")
WEEKDAYS = "월화수목금토일"

# 야후 경제지표 이름(앞부분이 같으면 매칭) → (한글 이름, 중요도, 같은 일정으로 볼 calendar.yaml 키워드)
ECON = [
    ("Fed Funds Tgt Rate", "FOMC 금리 결정", 3, "FOMC"),
    ("Non-Farm Payrolls", "비농업 고용", 3, "고용"),
    ("Unemployment Rate", "실업률", 2, "고용"),
    ("ADP National Employment", "ADP 민간고용", 2, "ADP"),
    ("Core PCE Price Index MM", "PCE 물가", 3, "PCE"),
    ("PCE Price Index MM", "PCE 물가", 3, "PCE"),
    ("Core CPI MM", "소비자물가(CPI)", 3, "CPI"),
    ("CPI MM", "소비자물가(CPI)", 3, "CPI"),
    ("GDP Advance", "GDP 속보치", 3, "GDP"),
    ("GDP Prelim", "GDP 잠정치", 3, "GDP"),
    ("GDP Second", "GDP 잠정치", 3, "GDP"),
    ("GDP Final", "GDP 확정치", 3, "GDP"),
    ("GDP Third", "GDP 확정치", 3, "GDP"),
    ("PPI Final Demand MM", "생산자물가(PPI)", 2, "PPI"),
    ("Retail Sales MM", "소매판매", 2, "소매판매"),
    ("ISM Manufacturing PMI", "ISM 제조업", 2, "ISM 제조업"),
    ("ISM N-Mfg PMI", "ISM 서비스업", 2, "ISM 서비스업"),
    ("Consumer Confidence", "컨퍼런스보드 소비자신뢰", 2, "소비자신뢰"),
    ("U Mich Sentiment", "미시간대 소비심리", 1, "소비심리"),
    ("JOLTS Job Openings", "JOLTS 구인", 2, "JOLTS"),
    ("Employment Costs", "고용비용지수(ECI)", 2, "ECI"),
    ("Durable Goods", "내구재 주문", 1, "내구재"),
]
TIMING = {"BMO": "bmo", "AMC": "amc"}
LISTED_URLS = ("https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
               "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")
_listed: set[str] | None = None


def listed_symbols(log) -> set[str]:
    """나스닥·뉴욕거래소 등 미국 정규 거래소 상장 종목 (장외 OTC 제외용)."""
    global _listed
    if _listed is None:
        import requests
        syms = set()
        for url in LISTED_URLS:
            try:
                text = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"}).text
                for line in text.splitlines()[1:]:
                    sym = line.split("|")[0].strip()
                    if sym and not sym.startswith("File Creation"):
                        syms.add(sym.replace(".", "-"))
            except Exception as e:  # noqa: BLE001
                log(f"  ! 상장 종목 목록 실패 ({url.rsplit('/', 1)[-1]}): {e}")
        _listed = syms
    return _listed


def week_start_for(run_date: date) -> date:
    """평일이면 그 주 월요일, 주말이면 다음 주 월요일."""
    if run_date.weekday() >= 5:
        return run_date + timedelta(days=7 - run_date.weekday())
    return run_date - timedelta(days=run_date.weekday())


def _pages(fetch, log, max_rows=3000):
    frames, offset = [], 0
    while offset < max_rows:
        df = fetch(offset)
        if df is None or df.empty:
            break
        frames.append(df)
        if len(df) < 100:
            break
        offset += 100
        time.sleep(0.5)
    return pd.concat(frames) if frames else pd.DataFrame()


def _et_date(ts) -> date:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    utc = ts.tz_convert("UTC")
    # 시간 미정 일정은 자정(UTC)으로 오므로 날짜만 그대로 씀
    if utc.hour == 0 and utc.minute == 0:
        return utc.date()
    return ts.tz_convert(ET).date()


def fetch_earnings(start: date, end: date, log, market_cap=None) -> list[dict]:
    cal = yf.Calendars(start=start, end=end + timedelta(days=1))
    df = _pages(lambda off: cal.get_earnings_calendar(
        market_cap=market_cap, filter_most_active=False, start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(), limit=100, offset=off, force=True), log)
    listed = listed_symbols(log)
    rows, seen = [], set()
    for sym, r in df.iterrows():
        d = _et_date(r.get("Event Start Date"))
        company = str(r.get("Company") or sym)
        # 장외(OTC) 종목 제외, 같은 날 같은 회사(예: GOOGL/GOOG)는 하나만
        if not (start <= d <= end) or (listed and str(sym) not in listed) \
                or (sym, d) in seen or (company, d) in seen:
            continue
        seen.update({(sym, d), (company, d)})

        def num(k):
            v = r.get(k)
            return None if v is None or pd.isna(v) else float(v)
        rows.append({"ticker": str(sym), "company": company, "date": d.isoformat(),
                     "slot": TIMING.get(str(r.get("Timing") or "").upper(), "tns"),
                     "mcap_b": round(num("Marketcap") / 1e9, 1) if num("Marketcap") else None,
                     "eps_est": num("EPS Estimate"), "eps_act": num("Reported EPS"), "surprise": num("Surprise(%)")})
    log(f"  · 실적 일정 {start}~{end}: {len(rows)}건")
    return rows


def fetch_econ(start: date, end: date, log) -> list[dict]:
    cal = yf.Calendars(start=start, end=end + timedelta(days=1))
    df = _pages(lambda off: cal.get_economic_events_calendar(
        start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), limit=100, offset=off, force=True),
        log, max_rows=1000)
    out, seen = [], set()
    for name, r in df.iterrows():
        if str(r.get("Region", "")).upper() not in ("US", "UNITED STATES"):
            continue
        hit = next((e for e in ECON if str(name).lower().startswith(e[0].lower())), None)
        if not hit:
            continue
        ts = pd.Timestamp(r.get("Event Time"))
        ts = (ts.tz_localize("UTC") if ts.tzinfo is None else ts).tz_convert(ET)
        d = ts.date()
        if not (start <= d <= end) or (hit[1], d) in seen:
            continue
        seen.add((hit[1], d))
        period = str(r.get("For") or r.get("Period") or "").strip()
        out.append({"date": d.isoformat(), "time": ts.strftime("%H:%M"), "title": hit[1] + (f" ({period})" if period and period != "nan" else ""),
                    "importance": hit[2], "key": hit[3], "country": "US", "tz": "ET"})
    log(f"  · 경제지표 {start}~{end}: {len(out)}건")
    return out


def yaml_events(start: date, end: date) -> list[dict]:
    """calendar.yaml 일정. 미국 일정은 한국 시간 → 미국 동부시간으로 바꿔 미국 날짜에 놓습니다."""
    out = []
    for e in _load_yaml():
        d, t, tz = e["date"], e["time"], "KST"
        if e["country"] == "US" and t:
            kst = datetime.combine(d, datetime.strptime(t, "%H:%M").time(), KST).astimezone(ET)
            d, t, tz = kst.date(), kst.strftime("%H:%M"), "ET"
        if start <= d <= end:
            out.append({"date": d.isoformat(), "time": t, "title": e["title"], "importance": e["importance"],
                        "country": e["country"], "tz": tz, "category": e["category"], "key": ""})
    return out


def _merge_events(fixed: list[dict], econ: list[dict]) -> list[dict]:
    """같은 날 calendar.yaml 에 이미 있는 지표(예: FOMC)는 야후 쪽을 빼서 중복을 없앱니다."""
    out = list(fixed)
    for e in econ:
        if any(f["date"] == e["date"] and e["key"] and e["key"] in f["title"] for f in fixed):
            continue
        out.append(e)
    return sorted(out, key=lambda e: (e["date"], e["time"] or "99:99", -e["importance"]))


def build_week(run_date: date, cfg: dict, log=print) -> dict:
    ec = cfg.get("earnings_calendar", {})
    watch = ec.get("watchlist", {}) or {}
    min_cap = ec.get("min_mcap_b", 8)
    per_slot = ec.get("per_slot", 6)
    mon = week_start_for(run_date)
    fri = mon + timedelta(days=4)
    iso = mon.isocalendar()

    rows = fetch_earnings(mon, fri, log)
    try:
        econ = fetch_econ(mon, fri, log)
    except Exception as e:  # noqa: BLE001
        log(f"  ! 경제지표 캘린더 실패: {e}")
        econ = []
    events = _merge_events(yaml_events(mon, fri), econ)

    def pick(slot_rows):
        cand = [r for r in slot_rows if r["ticker"] in watch or (r["mcap_b"] or 0) >= min_cap]
        cand.sort(key=lambda r: (r["ticker"] not in watch, -(r["mcap_b"] or 0)))
        for r in cand:
            r["watch"] = r["ticker"] in watch
        return {"total": len(slot_rows), "shown": cand[:per_slot], "more": cand[per_slot:],
                "small": len(slot_rows) - len(cand)}

    days = []
    for i in range(5):
        d = mon + timedelta(days=i)
        today = [r for r in rows if r["date"] == d.isoformat()]
        checks = [f"{r['ticker']} {watch[r['ticker']]}" for r in sorted(today, key=lambda r: -(r["mcap_b"] or 0))
                  if r["ticker"] in watch and watch[r["ticker"]]]
        days.append({"date": d.isoformat(), "dow": WEEKDAYS[i], "total": len(today),
                     "bmo": pick([r for r in today if r["slot"] == "bmo"]),
                     "amc": pick([r for r in today if r["slot"] == "amc"]),
                     "tns": pick([r for r in today if r["slot"] == "tns"]),
                     "events": [e for e in events if e["date"] == d.isoformat()],
                     "checks": checks})

    total = sum(d["total"] for d in days)
    busiest = max(days, key=lambda d: d["total"])
    big = list(dict.fromkeys(e["title"].split(" (")[0].split(" · ")[0] for e in events if e["importance"] >= 3))[:3]
    headline = (ec.get("headlines") or {}).get(f"{iso.year}-W{iso.week:02d}") or \
        f"실적 발표 {total}건 · {busiest['dow']}요일 {busiest['total']}건으로 최다" + \
        (f" · {', '.join(big)}" if big else "")

    later = build_later(fri, ec, watch, log)
    return {"label": f"{iso.year}-W{iso.week:02d}", "start": mon.isoformat(), "end": fri.isoformat(),
            "total": total, "headline": headline, "days": days, "later": later,
            "filters": {"min_mcap_b": min_cap, "per_slot": per_slot, "watchlist": len(watch)},
            "generated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="minutes")}


def build_later(fri: date, ec: dict, watch: dict, log) -> dict:
    """그다음 2주: 굵직한 일정만 텍스트로."""
    weeks = ec.get("later_weeks", 2)
    start, end = fri + timedelta(days=3), fri + timedelta(days=3 + 7 * weeks - 3)
    big_cap = ec.get("later_min_mcap_b", 100)
    try:
        rows = fetch_earnings(start, end, log, market_cap=ec.get("min_mcap_b", 8) * 1e9)
    except Exception as e:  # noqa: BLE001
        log(f"  ! 이후 실적 일정 실패: {e}")
        rows = []
    try:
        econ = fetch_econ(start, end, log)
    except Exception as e:  # noqa: BLE001
        econ = []
    events = [e for e in _merge_events(yaml_events(start, end), econ) if e["importance"] >= 2]
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            evs = [f"{e['time'] + ' ' if e['time'] else ''}{e['title']}{' (한국시간)' if e['tz'] == 'KST' else ''}"
                   for e in events if e["date"] == d.isoformat()]
            ers = sorted((r for r in rows if r["date"] == d.isoformat()
                          and (r["ticker"] in watch or (r["mcap_b"] or 0) >= big_cap)), key=lambda r: -(r["mcap_b"] or 0))
            tick = [f"{r['ticker']}{'(장전)' if r['slot'] == 'bmo' else '(장후)' if r['slot'] == 'amc' else ''}" for r in ers]
            if evs or tick:
                days.append({"date": d.isoformat(), "dow": WEEKDAYS[d.weekday()], "events": evs, "earnings": tick})
        d += timedelta(days=1)
    return {"start": start.isoformat(), "end": end.isoformat(), "days": days, "min_mcap_b": big_cap}
