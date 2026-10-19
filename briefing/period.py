"""기간 계산. Daily와 Weekly의 차이는 오직 여기서 정해집니다.

- Daily : 실행일 직전 거래일 종가  vs  그 전 거래일 종가
- Weekly: 이번 주 금요일 종가      vs  지난주 금요일 종가
금요일이 휴장이면 그 주의 마지막 거래일을 씁니다.
"""
from dataclasses import dataclass, asdict
from datetime import date, timedelta

WEEKDAYS = "월화수목금토일"


@dataclass
class Period:
    mode: str            # "daily" | "weekly"
    label: str           # 파일 이름: 2026-10-16 / 2026-W42
    title: str           # 화면 제목: 10월 16일(금) / 10월 3주차
    base: date           # 비교 기준일 (이 날 종가 대비)
    end: date            # 기준일 (이 날 종가)
    target_base: date    # 원래 기준이었어야 할 날 (휴장 확인용)
    target_end: date
    trend_len: int       # 추이 그래프 길이 (20거래일 / 12주)

    @property
    def unit(self) -> str:
        return "주" if self.mode == "weekly" else "일"

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("base", "end", "target_base", "target_end"):
            d[k] = d[k].isoformat()
        d["notes"] = self.holiday_notes()
        return d

    def holiday_notes(self) -> list[str]:
        notes = []
        for target, actual in ((self.target_base, self.base), (self.target_end, self.end)):
            if target != actual:
                notes.append(f"{fmt_md(target)} 휴장 → {fmt_md(actual)} 종가 사용")
        return notes


def fmt_md(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def last_trading_day_on_or_before(d: date, trading_days: list[date]) -> date:
    candidates = [t for t in trading_days if t <= d]
    if not candidates:
        raise ValueError(f"{d} 이전 거래일 데이터가 없습니다")
    return max(candidates)


def month_week(friday: date) -> str:
    """한국식 'N월 M주차' (그 주의 목요일이 속한 달 기준)."""
    thursday = friday - timedelta(days=1)
    return f"{thursday.month}월 {(thursday.day - 1) // 7 + 1}주차"


def weekly(run_date: date, trading_days: list[date], weeks: int = 12) -> Period:
    # 어제 이전의 가장 최근 금요일 (토요일 실행 → 전날 금요일)
    yesterday = run_date - timedelta(days=1)
    target_end = yesterday - timedelta(days=(yesterday.weekday() - 4) % 7)
    target_base = target_end - timedelta(days=7)
    end = last_trading_day_on_or_before(target_end, trading_days)
    base = last_trading_day_on_or_before(target_base, trading_days)
    iso = target_end.isocalendar()
    return Period(
        mode="weekly",
        label=f"{iso.year}-W{iso.week:02d}",
        title=month_week(target_end),
        base=base, end=end, target_base=target_base, target_end=target_end,
        trend_len=weeks,
    )


def daily(run_date: date, trading_days: list[date], days: int = 20) -> Period:
    # 아침 7시 30분 실행 → 한국장은 아직 안 열렸으므로 '어제까지'가 대상
    end = last_trading_day_on_or_before(run_date - timedelta(days=1), trading_days)
    base = last_trading_day_on_or_before(end - timedelta(days=1), trading_days)
    return Period(
        mode="daily",
        label=end.isoformat(),
        title=f"{end.month}월 {end.day}일({WEEKDAYS[end.weekday()]})",
        base=base, end=end, target_base=base, target_end=end,
        trend_len=days,
    )
