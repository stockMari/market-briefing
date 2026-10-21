"""7번: 시장 요약 3줄을 정해진 문장 틀로 자동 작성 (무료, API 키 불필요).

1줄: 지수  2줄: 수급  3줄: 업종 · 52주 신고가
"""
from collections import Counter


def _move(pct: float, strong: float) -> str:
    if abs(pct) < 0.05:
        return "보합"
    if pct > 0:
        return "급등" if pct >= strong else "상승"
    return "급락" if pct <= -strong else "하락"


def _idx(ix: dict, strong: float, with_close: bool = False) -> str:
    s = f"{ix['name']} {abs(ix['change_pct']):.2f}% {_move(ix['change_pct'], strong)}"
    if with_close:
        s += f"({ix['close']:,.0f})"
    return s


def _won(eok: int) -> str:
    """억원 → '3,204억' / '1.1조'"""
    a = abs(eok)
    return f"{a / 10000:.1f}조" if a >= 10000 else f"{a:,}억"


def _flow(who: str, eok: int) -> str:
    return f"{who} {_won(eok)} {'순매수' if eok >= 0 else '순매도'}"


def _streak(values: list[int]) -> int:
    """마지막 값과 같은 방향(+/-)이 몇 번 연속인지."""
    if not values or values[-1] == 0:
        return 0
    sign = values[-1] > 0
    n = 0
    for v in reversed(values):
        if v != 0 and (v > 0) == sign:
            n += 1
        else:
            break
    return n


def write_summary(r: dict) -> list[str]:
    weekly = r["mode"] == "weekly"
    strong = 3.0 if weekly else 2.0       # 이 이상이면 '급등/급락'
    unit = "주" if weekly else "거래일"
    ix = {i["name"]: i for i in r["indices"] if i["change_pct"] is not None}

    # 1줄: 지수
    parts = [_idx(ix[n], strong, with_close=(n == "KOSPI")) for n in ("KOSPI", "KOSDAQ") if n in ix]
    abroad = []
    for group in (("다우", "나스닥", "S&P500"), ("닛케이225", "상해종합", "대만가권")):
        movers = [ix[n] for n in group if n in ix]
        if movers:
            m = max(movers, key=lambda i: abs(i["change_pct"]))
            abroad.append(f"{m['name']} {m['change_pct']:+.2f}%")
    line1 = ", ".join(parts)
    if abroad:
        line1 += f" · 해외 {', '.join(abroad)}"

    # 2줄: 수급 (KOSPI 기준) + 연속 기록 + 동반 순매수
    cur = r["flows"]["current"]["KOSPI"]
    line2 = f"KOSPI {_flow('외국인', cur['외국인'])}, {_flow('기관', cur['기관'])}"
    st = _streak(r["flows"]["trend"]["KOSPI"]["외국인"])
    if st >= 3:
        line2 += f" · 외국인 {st}{unit} 연속 {'순매수' if cur['외국인'] >= 0 else '순매도'}"
    tb = r["top_buyers"]
    both = [x["name"] for x in tb["외국인"] if x["code"] in {y["code"] for y in tb["기관"]}]
    if both:
        line2 += f" · 동반 순매수 {both[0]}" + (f" 외 {len(both) - 1}종목" if len(both) > 1 else "")

    # 3줄: 업종 강약 + 52주 신고가가 몰린 곳
    ks = r["sectors"].get("KOSPI", [])
    line3 = ""
    if ks:
        up, dn = ks[0], ks[-1]
        if dn["change_pct"] > 0:      # 모든 업종 상승
            line3 = f"업종 전반 강세, 최강 {up['name']} {up['change_pct']:+.2f}% · 최약 {dn['name']} {dn['change_pct']:+.2f}%"
        elif up["change_pct"] < 0:    # 모든 업종 하락
            line3 = f"업종 전반 약세, 선방 {up['name']} {up['change_pct']:+.2f}% · 최약 {dn['name']} {dn['change_pct']:+.2f}%"
        else:
            line3 = f"업종 강세 {up['name']} {up['change_pct']:+.2f}%, 약세 {dn['name']} {dn['change_pct']:+.2f}%"
    if r["highs"]:
        line3 += f" · 52주 신고가 {len(r['highs'])}개"
        top2 = Counter(h["sector"] for h in r["highs"]).most_common(2)
        if top2[0][1] >= 2 and (len(top2) == 1 or top2[0][1] > top2[1][1]):
            line3 += f"({top2[0][0]} {top2[0][1]}개 최다)"
    else:
        line3 += " · 52주 신고가 없음"
    if len(r["lows"]) > len(r["highs"]) * 2 and len(r["lows"]) >= 10:
        line3 += f", 신저가 {len(r['lows'])}개"

    return [line1, line2, line3.lstrip(" ·")]
