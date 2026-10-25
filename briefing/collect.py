"""실제 데이터로 리포트 만들기 (1~6번 항목).

결과는 sample.py 와 똑같은 모양의 딕셔너리라서, 화면 코드는 그대로 씁니다.
Daily/Weekly 의 차이는 period(기간) 하나뿐입니다.
"""
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from . import krx, overseas
from . import period as P
from .judge import judge_high, judge_low, HIGH_VERDICTS, LOW_VERDICTS

KST = timezone(timedelta(hours=9))
EOK = 1e8  # 1억원


def _r(x, n=2):
    return None if x is None or pd.isna(x) else round(float(x), n)


# ── 1. 주요 지수 ───────────────────────────────────────
def collect_indices(cfg, per, run_date, log):
    rows = []
    for ix in cfg["indices"]:
        row = {"name": ix["name"], "region": ix["region"], "close": None, "change": None,
               "change_pct": None, "base_date": per.base.isoformat(), "end_date": per.end.isoformat()}
        try:
            if ix.get("source") == "krx":
                s = krx.index_daily(ix["code"], per.base - timedelta(days=7), per.end)["종가"]
                end_d, base_d = per.end, per.base
            else:
                s = overseas.closes(ix["ticker"], per.target_base - timedelta(days=12), run_date)
                if per.mode == "weekly":
                    end_d = max(d for d in s.index if d <= per.target_end)
                    base_d = max(d for d in s.index if d <= per.target_base)
                else:  # 실행 전날까지 마감된 장
                    end_d = max(d for d in s.index if d < run_date)
                    base_d = max(d for d in s.index if d < end_d)
            close, prev = float(s[end_d]), float(s[base_d])
            row.update(close=_r(close), change=_r(close - prev), change_pct=_r((close / prev - 1) * 100),
                       base_date=base_d.isoformat(), end_date=end_d.isoformat())
        except Exception as e:  # noqa: BLE001  하나가 실패해도 나머지는 계속
            log(f"  ! {ix['name']} 지수 실패: {e}")
            row["error"] = str(e)
        rows.append(row)
    return rows


# ── 2. 투자자별 수급 ───────────────────────────────────
def collect_flows(cfg, per, cal, log):
    start = next(d for d in cal if d > per.base)
    current, trend = {}, {}
    hist_start = per.end - timedelta(weeks=per.trend_len + 1) if per.mode == "weekly" \
        else [d for d in cal if d <= per.end][-per.trend_len]
    labels = None
    for m in ("KOSPI", "KOSDAQ"):
        df = krx.flows_by_date(min(start, hist_start), per.end, m)
        cur = df[df.index >= start].sum() / EOK
        current[m] = {k: int(round(cur[k])) for k in ("외국인", "기관", "개인")}
        if per.mode == "weekly":
            # 같은 주(금요일 기준)끼리 묶어서 합계, 라벨은 그 주 마지막 거래일
            key = [d + timedelta(days=(4 - d.weekday()) % 7) for d in df.index]
            g = df.groupby(key)
            sums = g.sum().tail(per.trend_len)
            last_days = pd.Series(df.index, index=key).groupby(level=0).max().loc[sums.index]
        else:
            sums = df.tail(per.trend_len)
            last_days = pd.Series(sums.index, index=sums.index)
        labels = [f"{d.month}/{d.day}" for d in last_days]
        trend[m] = {k: [int(round(v / EOK)) for v in sums[k]] for k in ("외국인", "기관")}
    trend["labels"] = labels
    return {"unit": "억원", "current": current, "trend": trend}


# ── 3. 업종 ───────────────────────────────────────────
def collect_sectors(per, members, log):
    sectors, sector_pct, unmatched = {}, {}, []
    for m in ("KOSPI", "KOSDAQ"):
        base_idx = krx.index_closes(per.base, m)
        end_idx = krx.index_closes(per.end, m)
        by_norm = {krx.norm(n): n for n in end_idx.index}
        rows = []
        for sector in sorted(members.loc[members["시장"] == m, "업종명"].dropna().unique()):
            key = by_norm.get(krx.norm(sector))
            if key is None or key not in base_idx.index or not base_idx[key]:
                unmatched.append(f"{m} {sector}")
                continue
            pct = (end_idx[key] / base_idx[key] - 1) * 100
            rows.append({"name": sector, "change_pct": _r(pct)})
            sector_pct[(m, sector)] = _r(pct)
        sectors[m] = sorted(rows, key=lambda r: r["change_pct"], reverse=True)
    if unmatched:
        log(f"  · 업종지수가 없는 업종 {len(unmatched)}개는 소속 종목으로 계산: {', '.join(unmatched[:8])}")
    return sectors, sector_pct


# ── 4. 52주 신고가 / 신저가 ─────────────────────────────
def collect_highs_lows(cfg, per, cal, members, sector_pct, log):
    j = cfg["judgment"]
    start = next(d for d in cal if d > per.base)
    window = [d for d in cal if start - timedelta(days=372) <= d <= per.end]
    panel = krx.price_panel(window, log)
    close = panel["close"]
    hi_src = panel["high"] if j.get("high_basis") == "high" else close
    lo_src = panel["low"] if j.get("high_basis") == "high" else close
    one_year_ago = start - timedelta(days=365)
    prior = [d for d in close.index if one_year_ago <= d < start]
    during = [d for d in close.index if start <= d <= per.end]

    # 대상: 보통주(코드 끝자리 0), 스팩 제외, 업종 정보 있음, 시가총액 기준 이상, 1년치 이력 충분
    min_cap = j.get("min_market_cap_eok", 0) * EOK
    history = hi_src.loc[prior].notna().sum()
    ok = [t for t in close.columns
          if t.endswith("0") and t in members.index
          and "스팩" not in str(members.at[t, "종목명"])
          and panel["mktcap"].get(t, 0) >= min_cap
          and history.get(t, 0) >= 200]

    prior_hi, prior_lo = hi_src.loc[prior, ok].max(), lo_src.loc[prior, ok].min()
    now_hi, now_lo = hi_src.loc[during, ok].max(), lo_src.loc[during, ok].min()
    ret = (close.loc[per.end, ok] / close.loc[per.base, ok] - 1) * 100

    # 업종지수가 없는 업종(은행·기타금융 등)은 소속 종목의 시가총액 가중 평균으로 계산
    all_ret = (close.loc[per.end] / close.loc[per.base] - 1) * 100
    estimated = {}

    def sector_rate(mk, sector):
        if (mk, sector) in sector_pct:
            return sector_pct[(mk, sector)], False
        if (mk, sector) not in estimated:
            codes = members.index[(members["시장"] == mk) & (members["업종명"] == sector)]
            r = all_ret.reindex(codes).dropna()
            w = panel["mktcap"].reindex(r.index).fillna(0)
            estimated[(mk, sector)] = _r((r * w).sum() / w.sum()) if w.sum() > 0 else None
        return estimated[(mk, sector)], True

    def rows(codes, fn, names):
        out = []
        for t in codes:
            mk, sector = members.at[t, "시장"], members.at[t, "업종명"]
            sp, est = sector_rate(mk, sector)
            if sp is None or pd.isna(ret[t]):
                continue
            kind, excess = fn(float(ret[t]), sp, j)
            out.append({"code": t, "name": members.at[t, "종목명"], "market": mk, "sector": sector,
                        "change_pct": _r(ret[t]), "sector_change_pct": sp, "sector_estimated": est,
                        "excess_pp": excess, "kind": kind, "verdict": names[kind]})
        return out

    highs = rows(now_hi.index[now_hi > prior_hi], judge_high, HIGH_VERDICTS)
    lows = rows(now_lo.index[now_lo < prior_lo], judge_low, LOW_VERDICTS)
    log(f"  · 비교 대상 {len(ok)}종목 → 신고가 {len(highs)}, 신저가 {len(lows)}")
    return highs, lows, panel


# ── 5·6. 외국인 / 기관 순매수 상위 ─────────────────────
def collect_top_buyers(cfg, per, cal, members, panel):
    start = next(d for d in cal if d > per.base)
    n = cfg["top_buyers"]["count"]
    close = panel["close"]
    out = {}
    for label, investor in (("외국인", "외국인"), ("기관", "기관합계")):
        df = pd.concat([krx.net_buy_ranking(start, per.end, m, investor).assign(시장=m)
                        for m in ("KOSPI", "KOSDAQ")])
        df = df[df.index.isin(members.index)]  # ETF 등 제외, 주식만
        df = df.sort_values("순매수거래대금", ascending=False).head(n)
        rows = []
        for i, (t, r) in enumerate(df.iterrows()):
            chg = None
            if t in close.columns:
                chg = _r((close.at[per.end, t] / close.at[per.base, t] - 1) * 100)
            rows.append({"rank": i + 1, "code": t, "name": r["종목명"], "market": r["시장"],
                         "net_buy": int(round(r["순매수거래대금"] / EOK)), "change_pct": chg})
        out[label] = rows
    return out


# ── 전체 조립 ──────────────────────────────────────────
def build_report(mode: str, run_date: date, cfg: dict, log=print) -> dict:
    log(f"[1/6] 거래일 달력 확인")
    cal = krx.trading_days(run_date - timedelta(days=420), run_date - timedelta(days=1))
    per = P.weekly(run_date, cal, cfg["flows"]["weekly_trend_weeks"]) if mode == "weekly" \
        else P.daily(run_date, cal, cfg["flows"]["daily_trend_days"])
    log(f"      {per.label} ({per.title}) : {per.base} 종가 → {per.end} 종가")

    log("[2/6] 주요 지수")
    indices = collect_indices(cfg, per, run_date, log)
    log("[3/6] 투자자별 수급")
    flows = collect_flows(cfg, per, cal, log)
    log("[4/6] 업종")
    members = krx.sector_members(per.end)
    sectors, sector_pct = collect_sectors(per, members, log)
    log("[5/6] 52주 신고가·신저가")
    highs, lows, panel = collect_highs_lows(cfg, per, cal, members, sector_pct, log)
    log("[6/6] 외국인·기관 순매수 상위")
    top = collect_top_buyers(cfg, per, cal, members, panel)
    log("[+] 나스닥 신고가·급등주")
    us = None
    try:
        from .us import collect_us
        us = collect_us(per, run_date, cfg, log)
    except Exception as e:  # noqa: BLE001  미국 쪽이 실패해도 한국 리포트는 만듦
        log(f"  ! 나스닥 수집 실패: {e}")
    events = None
    if mode == "weekly":
        from .events import upcoming
        log("[+] 앞으로 2주 일정")
        events = upcoming(per.target_end, cfg, log)

    return {
        "mode": mode,
        "label": per.label,
        "title": per.title,
        "period": per.to_dict(),
        "sample": False,
        "generated_at": datetime.now(KST).isoformat(timespec="minutes"),
        "judgment": cfg["judgment"],
        "summary": None,
        "indices": indices,
        "flows": flows,
        "sectors": sectors,
        "highs": highs,
        "lows": lows,
        "top_buyers": top,
        # 9번 신용잔고: 종목별 출처를 확정하면 채웁니다
        "credit": {"unit": "억원", "as_of": per.end.isoformat(), "stocks": [],
                   "market_trend": None, "source_pending": True},
        "us": us,
        "events": events,
        "news": None,
    }
