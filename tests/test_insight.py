import re

import pytest

from jeju_agent.agent import run_plan
from jeju_agent.demo import demo_tables, load_public
from jeju_agent.insight import TOURIST_GRADES, VERDICT_RULES, build_answer
from jeju_agent.planner import PUBLIC_ID, Plan, make_plan, make_public_plan, parse
from jeju_agent.synth import load_catalog

CAT = load_catalog()


def _answer(q, purpose, with_public=True):
    plan = make_plan(parse(q, CAT, purpose), CAT)
    L = demo_tables(plan, CAT)
    if with_public:
        pub = make_public_plan(plan.slots, CAT)
        plan = Plan(plan.slots, plan.steps + pub.steps, plan.requests + pub.requests, plan.notes, plan.scope_notes,
                    focus_label=plan.focus_label)
    outs = run_plan(plan, L)
    return plan, outs, build_answer(plan, outs, L)


@pytest.mark.parametrize("q,purpose,start", [
    ("애월읍에 카페 열면 어때?", "사업계획서·창업", "[체험] 애월읍 카페는"),
    ("노형동 한식당 요일·시간대별 매출은?", "가게·회사 운영", "[체험] 노형동 한식당은"),
    ("카페는 어느 동이 가장 많이 팔려?", "현황자료·보고서", "[체험] 제주에서 카페 매출이 가장 큰 동네는"),
    ("서귀포 렌터카 매출 추이", "가게·회사 운영", "[체험] 서귀포시 렌터카는"),
])
def test_headline_answers_question(q, purpose, start):
    plan, outs, a = _answer(q, purpose)
    assert a.headline.startswith(start) and a.headline.endswith(".")
    assert "  " not in a.headline and "관심 대상" not in a.headline
    assert a.cards and all(c.title and c.sowhat for c in a.cards)
    assert any("가상 데이터" in c for c in a.caveats)          # 체험(가상) 결론임을 밝힘
    assert a.public_card is not None and a.public_card.title.startswith("공개 데이터(실제 값)")   # 체험 모드: 일치 판정 안 함


def test_startup_answer_has_kpis_actions_trust():
    plan, outs, a = _answer("애월읍에 카페 열면 어때?", "사업계획서·창업")
    assert len(a.kpis) == 3 and len(a.actions) == 3
    assert a.kpis[0].label == "관광객 손님 몫" and a.kpis[1].label == "성수기 ÷ 비수기" and a.kpis[2].value.endswith("위")
    assert any("검산" in t for t in a.trust) and any("597" in t for t in a.trust)
    assert [c.key for c in a.cards][0] == "customers"
    grades = {g for _, g in TOURIST_GRADES}
    assert a.cards[0].grade in grades


def test_numbers_in_answer_come_from_results():
    plan, outs, a = _answer("애월읍에 카페 열면 어때?", "사업계획서·창업")
    allowed = set()
    for o in outs:
        if o.result is None:
            continue
        allowed |= set(re.findall(r"\d+(?:\.\d+)?", str(o.result.facts.get("applied"))))
        t = o.result.table
        allowed |= set(re.findall(r"\d+(?:\.\d+)?", t.to_string()))
        for col in [c for c in t.columns if "비중" in c]:
            v = list(t[col])
            allowed |= {str(round(a_ + b_, 1)) for i, a_ in enumerate(v) for b_ in v[i + 1:]}
            allowed |= {str(round(a_ + b_ + c_, 1)) for i, a_ in enumerate(v) for j, b_ in enumerate(v[i + 1:], i + 1)
                        for c_ in v[j + 1:]}
    allowed |= {str(round(float(x))) for x in allowed if "." in x}      # 지수 127.3 → 화면 '127'처럼 반올림 표기
    allowed |= {f"{float(x):.1f}" for x in allowed if "." in x}          # 1시간당 6.55% → 화면 '6.5%'(소수 한 자리)
    text = a.headline + " ".join(c.title + " " + c.explain for c in a.cards)
    nums = set(re.findall(r"\d+(?:\.\d+)?", text))
    fixed = {"10", "28.6", "14.3", "100", "120", "80", "2016", "2018", "597", "1-19"}
    nums = {n for n in nums - fixed if not re.fullmatch(r"\d", n) and not re.fullmatch(r"1[0-2]", n)
            and not re.fullmatch(r"\d{2}", n)}      # 'n월', 'n시간', '26년', '100원 중 n원' 같은 표기
    assert nums <= allowed, nums - allowed


def test_asked_view_comes_first():
    plan, outs, a = _answer("노형동 한식당 요일·시간대별 매출은?", "가게·회사 운영")
    assert [c.key for c in a.cards][:2] == ["week", "time"]
    assert a.cards[0].grade in ("주말형", "평일형", "요일 고른 편")
    assert a.headline.startswith("[체험] 노형동 한식당은 주말") and "일손 배치" in a.core


def test_public_only_answer_says_so():
    plan = make_public_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    L = {PUBLIC_ID: load_public(CAT)}
    a = build_answer(plan, run_plan(plan, L), L)
    assert "[체험]" not in a.headline and a.headline.startswith("제주시 읍면 지역 식음료는")
    assert "%p" not in a.public_card.explain
    assert any("공개 데이터" in c for c in a.caveats) and not any("가상" in c for c in a.caveats)
    assert any("제주데이터허브" in b for b in a.basis)
    assert "서귀포시 읍면(64.6%)" in a.public_card.explain        # 읍면이면 어디나 높다(공정한 비교)


def test_neutral_style_for_research():
    plan, outs, a = _answer("애월읍 카페 관광객 비중이 얼마나 돼?", "논문·연구")
    assert a.neutral and not a.actions and a.report_sentences and a.citation
    assert "장사" not in a.headline


def test_foreign_share_wording():
    plan, outs, a = _answer("중문동 편의점 외국인 손님 비중", "가게·회사 운영", with_public=False)
    assert "외국인 손님이 평균의" in a.headline and "배" in a.headline


def test_rules_table_is_published():
    assert len(VERDICT_RULES) == 6 and all(len(r) == 3 for r in VERDICT_RULES)


FORBIDDEN = ["반드시", "무조건", "확실히", "성공", "실패", "유망", "추천 입지", "열어도 됩니다", "열지 마세요", "창업하세요",
             "경쟁이 치열", "경쟁이 적", "bjd", "biz_nm", "use_amt", "tour_type", "dtYearMonth", "ageGroup"]


@pytest.mark.parametrize("q,purpose", [("애월읍에 카페 열면 어때?", "사업계획서·창업"),
                                       ("노형동 한식당 요일·시간대별 매출은?", "가게·회사 운영"),
                                       ("성산읍 흑돼지 식당, 관광객 비중은?", "사업계획서·창업")])
def test_screen_text_rules(q, purpose):
    plan, outs, a = _answer(q, purpose)
    screen = " ".join([a.headline, a.core, a.market] + a.actions + [k.label + k.value + k.delta for k in a.kpis]
                      + [c.title + c.explain + c.sowhat for c in a.cards])
    assert not [w for w in FORBIDDEN if w in screen]
    assert "%p" not in screen and "  " not in screen and "26년" not in screen
    assert a.headline.endswith("장사입니다.") and a.headline.count(",") <= 2
