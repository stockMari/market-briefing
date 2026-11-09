"""자사주 스크리닝 (OpenDART 공시 + KRX 기타법인 수급).

- 자기주식 취득결정(직접) / 신탁계약 체결결정 → 진행 중인 매입 목록
- 진행 정도 추정: 회사가 장내에서 직접 사면 거래소 통계상 '기타법인' 매수로 잡힘
  → 매입 기간 동안 그 종목의 기타법인 누적 순매수 ÷ 매입 예정 주식 수
  (다른 법인 매매도 섞이고, 신탁 매입은 증권사 쪽으로 잡힐 수 있어 '추정치')
- 결과보고서·신탁 해지 공시로 완료 여부 표시, 소각·처분 결정은 따로 목록
"""
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

KST = timezone(timedelta(hours=9))
API = "https://opendart.fss.or.kr/api/"
VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo="
MARKET = {"Y": "KOSPI", "K": "KOSDAQ"}


def dart(path: str, **params) -> dict:
    params["crtfc_key"] = os.environ["DART_API_KEY"].strip()
    for i in range(3):
        try:
            d = requests.get(API + path, params=params, timeout=30).json()
            if d.get("status") in ("000", "013"):   # 013 = 데이터 없음
                return d
            if d.get("status") == "020":
                raise RuntimeError("DART 하루 조회 한도 초과")
            raise RuntimeError(f"DART 오류 {d.get('status')}: {d.get('message')}")
        except requests.RequestException:
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"DART 접속 실패: {path}")


CACHE = Path(__file__).resolve().parent.parent / "cache" / "dart"


def _cached(name: str, fetch):
    """지난 공시는 바뀌지 않으므로 한 번 받은 결과를 cache/dart 에 보관."""
    path = CACHE / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def _list_range(s: date, e: date, ty: str) -> list[dict]:
    out, page = [], 1
    while True:
        d = dart("list.json", pblntf_detail_ty=ty, bgn_de=f"{s:%Y%m%d}", end_de=f"{e:%Y%m%d}",
                 page_no=page, page_count=100)
        out += d.get("list", [])
        if page >= int(d.get("total_page", 1) or 1):
            return out
        page += 1
        time.sleep(0.2)


def filings(start: date, end: date, ty: str, log) -> list[dict]:
    """전 시장 공시 목록. ty: 공시 상세유형 (B001 주요사항보고서, E001 자기주식 결과보고서,
    E002 신탁 보고서, I001 수시공시). 한 달 단위로 받고, 일주일 넘게 지난 달은 저장해 둔 것을 씀."""
    out, s = [], date(start.year, start.month, 1)
    while s <= end:
        nxt = date(s.year + (s.month == 12), s.month % 12 + 1, 1)
        e = min(nxt - timedelta(days=1), end)
        fetch = lambda s=s, e=e: _list_range(s, e, ty)  # noqa: E731
        rows = _cached(f"list_{ty}_{s:%Y%m}", fetch) if e < end - timedelta(days=7) else fetch()
        out += [r for r in rows if start <= _ymd(r["rcept_dt"]) <= end]
        s = nxt
    return out


def _ymd(t: str) -> date:
    return date(int(t[:4]), int(t[4:6]), int(t[6:8]))


def _date(txt: str) -> date | None:
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})", txt or "")
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def _num(txt) -> float | None:
    t = re.sub(r"[^\d.]", "", str(txt or ""))
    return float(t) if t else None


def _kind(name: str) -> str | None:
    if "자기주식취득신탁계약해지" in name:
        return "trust_end"
    if "자기주식취득신탁계약체결" in name:
        return "trust"
    if "자기주식취득결정" in name:
        return "direct"
    if "자기주식처분결정" in name:
        return "dispose"
    if "주식소각결정" in name:
        return "cancel"
    if "자기주식취득결과보고서" in name or "신탁계약해지결과보고서" in name:
        return "done"
    return None


def collect_buybacks(run_date: date, cfg: dict, log=print) -> dict:
    bc = cfg.get("buyback", {})
    look = bc.get("lookback_days", 180)
    start, end = run_date - timedelta(days=look), run_date
    raw = []
    for ty in ("B001", "E001", "E002"):
        raw += filings(start, end, ty, log)
    # 소각결정은 거래소 수시공시(양이 많음)라 최근 기간만
    raw += filings(run_date - timedelta(days=bc.get("cancel_days", 60)), end, "I001", log)
    rows = []
    for f in raw:
        k = _kind(f["report_nm"])
        if k and f.get("stock_code") and "자회사" not in f["report_nm"]:
            rows.append({**f, "kind": k, "fixed": "정정" in f["report_nm"]})
    log(f"  · 자사주 관련 공시 {len(rows)}건 ({start}~{end})")

    # 취득결정·신탁체결: 회사별 상세 (정정 공시가 있으면 최신 것이 반영됨)
    targets = {}
    for f in sorted(rows, key=lambda f: f["rcept_no"]):
        if f["kind"] in ("direct", "trust"):
            targets[(f["corp_code"], f["kind"])] = f
    plans = []
    for (corp, kind), f in targets.items():
        api = "tsstkAqDecsn.json" if kind == "direct" else "tsstkAqTrctrCnsDecsn.json"
        # 공시 상세는 접수번호별로 저장 (같은 공시를 다시 받지 않음)
        try:
            items = _cached(f"{api.split('.')[0]}_{f['rcept_no']}", lambda: dart(
                api, corp_code=corp, bgn_de=f["rcept_dt"], end_de=f["rcept_dt"]).get("list", []))
        except RuntimeError as e:
            log(f"  ! {f['corp_name']} 상세 실패: {e}")
            continue
        for it in items:
            if kind == "direct":
                bgn, edd = _date(it.get("aqexpd_bgd")), _date(it.get("aqexpd_edd"))
                shares, amount = _num(it.get("aqpln_stk_ostk")), _num(it.get("aqpln_prc_ostk"))
                how, why = it.get("aq_mth", ""), it.get("aq_pp", "")
            else:
                bgn, edd = _date(it.get("ctr_pd_bgd")), _date(it.get("ctr_pd_edd"))
                shares, amount = None, _num(it.get("ctr_prc"))
                how, why = f"신탁계약 ({it.get('ctr_cns_int', '')})", it.get("ctr_pp", "")
            if not bgn or not edd:
                continue
            plans.append({"corp_code": corp, "name": f["corp_name"], "code": f["stock_code"],
                          "market": MARKET.get(f.get("corp_cls"), "기타"), "kind": kind,
                          "rcept_no": it.get("rcept_no", f["rcept_no"]),
                          "decided": f"{f['rcept_dt'][:4]}-{f['rcept_dt'][4:6]}-{f['rcept_dt'][6:]}",
                          "start": bgn.isoformat(), "end": edd.isoformat(),
                          "shares": shares, "amount": amount, "how": how.strip(), "why": why.strip()})
    # 같은 공시가 정정으로 여러 번 오면 접수번호 기준 최신 하나만
    dedup = {}
    for p in sorted(plans, key=lambda p: p["rcept_no"]):
        dedup[(p["corp_code"], p["kind"], p["start"])] = p
    plans = list(dedup.values())

    # 완료·해지 표시
    for p in plans:
        late = [f for f in rows if f["corp_code"] == p["corp_code"] and f["kind"] in ("done", "trust_end")
                and f["rcept_dt"] >= p["decided"].replace("-", "")]
        if p["kind"] == "trust" and any(f["kind"] == "trust_end" for f in late):
            p["status"] = "해지"
        elif p["kind"] == "direct" and any(f["kind"] == "done" for f in late):
            p["status"] = "완료"
        elif date.fromisoformat(p["end"]) < run_date:
            p["status"] = "기간 종료"
        elif date.fromisoformat(p["start"]) > run_date:
            p["status"] = "시작 전"
        else:
            p["status"] = "진행 중"

    add_progress(plans, run_date, log)
    for p in plans:   # 값을 못 구한 칸은 화면에 '–'로
        for k in ("cap_pct", "time_pct", "progress_pct", "other_corp_net", "price_chg", "shares_est"):
            p.setdefault(k, None)

    def simple(kind):
        out = []
        for f in sorted((f for f in rows if f["kind"] == kind and not f["fixed"]), key=lambda f: f["rcept_no"], reverse=True):
            out.append({"name": f["corp_name"], "code": f["stock_code"], "market": MARKET.get(f.get("corp_cls"), "기타"),
                        "date": f"{f['rcept_dt'][:4]}-{f['rcept_dt'][4:6]}-{f['rcept_dt'][6:]}",
                        "url": VIEW + f["rcept_no"]})
        return out[: bc.get("max_list", 40)]

    plans.sort(key=lambda p: ({"진행 중": 0, "시작 전": 1, "완료": 2, "기간 종료": 2, "해지": 3}[p["status"]],
                              -(p.get("cap_pct") or 0)))
    for p in plans:
        p["url"] = VIEW + p["rcept_no"]
    new_cut = (run_date - timedelta(days=14)).isoformat()
    return {
        "as_of": run_date.isoformat(), "lookback_days": look,
        "generated_at": datetime.now(KST).isoformat(timespec="minutes"),
        "plans": plans,
        "cancels": simple("cancel"), "disposals": simple("dispose"),
        "stats": {
            "active": sum(p["status"] == "진행 중" for p in plans),
            "active_amount": sum((p["amount"] or 0) for p in plans if p["status"] == "진행 중"),
            "new_2w": sum(p["decided"] >= new_cut for p in plans),
            "cancels_2w": sum(c["date"] >= new_cut for c in simple("cancel")),
        },
    }


def add_progress(plans: list[dict], run_date: date, log):
    """KRX 기타법인 순매수로 매입 진행 정도 추정 + 시총 대비 규모, 결정 후 주가 변화."""
    try:
        from pykrx import stock
        from .krx import call, ymd, trading_days
        last = trading_days(run_date - timedelta(days=14), run_date - timedelta(days=1))[-1]
        caps = pd.concat([call(stock.get_market_cap, ymd(last), market=m) for m in ("KOSPI", "KOSDAQ")])
    except Exception as e:  # noqa: BLE001
        log(f"  ! KRX 연결 실패 (진행률 추정 생략): {e}")
        return
    n_ok = 0
    for p in plans:
        if p["status"] in ("시작 전",):
            continue
        cap = caps.loc[p["code"]] if p["code"] in caps.index else None
        price = float(cap["종가"]) if cap is not None and cap["종가"] else None
        if cap is not None and p["amount"]:
            p["cap_pct"] = round(p["amount"] / float(cap["시가총액"]) * 100, 2)
        if p["shares"] is None and p["amount"] and price:
            p["shares_est"] = int(p["amount"] / price)   # 신탁: 계약금액 ÷ 현재가
        s, e = date.fromisoformat(p["start"]), min(date.fromisoformat(p["end"]), last)
        total = (date.fromisoformat(p["end"]) - s).days or 1
        p["time_pct"] = round(min(max((min(run_date, date.fromisoformat(p["end"])) - s).days / total, 0), 1) * 100)
        if e < s:
            continue
        try:
            vol = call(stock.get_market_trading_volume_by_date, ymd(s), ymd(e), p["code"])
            px = call(stock.get_market_ohlcv, ymd(s - timedelta(days=7)), ymd(e), p["code"])
        except Exception as ex:  # noqa: BLE001
            log(f"  · {p['name']} 수급 조회 실패: {ex}")
            continue
        if vol.empty or "기타법인" not in vol.columns:
            continue
        cum = vol["기타법인"].cumsum()
        planned = p["shares"] or p.get("shares_est")
        p["other_corp_net"] = int(cum.iloc[-1])
        p["other_corp_curve"] = [int(v) for v in cum.tolist()]
        if planned:
            p["progress_pct"] = round(max(cum.iloc[-1], 0) / planned * 100, 1)
        if not px.empty:
            before = px[px.index < pd.Timestamp(s)]["종가"]
            base = float(before.iloc[-1]) if len(before) else float(px["종가"].iloc[0])
            p["price_chg"] = round((float(px["종가"].iloc[-1]) / base - 1) * 100, 2)
        n_ok += 1
    log(f"  · 기타법인 수급으로 진행률 추정 {n_ok}건")
