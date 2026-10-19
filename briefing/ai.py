"""7번: Claude 가 리포트 숫자를 읽고 시장 요약 3줄을 씁니다.

API 키(ANTHROPIC_API_KEY)가 없거나 호출이 실패해도 리포트는 그대로 만들어집니다.
요약 자리만 비어 있게 됩니다.
"""
import json
import os
from collections import Counter

import anthropic
from pydantic import BaseModel

SYSTEM = """너는 한국 주식시장 아침 브리핑의 편집자다.
주어진 데이터만 근거로 시장 요약을 정확히 3줄 쓴다.

- 1줄: 지수 흐름 (국내 + 해외 중 눈에 띄는 것)
- 2줄: 투자자 수급 (외국인·기관의 방향과 규모)
- 3줄: 업종·종목 특징 (강세/약세 업종, 52주 신고가가 몰린 곳, 외국인·기관 동반 매수 종목 등)

각 줄은 한 문장, 60자 안팎. 숫자는 데이터에 있는 값을 반올림해 쓰고, 데이터에 없는 사실·원인·전망·투자 권유는 쓰지 않는다.
문체는 신문 시황 기사처럼 간결하게 끝낸다. (예: "KOSPI 2.1% 반등, 나스닥은 2.2% 하락")"""


class Summary(BaseModel):
    lines: list[str]


def digest(r: dict) -> dict:
    """요약에 필요한 숫자만 간추립니다 (토큰 절약)."""
    def top(rows, n):
        return [(x["name"], x["change_pct"]) for x in rows[:n]]

    tb = r["top_buyers"]
    both = [x["name"] for x in tb["외국인"] if x["code"] in {y["code"] for y in tb["기관"]}]
    trend = r["flows"]["trend"]
    return {
        "기간": {"구분": r["mode"], "제목": r["title"], "비교": f'{r["period"]["base"]} 종가 → {r["period"]["end"]} 종가',
               "휴장": r["period"].get("notes", [])},
        "지수_등락률": {i["name"]: i["change_pct"] for i in r["indices"] if i["change_pct"] is not None},
        "순매수_억원": r["flows"]["current"],
        "순매수_누적_추이기간_억원": {m: {k: sum(v) for k, v in trend[m].items()} for m in ("KOSPI", "KOSDAQ")},
        "추이기간": f'{trend["labels"][0]}~{trend["labels"][-1]}',
        "업종_상위": {m: top(rows, 5) for m, rows in r["sectors"].items()},
        "업종_하위": {m: top(rows[::-1], 5) for m, rows in r["sectors"].items()},
        "52주신고가": {"종목수": len(r["highs"]),
                    "섹터별": Counter(h["sector"] for h in r["highs"]).most_common(5),
                    "판정별": Counter(h["verdict"] for h in r["highs"]).most_common(),
                    "등락률상위": [(h["name"], h["change_pct"], h["verdict"])
                              for h in sorted(r["highs"], key=lambda h: -h["change_pct"])[:5]]},
        "52주신저가": {"종목수": len(r["lows"]),
                    "섹터별": Counter(h["sector"] for h in r["lows"]).most_common(5)},
        "외국인_순매수상위_억원": [(x["name"], x["net_buy"]) for x in tb["외국인"][:5]],
        "기관_순매수상위_억원": [(x["name"], x["net_buy"]) for x in tb["기관"][:5]],
        "외국인기관_동반순매수": both,
    }


def summarize(report: dict, cfg: dict, log=print) -> list[str] | None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        log("  · ANTHROPIC_API_KEY 가 없어 AI 요약은 건너뜁니다")
        return None
    ai = cfg.get("ai", {})
    client = anthropic.Anthropic()
    data = json.dumps(digest(report), ensure_ascii=False)
    try:
        resp = client.beta.messages.parse(
            model=ai.get("model", "claude-opus-5-5"),
            max_tokens=16000,
            # 안전 필터가 거절하면 서버가 알아서 다른 모델로 다시 시도
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": ai.get("effort", "medium")},
            system=SYSTEM,
            messages=[{"role": "user", "content": f"다음 데이터로 3줄 요약을 써 줘.\n\n{data}"}],
            output_format=Summary,
        )
    except anthropic.AuthenticationError:
        log("  ! AI 요약 실패: API 키가 올바르지 않습니다")
        return None
    except anthropic.RateLimitError:
        log("  ! AI 요약 실패: 사용량 한도 초과 (잠시 후 다시)")
        return None
    except anthropic.APIStatusError as e:
        log(f"  ! AI 요약 실패: {e.status_code} {e.message}")
        return None
    except anthropic.APIConnectionError:
        log("  ! AI 요약 실패: 네트워크 연결 오류")
        return None

    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        log(f"  ! AI 요약을 받지 못했습니다 (stop_reason={resp.stop_reason})")
        return None
    lines = [s.strip() for s in resp.parsed_output.lines if s.strip()][:3]
    log(f"  · AI 요약 완료 ({resp.model}, 입력 {resp.usage.input_tokens} / 출력 {resp.usage.output_tokens} 토큰)")
    return lines or None
