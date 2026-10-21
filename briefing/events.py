"""Weekly: 앞으로 2주 주요 일정.

세 군데에서 모읍니다.
1. calendar.yaml  — 금리 결정, 경제지표, 휴장일 (직접 고칠 수 있는 파일)
2. 자동 계산       — 한국 옵션 만기일(둘째 목요일), 미국 옵션 만기일(셋째 금요일)
3. 야후 파이낸스   — config.yaml 에 적은 미국 대형주 실적 발표일
"""
from datetime import date, timedelta

import yaml

from .config import ROOT

WEEKDAYS = "월화수목금토일"


def _nth_weekday(y: int, m: int, weekday: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _load_yaml(path=None) -> list[dict]:
    path = path or ROOT / "calendar.yaml"
    if not path.exists():
        return []
    rows = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("events") or []
    out = []
    for r in rows:
        d = r["date"] if isinstance(r["date"], date) else date.fromisoformat(str(r["date"]))
        out.append({"date": d, "time": str(r.get("time") or ""), "country": r.get("country", ""),
                    "category": r.get("category", ""), "importance": int(r.get("importance", 1)),
                    "title": r["title"], "source": "calendar"})
    return out


def _expiries(start: date, end: date, kr_closed: set[date]) -> list[dict]:
    out = []
    for y, m in _months(start, end):
        quarterly = m in (3, 6, 9, 12)
        # 한국: 둘째 목요일, 휴장이면 그 전 거래일
        d = _nth_weekday(y, m, 3, 2)
        while d in kr_closed or d.weekday() >= 5:
            d -= timedelta(days=1)
        out.append({"date": d, "time": "15:20", "country": "KR", "category": "만기",
                    "importance": 3 if quarterly else 2, "source": "auto",
                    "title": "선물·옵션 동시만기일" if quarterly else "옵션 만기일"})
        # 미국: 셋째 금요일 (현지 날짜)
        d = _nth_weekday(y, m, 4, 3)
        out.append({"date": d, "time": "", "country": "US", "category": "만기",
                    "importance": 2 if quarterly else 1, "source": "auto",
                    "title": "미국 분기 옵션·선물 동시만기 (쿼드러플 위칭)" if quarterly else "미국 월물 옵션 만기"})
    return [e for e in out if start <= e["date"] <= end]


def _earnings(start: date, end: date, tickers: dict, log) -> list[dict]:
    if not tickers:
        return []
    try:
        import yfinance as yf
    except ImportError:
        return []
    out = []
    for sym, name in tickers.items():
        try:
            cal = yf.Ticker(sym).calendar
            dates = cal.get("Earnings Date") if isinstance(cal, dict) else None
            if dates is None and hasattr(cal, "loc"):  # 예전 yfinance 는 표 형태
                dates = list(cal.loc["Earnings Date"])
            for d in dates or []:
                d = d if isinstance(d, date) else d.date()
                if start <= d <= end:
                    out.append({"date": d, "time": "", "country": "US", "category": "실적",
                                "importance": 2, "source": "yfinance",
                                "title": f"{name} 실적 발표 (현지 날짜)"})
                    break
        except Exception as e:  # noqa: BLE001  한 종목 실패는 건너뜀
            log(f"  · {sym} 실적 일정 조회 실패: {e}")
    return out


def upcoming(after: date, cfg: dict, log=print) -> dict:
    """after(리포트 기준 금요일) 다음 월요일부터 2주(일요일까지)."""
    ecfg = cfg.get("events", {})
    weeks = ecfg.get("weeks", 2)
    start = after + timedelta(days=(7 - after.weekday()) % 7 or 7)   # 다음 월요일
    end = start + timedelta(days=7 * weeks - 1)

    fixed = _load_yaml()
    kr_closed = {e["date"] for e in fixed if e["category"] == "휴장" and e["country"] == "KR"}
    items = [e for e in fixed if start <= e["date"] <= end]
    items += _expiries(start, end, kr_closed)
    if not ecfg.get("show_us_monthly_opex", True):
        items = [e for e in items if not (e["category"] == "만기" and e["country"] == "US" and e["importance"] == 1)]
    items += _earnings(start, end, ecfg.get("earnings", {}), log)
    items.sort(key=lambda e: (e["date"], e["time"] or "99", -e["importance"]))

    weeks_out = []
    for w in range(weeks):
        ws, we = start + timedelta(days=7 * w), start + timedelta(days=7 * w + 6)
        days = {}
        for e in items:
            if ws <= e["date"] <= we:
                days.setdefault(e["date"], []).append({**e, "date": e["date"].isoformat()})
        weeks_out.append({
            "label": "다음 주" if w == 0 else ("그다음 주" if w == 1 else f"{w + 1}주 뒤"),
            "start": ws.isoformat(), "end": we.isoformat(),
            "days": [{"date": d.isoformat(), "dow": WEEKDAYS[d.weekday()], "events": evs}
                     for d, evs in sorted(days.items())],
        })
    log(f"  · {start}~{end} 일정 {len(items)}건")
    return {"start": start.isoformat(), "end": end.isoformat(), "weeks": weeks_out}
