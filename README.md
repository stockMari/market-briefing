# Market Briefing (마켓 브리핑)

매일 아침과 매주 토요일에 시장 데이터를 모아 웹페이지로 만드는 프로그램입니다.

## 직접 고치는 파일은 두 개뿐

| 파일 | 내용 |
|---|---|
| `config.yaml` | 지수 목록, 신고가 판정 기준(5%p 등), 텔레그램 채널, 블로그 주소 |
| `.env` (내 컴퓨터에서 돌릴 때만) | 비밀번호류. `.env.example`을 복사해서 만듭니다 |

GitHub에서 돌릴 때는 `.env` 대신 **Settings → Secrets and variables → Actions**에 같은 이름으로 넣습니다.

## 실행

```bash
python run.py --mode weekly          # 이번 주 리포트
python run.py --mode daily           # 오늘 리포트
python run.py --mode weekly --sample # 샘플 숫자로 화면만 확인
```

GitHub에서는 **Actions → Market Briefing → Run workflow** 버튼으로 실행합니다.

## 폴더

```
run.py              실행 파일
config.yaml         설정
briefing/           데이터 수집·판정·페이지 생성 코드
templates/          웹페이지 디자인
site/               완성된 웹사이트 (index.html, weekly/, daily/, data/)
cache/              1년치 시세 저장 (52주 신고가 계산용, GitHub에 올리지 않음)
```

## 진행 상황

- [x] 1단계 설계
- [x] 2단계 Weekly 페이지 (1~6번)
- [x] 3단계 Daily
- [ ] 4단계 텔레그램·블로그 (보류)
- [x] 5단계 Claude 요약 (Secrets 에 ANTHROPIC_API_KEY 필요)
- [x] 6단계 자동 실행 (평일 07:10, 토 08:40 KST 시작 · 저장소 공개 시 웹사이트 자동 배포)
- [ ] 9번 신용잔고 — 종목별 데이터 출처 확정 필요
