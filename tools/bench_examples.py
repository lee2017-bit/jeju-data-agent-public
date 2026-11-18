"""결과 설명자료용 실행 기록: 여러 질문을 화면과 같은 순서(질문 해석 → 계획 → 도구 → 검산 → 판정)로 돌려 결과를 저장한다.

    python tools/bench_examples.py              → docs/submission/results/examples.json
- 질문 해석은 규칙만 쓴다(키 없이 재현 가능). AI 해석 실측은 tools/bench_parse.py.
- 센터 데이터 자리는 명세서 형식의 가상 데이터(체험, 같은 seed)이고, 공개 데이터는 동봉한 실제 값이다.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jeju_agent.agent import run_plan  # noqa: E402
from jeju_agent.datagokr import POP_ID, VISIT_ID, load_population, load_visitors  # noqa: E402
from jeju_agent.demo import demo_tables  # noqa: E402
from jeju_agent.hub_district import DISTRICT_ID, load_district  # noqa: E402
from jeju_agent.insight import build_answer  # noqa: E402
from jeju_agent.planner import PUBLIC_ID, Plan, make_plan, make_public_plan, parse  # noqa: E402
from jeju_agent.stores import STORES_ID, load_stores  # noqa: E402
from jeju_agent.synth import load_catalog  # noqa: E402

OUT = ROOT / "docs" / "submission" / "results" / "examples.json"
QUESTIONS = [
    ("카페 하려는데 애월이랑 한림 중 어디가 좋을까?", "사업계획서·창업"),
    ("성산읍 흑돼지 식당, 관광객 비중은?", "가게·회사 운영"),
    ("노형동 한식당 창업, 요일·시간대별 매출은?", "사업계획서·창업"),
    ("중문동 호텔 중국인 손님 비중", "현황자료·보고서"),
    ("서귀포시 숙박업 계절별 매출 흐름", "현황자료·보고서"),
    ("구좌읍 카페 매출을 다른 동네와 비교", "논문·연구"),
]
OK = ("검산", "기간 확인", "중복 방지")
WARN = ("주의", "기간 누락")


def card_row(c) -> dict:
    return {"key": c.key, "title": c.title, "grade": c.grade, "public": c.public, "synthetic": c.synthetic, "hold": c.hold}


def one(q: str, purpose: str, cat: dict, open_: dict) -> dict:
    t0 = time.perf_counter()
    s = parse(q, cat, purpose)
    plan = make_plan(s, cat)
    loaded = demo_tables(plan, cat)                       # 센터 3표(가상) + 597(실제)
    loaded.update(open_)
    t_load = time.perf_counter() - t0
    pub = make_public_plan(s, cat) if PUBLIC_ID in loaded else None
    extra = [x for x in (pub.steps if pub else []) if not any(x.tool == y.tool and x.table_id == y.table_id for y in plan.steps)]
    run = Plan(s, plan.steps + extra, plan.requests + (pub.requests if pub else []), plan.notes, plan.scope_notes,
               focus_label=plan.focus_label)
    t1 = time.perf_counter()
    outs = run_plan(run, loaded)
    answer = build_answer(run, outs, loaded)
    t_run = time.perf_counter() - t1
    real = {k: v for k, v in loaded.items() if k.startswith(("허브-", "공개-"))}
    pub_answer = build_answer(pub, run_plan(pub, real), real) if pub else None
    done = [o for o in outs if o.result is not None]
    checks = [c for o in done for c in o.result.checks]
    n_pub = sum(1 for x in run.steps if x.table_id.startswith(("허브-", "공개-")))
    return {
        "question": q, "purpose": purpose,
        "understood": {"regions": s.regions, "city": s.city, "business": s.business, "segment": s.segment[2] if s.segment else "",
                       "views": s.views},
        "center_tables": [r.table_id for r in plan.requests],
        "steps": {"total": len(run.steps), "center": len(run.steps) - n_pub, "public": n_pub, "done": len(done),
                  "skipped": len(outs) - len(done)},
        "tools": [f"{o.step.tool}@{o.step.table_id}" for o in outs],
        "checks_passed": sum(1 for c in checks if c.startswith(OK)),
        "warnings": [c for c in checks if c.startswith(WARN)],
        "export_verdicts": sorted({o.export_verdict for o in done}),
        "seconds": {"load": round(t_load, 2), "analyze": round(t_run, 2)},
        "answer_demo": {"headline": answer.headline, "core": answer.core, "kpis": [[k.label, k.value] for k in answer.kpis],
                        "actions": answer.actions, "badges": [b[0] for b in answer.badges],
                        "cards": [card_row(c) for c in answer.cards], "neutral": answer.neutral,
                        "report_sentences": answer.report_sentences[:3], "synthetic": answer.synthetic},
        "answer_public": None if pub_answer is None else {
            "headline": pub_answer.headline, "kpis": [[k.label, k.value] for k in pub_answer.kpis],
            "cards": [card_row(c) for c in pub_answer.cards] + ([card_row(pub_answer.public_card)] if pub_answer.public_card else []),
            "synthetic": pub_answer.synthetic},
    }


def main() -> None:
    cat = load_catalog()
    open_ = {STORES_ID: load_stores(cat)}
    for tid, fn in ((VISIT_ID, load_visitors), (POP_ID, load_population), (DISTRICT_ID, load_district)):
        lt = fn(cat)
        if lt is not None:
            open_[tid] = lt
    rows = [one(q, p, cat, open_) for q, p in QUESTIONS]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"run_date": str(date.today()), "note": "센터 데이터는 가상(체험), 공개 데이터는 실제 값",
                               "examples": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        print(f"{r['question']:<28} 단계 {r['steps']['done']}/{r['steps']['total']} · 검산 {r['checks_passed']} · "
              f"{r['seconds']['analyze']}초 · {r['answer_public']['headline'][:50] if r['answer_public'] else '-'}")
    print(OUT)


if __name__ == "__main__":
    main()
