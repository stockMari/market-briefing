# Market Briefing — 작업 안내 (Claude용)

사용자는 코딩을 잘 모름. 설명은 짧고 쉬운 한국어로.

## "데일리 갱신해줘" / "위클리 갱신해줘" 같은 요청
데이터 수집은 이 작업 공간이 아니라 **GitHub Actions** 에서 돌린다 (여기서는 KRX 접속이 막혀 있음).

```bash
git pull -q origin main
# mode: daily / weekly / earnings / buyback / rebuild,  date: 비우면 오늘 (YYYY-MM-DD)
gh api -X POST repos/stockMari/market-briefing/actions/workflows/briefing.yml/dispatches \
  -f ref=main -f 'inputs[mode]=daily' -f 'inputs[date]='
# 최신 실행이 끝날 때까지 기다린 뒤 결과 확인
RID=$(gh api "repos/stockMari/market-briefing/actions/runs?per_page=1" --jq '.workflow_runs[0].id')
gh api repos/stockMari/market-briefing/actions/runs/$RID --jq '.status + " " + (.conclusion // "")'
git pull -q origin main && tail -20 logs/last-run.log     # 실행 기록 (Actions 로그는 직접 못 읽음)
```
끝나면 `site/data/daily/<날짜>.json` 의 `summary` 3줄과 주요 숫자를 짧게 알려주고
웹사이트 주소 https://stockmari.github.io/market-briefing/ 를 준다.

## 구조
- `run.py` 실행 파일, `config.yaml` 설정, `calendar.yaml` 일정, `briefing/` 코드, `templates/` 화면
- `site/` 결과물 (GitHub Pages 로 배포), `cache/` 는 Actions 캐시
- 비밀값은 GitHub Secrets: KRX_ID, KRX_PW, (DART_API_KEY), (ANTHROPIC_API_KEY)
- 자동 실행: 평일 06:50 KST Daily, 토 08:20 KST Weekly
