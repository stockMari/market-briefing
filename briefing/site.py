"""모은 데이터를 웹페이지로 만듭니다.

site/
├── index.html              첫 화면 (가장 최근 리포트)
├── weekly/2026-W42.html
├── daily/2026-10-16.html
└── data/weekly/2026-W42.json   리포트 원본 숫자 (지난 리포트 목록도 여기서 만듦)
"""
import json
from collections import defaultdict
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .config import ROOT
from .judge import HIGH_VERDICTS, LOW_VERDICTS

MODES = ("daily", "weekly")


# ── 숫자 표시 형식 ─────────────────────────────────────────
def f_num(v, digits=0):
    return "–" if v is None else f"{v:,.{digits}f}"


def f_signed(v, digits=0):
    return "–" if v is None else f"{v:+,.{digits}f}"


def f_pct(v, digits=2):
    return "–" if v is None else f"{v:+.{digits}f}%"


def f_pp(v, digits=1):
    return "–" if v is None else f"{v:+.{digits}f}%p"


def f_sign(v):
    if v is None or abs(v) < 1e-9:
        return "flat"
    return "up" if v > 0 else "down"


def f_md(iso):
    y, m, d = iso.split("-")
    return f"{int(m)}/{int(d)}"


def f_spark(vals, w=96, h=26):
    """최근 주가 흐름 미니 그래프 (SVG)."""
    v = [x for x in vals or [] if x is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    span = hi - lo or 1
    pts = [(2 + i * (w - 4) / (len(v) - 1), h - 2 - (x - lo) / span * (h - 4)) for i, x in enumerate(v)]
    color = "var(--up-fill)" if v[-1] >= v[0] else "var(--down-fill)"
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    pct = (v[-1] / v[0] - 1) * 100
    return Markup(
        f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
        f'aria-label="최근 {len(v)}거래일 {pct:+.1f}%"><title>최근 {len(v)}거래일 {pct:+.1f}%</title>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>'
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.2" fill="{color}"/></svg>')


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html"]))
    env.filters.update(num=f_num, signed=f_signed, pct=f_pct, pp=f_pp, sign=f_sign, md=f_md, spark=f_spark)
    return env


# ── 화면용으로 데이터 정리 ────────────────────────────────
def group_by_sector(rows: list[dict], verdict_names: dict) -> list[dict]:
    """신고가/신저가 종목을 섹터별로 묶고, 종목 수가 많은 섹터부터 정렬."""
    groups = defaultdict(list)
    for r in rows:
        groups[r["sector"]].append(r)
    out = []
    for sector, items in groups.items():
        items.sort(key=lambda r: r["change_pct"], reverse=True)
        counts = {k: sum(1 for r in items if r["kind"] == k) for k in verdict_names}
        rates = {}
        for r in items:
            rates.setdefault(r["market"], (r["sector_change_pct"], r.get("sector_estimated", False)))
        out.append({"sector": sector, "stocks": items, "counts": counts, "rates": rates})
    out.sort(key=lambda g: (-len(g["stocks"]), g["sector"]))
    return out


def build_view(report: dict) -> dict:
    tb = report["top_buyers"]
    both = {r["code"] for r in tb["외국인"]} & {r["code"] for r in tb["기관"]}
    return {
        "high_groups": group_by_sector(report["highs"], HIGH_VERDICTS),
        "low_groups": group_by_sector(report["lows"], LOW_VERDICTS),
        "high_verdicts": HIGH_VERDICTS,
        "low_verdicts": LOW_VERDICTS,
        "both_codes": both,
        "both_names": [r["name"] for r in tb["외국인"] if r["code"] in both],
        "indices_by_region": _by_region(report["indices"]),
        "us_high_groups": _us_groups(report.get("us")),
    }


def _us_groups(us):
    if not us:
        return []
    groups = {name: [] for name, _ in us["high_sectors"]}
    for r in us["highs"]:
        groups.setdefault(r["sector"], []).append(r)
    return [{"sector": k, "stocks": v} for k, v in groups.items() if v]


def _by_region(indices):
    regions = []
    for ix in indices:
        if not regions or regions[-1][0] != ix["region"]:
            regions.append((ix["region"], []))
        regions[-1][1].append(ix)
    return regions


# ── 저장 · 목록 · 페이지 생성 ─────────────────────────────
def save_report(report: dict, site_dir: Path) -> Path:
    path = site_dir / "data" / report["mode"] / f"{report['label']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_reports(site_dir: Path) -> dict[str, list[dict]]:
    reports = {m: [] for m in MODES}
    for m in MODES:
        for p in sorted((site_dir / "data" / m).glob("*.json"), reverse=True):
            reports[m].append(json.loads(p.read_text(encoding="utf-8")))
    return reports


def manifest(reports: dict[str, list[dict]]) -> dict[str, list[dict]]:
    out = {}
    for m, items in reports.items():
        out[m] = []
        for r in items:
            kospi = next((i for i in r["indices"] if i["name"] == "KOSPI"), None)
            out[m].append({
                "label": r["label"], "title": r["title"],
                "base": r["period"]["base"], "end": r["period"]["end"],
                "kospi_pct": kospi["change_pct"] if kospi else None,
                "highs": len(r["highs"]), "sample": r.get("sample", False),
            })
    return out


def render_page(report: dict, man: dict, root: str, standalone: bool = True) -> str:
    tpl = _env().get_template("report.html")
    return tpl.render(r=report, v=build_view(report), manifest=man, root=root,
                      standalone=standalone, chart_data=json.dumps(_chart_payload(report), ensure_ascii=False).replace("</", "<\\/"))


def _chart_payload(report: dict) -> dict:
    """그래프 그리기에 필요한 숫자만 페이지에 넣습니다."""
    return {
        "mode": report["mode"],
        "unit": "주" if report["mode"] == "weekly" else "일",
        "indices": [i for i in report["indices"] if i["change_pct"] is not None],
        "flows": report["flows"],
        "sectors": report["sectors"],
        "highGroups": [{"sector": g["sector"], "counts": g["counts"]}
                       for g in group_by_sector(report["highs"], HIGH_VERDICTS)],
        "lowGroups": [{"sector": g["sector"], "counts": g["counts"]}
                      for g in group_by_sector(report["lows"], LOW_VERDICTS)],
        "highVerdicts": HIGH_VERDICTS,
        "lowVerdicts": LOW_VERDICTS,
        "creditTrend": report["credit"]["market_trend"],
        "usGainers": [{"ticker": g["ticker"], "name": g["name"], "pct": g["change_pct"], "high": g["is_high"]}
                      for g in (report.get("us") or {}).get("gainers", [])],
        "usHighSectors": (report.get("us") or {}).get("high_sectors", []),
    }


def build_site(site_dir: Path, preview_path: Path | None = None) -> list[Path]:
    """data/ 에 쌓인 모든 리포트로 페이지를 다시 만듭니다 (지난 리포트 목록이 항상 최신이 되도록)."""
    reports = load_reports(site_dir)
    man = manifest(reports)
    written = []
    for m, items in reports.items():
        for r in items:
            out = site_dir / m / f"{r['label']}.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(render_page(r, man, root="../"), encoding="utf-8")
            written.append(out)
    # 첫 화면: Daily가 있으면 최신 Daily, 없으면 최신 Weekly
    home = (reports["daily"] or reports["weekly"] or [None])[0]
    if home:
        (site_dir / "index.html").write_text(render_page(home, man, root=""), encoding="utf-8")
        written.append(site_dir / "index.html")
        if preview_path:
            preview_path.write_text(render_page(home, man, root="", standalone=False), encoding="utf-8")
    return written
