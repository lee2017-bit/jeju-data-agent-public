"""질문 해석 정확도 실측: 규칙만 vs AI(gpt-6-luna). 규칙만으로는 놓치는 일상 표현이 들어간 15문항.

    python tools/bench_parse.py            → docs/submission/results/parse_bench.json
채점: 최종 슬롯(동네·업종·대상·관점)이 기대값을 모두 포함하면 '완전 정답'. AI는 키가 있을 때만 잰다(15문항 약 $0.002).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jeju_agent import llm  # noqa: E402
from jeju_agent.planner import parse_hybrid  # noqa: E402
from jeju_agent.synth import load_catalog  # noqa: E402

OUT = ROOT / "docs" / "submission" / "results" / "parse_bench.json"
CAT = load_catalog()
# (질문, 기대 동네 일부, 기대 업종 일부, 기대 대상 라벨 or None, 기대 관점 집합)
CASES = [
    ("함덕 해수욕장 앞에서 브런치 가게 하려는데 외지인 손님 비율 높을까요?", {"조천읍"}, {"서양식 음식점업"}, "관광객", {"share"}),
    ("애월 바닷가 커피숍, 여름 한철 장사인가요?", {"애월읍"}, {"비알콜 음료점업"}, None, {"trend"}),
    ("노형 쪽 고깃집인데 몇 시에 제일 붐벼요?", {"노형동"}, {"한식 음식점업"}, None, {"timeslot"}),
    ("중문 호텔들 중국 손님 얼마나 돼요", {"중문동"}, {"호텔업"}, "중국인", {"share"}),
    ("서귀포 시내 술집은 주말에 몰리나요 평일에 몰리나요", {"서귀동"}, {"기타 주점업"}, None, {"weekday"}),
    ("성산 일출봉 근처 기념품 가게 매출이 어느 달에 제일 좋아요?", {"성산읍"}, {"관광 민예품 및 선물용품 소매업"}, None, {"trend"}),
    ("제주공항 주변 렌트카 업체는 단체 관광객 비중이 어때요?", {"용담이동"}, {"자동차 임대업"}, "단체 관광객", {"share"}),
    ("연동 편의점 야간 매출 비중", {"연동"}, {"체인화 편의점"}, None, {"timeslot", "share"}),
    ("한림 쪽 펜션 비수기가 언제예요?", {"한림읍"}, {"여관업"}, None, {"trend"}),
    ("구좌 월정리 카페 중에 어디가 제일 잘 팔려요? 다른 동네랑 비교도", {"구좌읍"}, {"비알콜 음료점업"}, None, {"rank", "compare"}),
    ("표선 해장국집 도민 손님 많나요", {"표선면"}, {"한식 음식점업"}, "도민", {"share"}),
    ("이도동 일식집 점심이랑 저녁 중 언제 장사가 더 돼요", {"이도일동", "이도이동"}, {"일식 음식점업"}, None, {"timeslot"}),
    ("우도 가게들 일본 사람들 많이 와요?", {"우도면"}, set(), "일본인", {"share"}),
    ("대정 모슬포항 횟집 계절 타나요", {"대정읍"}, {"한식 음식점업"}, None, {"trend"}),
    ("삼도동 호프집 손님 연령대랑 요일 패턴", {"삼도일동", "삼도이동"}, {"기타 주점업"}, None, {"weekday"}),
]




def score(slots, exp) -> dict:
    return {"동네": exp[1] <= set(slots.regions) if exp[1] else True,
            "업종": exp[2] <= set(slots.business) if exp[2] else True,
            "대상": (slots.segment[2].startswith(exp[3]) if slots.segment else False) if exp[3] else True,
            "관점": exp[4] <= set(slots.views)}


def run(use_ai: bool) -> dict:
    rows, t0 = [], time.time()
    spent0 = llm.month_spent()
    for c in CASES:
        s, note = parse_hybrid(c[0], CAT, "사업계획서·창업", use_llm=use_ai)
        sc = score(s, c)
        rows.append({"question": c[0], "ok": all(sc.values()), **sc, "regions": s.regions, "business": s.business,
                     "segment": s.segment[2] if s.segment else "", "views": s.views, "note": note})
    n = len(rows)
    return {"mode": "AI(gpt-6-luna) + 규칙" if use_ai else "규칙만", "완전 정답": sum(r["ok"] for r in rows), "문항": n,
            **{k: sum(r[k] for r in rows) for k in ("동네", "업종", "대상", "관점")},
            "초": round(time.time() - t0, 1), "AI 비용(USD)": round(llm.month_spent() - spent0, 5), "rows": rows}


if __name__ == "__main__":
    repeat = int(sys.argv[1]) if len(sys.argv) > 1 else 3          # AI 답은 실행마다 다를 수 있어 여러 번 잰다
    res = [run(False)]
    if llm.get_config().enabled:
        res += [run(True) for _ in range(repeat)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"run_date": str(date.today()), "results": res}, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in res:
        print(r["mode"], f"완전 정답 {r['완전 정답']}/{r['문항']}", {k: r[k] for k in ("동네", "업종", "대상", "관점")},
              f"{r['초']}초", f"${r['AI 비용(USD)']}")
