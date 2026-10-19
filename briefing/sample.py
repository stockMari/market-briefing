"""디자인 확인용 샘플 데이터.

실제 수집 코드(2단계 후반)가 만들 데이터와 '모양'이 완전히 같습니다.
숫자는 무작위로 만든 가짜이며, 화면에도 '샘플 데이터'라고 표시됩니다.
"""
import random
from datetime import date, datetime, timedelta, timezone

from . import period as P
from .judge import judge_high, judge_low, HIGH_VERDICTS, LOW_VERDICTS

KST = timezone(timedelta(hours=9))

# 2026년 KRX 휴장일 (샘플 달력용. 실제 실행 때는 거래소 데이터의 날짜를 씁니다)
KRX_HOLIDAYS_2026 = {
    date(2026, 1, 1), date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18),
    date(2026, 3, 2), date(2026, 5, 1), date(2026, 5, 5), date(2026, 5, 25),
    date(2026, 6, 3), date(2026, 8, 17), date(2026, 9, 24), date(2026, 9, 25),
    date(2026, 10, 5), date(2026, 10, 9), date(2026, 12, 25), date(2026, 12, 31),
}
# 해외 시장이 한국과 다르게 쉬는 날 (샘플용)
FOREIGN_CLOSED = {
    "대만가권": {date(2026, 10, 9)},
    "상해종합": {date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5),
              date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)},
    "닛케이225": {date(2026, 9, 21), date(2026, 9, 22), date(2026, 9, 23), date(2026, 10, 12)},
}


def krx_trading_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5 and d not in KRX_HOLIDAYS_2026:
            days.append(d)
        d += timedelta(days=1)
    return days


def market_days(name: str, region: str, start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        closed = FOREIGN_CLOSED.get(name, set())
        if region == "한국":
            closed = KRX_HOLIDAYS_2026
        if d.weekday() < 5 and d not in closed:
            days.append(d)
        d += timedelta(days=1)
    return days


KOSPI_SECTORS = [
    "음식료·담배", "섬유·의류", "종이·목재", "화학", "제약", "비금속", "금속",
    "기계·장비", "전기·전자", "의료·정밀기기", "운송장비·부품", "유통", "전기·가스",
    "건설", "운송·창고", "통신", "금융", "증권", "보험", "일반서비스", "IT 서비스",
    "오락·문화", "부동산",
]
KOSDAQ_SECTORS = [
    "음식료·담배", "섬유·의류", "종이·목재", "출판·매체복제", "화학", "제약", "비금속",
    "금속", "기계·장비", "전기·전자", "의료·정밀기기", "운송장비·부품", "기타제조",
    "건설", "유통", "운송·창고", "금융", "오락·문화", "통신", "IT 서비스", "일반서비스",
]

# (코드, 종목명, 시장, 업종) — KOSPI 앞 20개는 시가총액 상위 순서로 둡니다(샘플)
STOCKS = [
    ("005930", "삼성전자", "KOSPI", "전기·전자"),
    ("000660", "SK하이닉스", "KOSPI", "전기·전자"),
    ("373220", "LG에너지솔루션", "KOSPI", "전기·전자"),
    ("207940", "삼성바이오로직스", "KOSPI", "제약"),
    ("005380", "현대차", "KOSPI", "운송장비·부품"),
    ("012450", "한화에어로스페이스", "KOSPI", "기계·장비"),
    ("329180", "HD현대중공업", "KOSPI", "운송장비·부품"),
    ("000270", "기아", "KOSPI", "운송장비·부품"),
    ("105560", "KB금융", "KOSPI", "금융"),
    ("068270", "셀트리온", "KOSPI", "제약"),
    ("034020", "두산에너빌리티", "KOSPI", "기계·장비"),
    ("035420", "NAVER", "KOSPI", "IT 서비스"),
    ("055550", "신한지주", "KOSPI", "금융"),
    ("028260", "삼성물산", "KOSPI", "유통"),
    ("012330", "현대모비스", "KOSPI", "운송장비·부품"),
    ("042660", "한화오션", "KOSPI", "운송장비·부품"),
    ("032830", "삼성생명", "KOSPI", "보험"),
    ("267260", "HD현대일렉트릭", "KOSPI", "전기·전자"),
    ("086790", "하나금융지주", "KOSPI", "금융"),
    ("009540", "HD한국조선해양", "KOSPI", "운송장비·부품"),
    ("006400", "삼성SDI", "KOSPI", "전기·전자"),
    ("051910", "LG화학", "KOSPI", "화학"),
    ("010130", "고려아연", "KOSPI", "금속"),
    ("005490", "POSCO홀딩스", "KOSPI", "금속"),
    ("064350", "현대로템", "KOSPI", "운송장비·부품"),
    ("079550", "LIG넥스원", "KOSPI", "전기·전자"),
    ("010120", "LS ELECTRIC", "KOSPI", "전기·전자"),
    ("298040", "효성중공업", "KOSPI", "전기·전자"),
    ("042700", "한미반도체", "KOSPI", "전기·전자"),
    ("009150", "삼성전기", "KOSPI", "전기·전자"),
    ("010140", "삼성중공업", "KOSPI", "운송장비·부품"),
    ("047810", "한국항공우주", "KOSPI", "운송장비·부품"),
    ("003230", "삼양식품", "KOSPI", "음식료·담배"),
    ("271560", "오리온", "KOSPI", "음식료·담배"),
    ("090430", "아모레퍼시픽", "KOSPI", "화학"),
    ("006800", "미래에셋증권", "KOSPI", "증권"),
    ("039490", "키움증권", "KOSPI", "증권"),
    ("071050", "한국금융지주", "KOSPI", "증권"),
    ("000720", "현대건설", "KOSPI", "건설"),
    ("047040", "대우건설", "KOSPI", "건설"),
    ("028050", "삼성E&A", "KOSPI", "건설"),
    ("017670", "SK텔레콤", "KOSPI", "통신"),
    ("030200", "KT", "KOSPI", "통신"),
    ("015760", "한국전력", "KOSPI", "전기·가스"),
    ("011200", "HMM", "KOSPI", "운송·창고"),
    ("035720", "카카오", "KOSPI", "IT 서비스"),
    ("259960", "크래프톤", "KOSPI", "IT 서비스"),
    ("097950", "CJ제일제당", "KOSPI", "음식료·담배"),
    ("196170", "알테오젠", "KOSDAQ", "제약"),
    ("247540", "에코프로비엠", "KOSDAQ", "전기·전자"),
    ("028300", "HLB", "KOSDAQ", "제약"),
    ("277810", "레인보우로보틱스", "KOSDAQ", "기계·장비"),
    ("141080", "리가켐바이오", "KOSDAQ", "제약"),
    ("214450", "파마리서치", "KOSDAQ", "제약"),
    ("214150", "클래시스", "KOSDAQ", "의료·정밀기기"),
    ("058470", "리노공업", "KOSDAQ", "전기·전자"),
    ("095340", "ISC", "KOSDAQ", "전기·전자"),
    ("087010", "펩트론", "KOSDAQ", "제약"),
    ("145020", "휴젤", "KOSDAQ", "제약"),
    ("257720", "실리콘투", "KOSDAQ", "유통"),
    ("039030", "이오테크닉스", "KOSDAQ", "기계·장비"),
    ("240810", "원익IPS", "KOSDAQ", "기계·장비"),
    ("036930", "주성엔지니어링", "KOSDAQ", "기계·장비"),
    ("263750", "펄어비스", "KOSDAQ", "오락·문화"),
    ("298380", "에이비엘바이오", "KOSDAQ", "제약"),
]

INDEX_LEVELS = {
    "KOSPI": 3450, "KOSDAQ": 880, "다우": 46200, "나스닥": 22400, "S&P500": 6650,
    "닛케이225": 45800, "상해종합": 3850, "대만가권": 26300,
}
# 업종 분위기 (샘플): 조선·방산·전력기기는 강하고, 화학·건설은 약하게
SECTOR_BIAS = {
    "운송장비·부품": 4.5, "전기·전자": 3.2, "기계·장비": 3.8, "증권": 2.5,
    "화학": -2.8, "건설": -2.2, "음식료·담배": -1.4, "통신": -0.8, "부동산": -1.6,
}


def _round(x: float, n: int = 2) -> float:
    return round(float(x), n)


def build_sample(mode: str, run_date: date, cfg: dict) -> dict:
    cal = krx_trading_days(date(2026, 1, 2), run_date)
    if mode == "weekly":
        per = P.weekly(run_date, cal, cfg["flows"]["weekly_trend_weeks"])
    else:
        per = P.daily(run_date, cal, cfg["flows"]["daily_trend_days"])
    rng = random.Random(per.label)
    scale = 1.0 if mode == "weekly" else 0.45  # 하루 변동은 한 주보다 작게

    # 1. 지수
    indices = []
    for ix in cfg["indices"]:
        days = market_days(ix["name"], ix["region"], date(2026, 9, 1), per.target_end)
        end_d = max(d for d in days if d <= per.target_end)
        base_d = max(d for d in days if d <= (per.target_base if mode == "weekly" else per.base))
        if ix["region"] != "한국" and mode == "daily":
            # 미국·아시아는 실행 전날까지 마감된 장 기준
            end_d = max(d for d in days if d <= run_date - timedelta(days=1))
            base_d = max(d for d in days if d < end_d)
        pct = rng.gauss(0.6, 1.8) * scale
        if ix["name"] in ("KOSPI", "KOSDAQ"):
            pct = rng.gauss(1.4, 1.2) * scale
        close = INDEX_LEVELS[ix["name"]] * (1 + rng.gauss(0, 0.01))
        prev = close / (1 + pct / 100)
        indices.append({
            "name": ix["name"], "region": ix["region"],
            "close": _round(close), "change": _round(close - prev),
            "change_pct": _round(pct), "base_date": base_d.isoformat(), "end_date": end_d.isoformat(),
        })

    # 2. 투자자별 수급 (억원)
    def flow(mu, sd):
        return int(rng.gauss(mu, sd) * (1 if mode == "weekly" else 0.35))

    current = {
        "KOSPI": {"외국인": flow(8400, 3000), "기관": flow(-2100, 2500)},
        "KOSDAQ": {"외국인": flow(1200, 900), "기관": flow(350, 600)},
    }
    for m in current:
        current[m]["개인"] = -(current[m]["외국인"] + current[m]["기관"]) + flow(0, 300)

    if mode == "weekly":
        fridays, d = [], per.target_end
        for _ in range(per.trend_len):
            fridays.append(P.last_trading_day_on_or_before(d, cal))
            d -= timedelta(days=7)
        labels = [f"{x.month}/{x.day}" for x in reversed(fridays)]
    else:
        days = [x for x in cal if x <= per.end][-per.trend_len:]
        labels = [f"{x.month}/{x.day}" for x in days]
    trend = {"labels": labels}
    for m, (fmu, imu) in {"KOSPI": (3000, -800), "KOSDAQ": (400, 100)}.items():
        trend[m] = {
            "외국인": [flow(fmu, 5000) for _ in labels[:-1]] + [current[m]["외국인"]],
            "기관": [flow(imu, 3500) for _ in labels[:-1]] + [current[m]["기관"]],
        }

    # 3. 업종
    sectors = {}
    for m, names in (("KOSPI", KOSPI_SECTORS), ("KOSDAQ", KOSDAQ_SECTORS)):
        rows = [{"name": n, "change_pct": _round((SECTOR_BIAS.get(n, 0.3) + rng.gauss(0, 1.6)) * scale)}
                for n in names]
        sectors[m] = sorted(rows, key=lambda r: r["change_pct"], reverse=True)
    sector_pct = {(m, r["name"]): r["change_pct"] for m, rows in sectors.items() for r in rows}

    # 4. 52주 신고가 / 신저가
    jcfg = cfg["judgment"]
    pool = STOCKS[:]
    rng.shuffle(pool)
    strong = [s for s in pool if sector_pct[(s[2], s[3])] > 1.0]
    weak = [s for s in pool if sector_pct[(s[2], s[3])] <= 0.0]
    highs = []
    picks = strong[:16] + [s for s in pool if s not in strong][:6]
    for code, name, market, sector in picks:
        sp = sector_pct[(market, sector)]
        boost = rng.choice([1.5, 2.5, 3.5, 7.0, 9.0]) if sp > jcfg["sector_weak_pct"] else rng.choice([4.0, 8.0, 12.0])
        stock_pct = _round(max(sp + boost * scale + rng.gauss(0, 1.2), 0.8))
        kind, excess = judge_high(stock_pct, sp, jcfg)
        highs.append({"code": code, "name": name, "market": market, "sector": sector,
                      "change_pct": stock_pct, "sector_change_pct": sp, "excess_pp": excess,
                      "kind": kind, "verdict": HIGH_VERDICTS[kind]})
    lows = []
    used = {h["code"] for h in highs}
    low_pool = [s for s in weak if s[0] not in used][:5] + [s for s in pool if s[0] not in used and s not in weak][:3]
    for code, name, market, sector in low_pool:
        sp = sector_pct[(market, sector)]
        stock_pct = _round(sp - rng.choice([1.0, 2.0, 6.5, 9.0]) * scale + rng.gauss(0, 0.8))
        kind, excess = judge_low(stock_pct, sp, jcfg)
        lows.append({"code": code, "name": name, "market": market, "sector": sector,
                     "change_pct": stock_pct, "sector_change_pct": sp, "excess_pp": excess,
                     "kind": kind, "verdict": LOW_VERDICTS[kind]})

    # 5·6. 외국인 / 기관 순매수 상위 (억원)
    def top_list(seed_pool, base_amt):
        chosen = rng.sample(seed_pool, cfg["top_buyers"]["count"])
        amts = sorted((int(base_amt * rng.uniform(0.15, 1.0) * (1 if mode == "weekly" else 0.4)) for _ in chosen),
                      reverse=True)
        return [{"rank": i + 1, "code": c, "name": n, "market": m, "net_buy": a,
                 "change_pct": _round(sector_pct[(m, s)] + rng.gauss(1.0, 2.5) * scale)}
                for i, ((c, n, m, s), a) in enumerate(zip(chosen, amts))]

    big = STOCKS[:32]
    top_f = top_list(big[:14] + STOCKS[48:54], 9500)
    shared = [s for s in big if s[0] in {r["code"] for r in top_f}][:4]
    top_i = top_list(shared + rng.sample([s for s in STOCKS if s not in shared], 12), 3800)

    # 9. 신용잔고 (KOSPI 시총 상위)
    n_credit = cfg["credit"]["top_n_by_market_cap"]
    credit_rows = []
    for i, (code, name, market, sector) in enumerate([s for s in STOCKS if s[2] == "KOSPI"][:n_credit]):
        ratio = _round(abs(rng.gauss(0.6, 0.45)) + 0.05)
        credit_rows.append({
            "rank": i + 1, "code": code, "name": name,
            "credit_eok": int(rng.uniform(300, 9000) if i > 1 else rng.uniform(9000, 21000)),
            "ratio": ratio, "ratio_change_pp": _round(rng.gauss(0.02, 0.06) * scale, 2),
            "change_pct": _round(sector_pct[(market, sector)] + rng.gauss(0.5, 2.0) * scale),
        })
    k, q = 11.8, 8.9
    credit_trend = {"labels": labels, "KOSPI": [], "KOSDAQ": []}
    for _ in labels:
        k += rng.gauss(0.12, 0.18) * (1 if mode == "weekly" else 0.3)
        q += rng.gauss(0.03, 0.12) * (1 if mode == "weekly" else 0.3)
        credit_trend["KOSPI"].append(_round(k, 2))
        credit_trend["KOSDAQ"].append(_round(q, 2))

    return {
        "mode": mode,
        "label": per.label,
        "title": per.title,
        "period": per.to_dict(),
        "sample": True,
        "generated_at": datetime.combine(run_date, datetime.min.time(), KST)
        .replace(hour=9 if mode == "weekly" else 7, minute=0 if mode == "weekly" else 30).isoformat(),
        "judgment": jcfg,
        "summary": None,
        "indices": indices,
        "flows": {"unit": "억원", "current": current, "trend": trend},
        "sectors": sectors,
        "highs": highs,
        "lows": lows,
        "top_buyers": {"외국인": top_f, "기관": top_i},
        "credit": {"unit": "억원", "as_of": per.end.isoformat(), "stocks": credit_rows,
                   "market_trend": credit_trend, "source_pending": True},
        "news": None,
    }
