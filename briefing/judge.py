"""52주 신고가/신저가 종목 판정.

초과수익(%p) = 종목 등락률 - 소속 섹터 등락률
기준값(X %p, 약한 섹터 기준)은 config.yaml 의 judgment 에서 바꿉니다.
"""

# 화면에 쓰는 판정 이름. kind 는 색상 구분용(동반 / 주도 / 개별 / 혼조)
HIGH_VERDICTS = {
    "together": "섹터 동반",
    "leader": "섹터 동반 + 주도주",
    "solo": "개별 강세(개인기)",
    "mixed": "혼조",
}
LOW_VERDICTS = {
    "together": "섹터 동반 약세",
    "leader": "섹터 약세 + 낙폭 과대",
    "solo": "개별 약세",
    "mixed": "혼조",
}


def judge_high(stock_pct: float, sector_pct: float, cfg: dict) -> tuple[str, float]:
    x, weak = cfg["individual_excess_pp"], cfg["sector_weak_pct"]
    excess = stock_pct - sector_pct
    sector_strong = sector_pct > weak
    if sector_strong:
        kind = "leader" if excess >= x else "together"
    else:
        kind = "solo" if excess >= x else "mixed"
    return kind, round(excess, 2)


def judge_low(stock_pct: float, sector_pct: float, cfg: dict) -> tuple[str, float]:
    x, weak = cfg["individual_excess_pp"], cfg["sector_weak_pct"]
    excess = stock_pct - sector_pct
    sector_weak = sector_pct <= weak
    if sector_weak:
        kind = "leader" if excess <= -x else "together"
    else:
        kind = "solo" if excess <= -x else "mixed"
    return kind, round(excess, 2)
