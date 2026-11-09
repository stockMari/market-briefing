"""국내 실적 페이지 (OpenDART).

- 잠정실적: '연결재무제표기준영업(잠정)실적', '영업(잠정)실적' 공정공시 원문에서
  매출액·영업이익·순이익과 전기/전년동기 대비 증감률을 읽어 옴
- 실적발표 예정: '기업설명회(IR)개최' 공시의 일시·내용
- 공시 원문은 접수번호별로 cache/dart 에 저장해 다시 받지 않음
"""
import html
import io
import re
import zipfile
from datetime import date, datetime, timedelta, timezone

from .buyback import MARKET, VIEW, _cached, _ymd, dart, filings

KST = timezone(timedelta(hours=9))
ROWS = [("sales", r"매출액"), ("op", r"영업이익"), ("net", r"(?<!지배기업 소유주지분 )당기순이익"),
        ("ctrl", r"지배기업\s*소유주\s*지분\s*순이익")]
UNIT = {"원": 1e-8, "천원": 1e-5, "백만원": 1e-2, "억원": 1.0}


def _document_text(rcept_no: str) -> str:
    import requests
    import os

    def fetch():
        r = requests.get("https://opendart.fss.or.kr/api/document.xml",
                         params={"crtfc_key": os.environ["DART_API_KEY"].strip(), "rcept_no": rcept_no}, timeout=60)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        raw = z.read(z.namelist()[0]).decode("utf-8", errors="ignore")
        t = html.unescape(re.sub(r"<[^>]+>", " ", raw))
        return {"text": re.sub(r"\s+", " ", t)}
    return html.unescape(_cached(f"doc_{rcept_no}", fetch)["text"])


def _num(s: str):
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_results(text: str) -> dict | None:
    """잠정실적 공시 원문 → 숫자 (억원)."""
    m = re.search(r"단위\s*:\s*(원|천원|백만원|억원)", text)
    if not m:
        return None
    mult = UNIT[m[1]]
    q = re.search(r"\((\d{4})년\s*(\d)분기\)", text)
    if q:
        period = f"{q[1][2:]}년 {q[2]}Q"
    else:   # '당기실적 2026-07-01 ~ 2026-09-30' 에서 분기 계산
        d = re.search(r"당기실적\s+(\d{4})-(\d{2})-\d{2}\s*~\s*\d{4}-(\d{2})", text)
        period = f"{d[1][2:]}년 {(int(d[3]) - 1) // 3 + 1}Q" if d else ""
    out = {"period": period, "unit_src": m[1]}
    body = text[m.end():]
    for key, label in ROWS:
        # 라벨 당해실적 [당기] [전기] [전기대비%] [흑적전환] [전년동기] [전년비%] [흑적전환]
        r = re.search(label + r"[^당]{0,20}당해실적\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", body)
        if not r:
            continue
        cur, prev, qoq, qflag, yago, yoy, yflag = r.groups()
        val = lambda x: None if _num(x) is None else round(_num(x) * mult, 1)  # noqa: E731
        out[key] = {"cur": val(cur), "prev_q": val(prev), "qoq": _num(qoq), "yago": val(yago), "yoy": _num(yoy),
                    "yflag": "" if yflag in ("-", "") else yflag,     # 전년동기 대비 흑자/적자 전환
                    "qflag": "" if qflag in ("-", "") else qflag}     # 직전 분기 대비
    return out if "op" in out or "sales" in out else None


def _ir_events(rows: list[dict], run_date: date, days: int, log) -> list[dict]:
    out, seen = [], set()
    for f in sorted(rows, key=lambda f: f["rcept_no"], reverse=True):
        try:
            t = _document_text(f["rcept_no"])
        except Exception as e:  # noqa: BLE001
            log(f"  · {f['corp_name']} IR 공시 읽기 실패: {e}")
            continue
        m = re.search(r"일시\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?", t)
        if not m:
            continue
        d = date.fromisoformat(m[1])
        about = re.search(r"주요\s*설명회\s*내용\s*\(요약\)\s+(.+?)\s+\d+\.\s", t)
        about = about[1].strip() if about else ""
        how = re.search(r"개최방법\s+(.+?)\s+\d+\.\s", t)
        key = (f["corp_code"], d)
        if not (run_date - timedelta(days=1) <= d <= run_date + timedelta(days=days)) or key in seen:
            continue
        seen.add(key)
        out.append({"date": d.isoformat(), "time": m[2] or "", "name": f["corp_name"], "code": f["stock_code"],
                    "market": MARKET.get(f.get("corp_cls"), "기타"), "about": about[:60],
                    "how": (how[1].strip()[:30] if how else ""), "earnings": bool(re.search(r"실적|분기|결산", about)),
                    "url": VIEW + f["rcept_no"]})
    return sorted(out, key=lambda e: (e["date"], e["time"] or "99"))


def collect_kr_earnings(run_date: date, cfg: dict, log=print) -> dict:
    kc = cfg.get("kr_earnings", {})
    look = kc.get("lookback_days", 14)
    start = run_date - timedelta(days=look)

    raw = filings(start, run_date, "I002", log)
    picks = {}
    for f in sorted(raw, key=lambda f: f["rcept_no"]):
        n = f["report_nm"]
        if "잠정" in n and "실적" in n and f.get("stock_code") and "첨부" not in n and "자회사" not in n:
            picks[f["corp_code"]] = f       # 정정 공시가 있으면 최신 것으로
    results = []
    for f in picks.values():
        try:
            text = _document_text(f["rcept_no"])
            p = parse_results(text)
        except Exception as e:  # noqa: BLE001
            log(f"  · {f['corp_name']} 실적 공시 읽기 실패: {e}")
            continue
        if not p:
            continue
        results.append({**p, "name": f["corp_name"], "code": f["stock_code"],
                        "market": MARKET.get(f.get("corp_cls"), "기타"), "date": _ymd(f["rcept_dt"]).isoformat(),
                        "consolidated": "연결" in f["report_nm"] or "연결실적" in text, "url": VIEW + f["rcept_no"]})
    log(f"  · 잠정실적 {len(results)}건 ({start}~{run_date})")

    _add_caps(results, run_date, log)
    for r in results:
        op, sales = r.get("op") or {}, r.get("sales") or {}
        r["op_margin"] = round(op["cur"] / sales["cur"] * 100, 1) if op.get("cur") is not None and sales.get("cur") else None
    results.sort(key=lambda r: r["date"], reverse=True)
    results.sort(key=lambda r: -(r.get("mcap_eok") or 0))   # 시총 큰 순 (같으면 최근 발표 먼저)

    ir_rows = [f for ty in ("I001", "I003") for f in filings(run_date - timedelta(days=30), run_date, ty, log)
               if "기업설명회" in f["report_nm"] and f.get("stock_code")]
    events = _ir_events(ir_rows, run_date, kc.get("ahead_days", 14), log)
    log(f"  · IR 일정 {len(events)}건")

    week_cut = (run_date - timedelta(days=7)).isoformat()
    recent = [r for r in results if r["date"] >= week_cut]
    def op_of(r): return (r.get("op") or {})
    return {
        "as_of": run_date.isoformat(), "lookback_days": look,
        "generated_at": datetime.now(KST).isoformat(timespec="minutes"),
        "results": results, "events": events,
        "stats": {
            "week": len(recent),
            "op_up": sum((op_of(r).get("yoy") or 0) > 0 or op_of(r).get("yflag") == "흑자전환" for r in recent),
            "op_down": sum((op_of(r).get("yoy") or 0) < 0 or op_of(r).get("yflag") in ("적자전환", "적자지속") for r in recent),
            "turnaround": sum(op_of(r).get("yflag") == "흑자전환" for r in recent),
            "ir_upcoming": sum(e["date"] >= run_date.isoformat() for e in events),
        },
    }


def _add_caps(results: list[dict], run_date: date, log):
    """시가총액 (KRX). 접속이 안 되면 비워 둠."""
    try:
        import pandas as pd
        from pykrx import stock
        from .krx import call, ymd, trading_days
        last = trading_days(run_date - timedelta(days=14), run_date - timedelta(days=1))[-1]
        caps = pd.concat([call(stock.get_market_cap, ymd(last), market=m) for m in ("KOSPI", "KOSDAQ")])
        for r in results:
            if r["code"] in caps.index:
                r["mcap_eok"] = round(float(caps.at[r["code"], "시가총액"]) / 1e8)
    except Exception as e:  # noqa: BLE001
        log(f"  · 시가총액 생략 (KRX 연결 안 됨): {str(e)[:80]}")
