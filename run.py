"""마켓 브리핑 실행 파일.

사용법
  python run.py --mode weekly            이번 주 리포트 만들기
  python run.py --mode daily             오늘 리포트 만들기
  python run.py --mode weekly --sample   샘플 숫자로 디자인만 확인
  python run.py --mode weekly --date 2026-10-17   특정 날짜에 실행한 것처럼 만들기
  python run.py --rebuild                저장된 숫자로 페이지만 다시 만들기
"""
import argparse
from datetime import date, datetime, timedelta, timezone

from briefing.config import ROOT, load_config
from briefing.site import build_site, save_report

KST = timezone(timedelta(hours=9))


def main():
    ap = argparse.ArgumentParser(description="마켓 브리핑 만들기")
    ap.add_argument("--mode", choices=["daily", "weekly"])
    ap.add_argument("--date", help="실행일 (YYYY-MM-DD). 비우면 오늘")
    ap.add_argument("--sample", action="store_true", help="샘플 데이터로 만들기")
    ap.add_argument("--preview", help="미리보기용 HTML 저장 경로")
    ap.add_argument("--rebuild", action="store_true", help="데이터 수집 없이 페이지만 다시 만들기")
    args = ap.parse_args()
    if not args.rebuild and not args.mode:
        ap.error("--mode daily 또는 --mode weekly 를 지정해 주세요")

    cfg = load_config()
    run_date = date.fromisoformat(args.date) if args.date else datetime.now(KST).date()
    site_dir = ROOT / cfg["site"]["output_dir"]

    if args.rebuild:
        pages = build_site(site_dir, preview_path=args.preview and ROOT / args.preview)
        print(f"[완료] 페이지 {len(pages)}개 다시 생성")
        return
    if args.sample:
        from briefing.sample import build_sample
        report = build_sample(args.mode, run_date, cfg)
    else:
        from briefing.collect import build_report
        report = build_report(args.mode, run_date, cfg)

    save_report(report, site_dir)
    pages = build_site(site_dir, preview_path=args.preview and ROOT / args.preview)
    print(f"[완료] {report['mode']} {report['label']} ({report['title']}) · 페이지 {len(pages)}개 생성")


if __name__ == "__main__":
    main()
