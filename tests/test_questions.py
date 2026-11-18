"""다양한 질문 5종(+비교) — 실제 화면 테스트에서 나온 문제를 고정한다."""
import pytest

from jeju_agent.agent import run_plan
from jeju_agent.demo import demo_tables
from jeju_agent.insight import build_answer
from jeju_agent.planner import make_plan, parse
from jeju_agent.synth import load_catalog

CAT = load_catalog()


def ask(q, purpose="사업계획서·창업"):
    s = parse(q, CAT, purpose)
    plan = make_plan(s, CAT)
    L = demo_tables(plan, CAT)
    return s, plan, build_answer(plan, run_plan(plan, L), L)


def test_compare_two_dongs_in_question_order():
    s, plan, a = ask("연동이랑 노형동 편의점 매출 비교해줘", "논문·연구")
    assert s.regions == ["연동", "노형동"]                       # 질문에 나온 순서
    assert any(st.tool == "region_compare" for st in plan.steps)
    assert a.cards[0].key == "regions"
    assert [k.label for k in a.kpis] == ["연동 관광객 몫", "노형동 관광객 몫"]
    assert a.report_sentences[0].startswith("편의점 카드 매출 중 관광객 결제 비중은 연동")
    assert "높다" in a.report_sentences[0] or "비슷하다" in a.report_sentences[0]
    assert "비교된다" not in a.report_sentences[0]


def test_which_is_better_is_a_comparison():
    s, plan, a = ask("애월읍이랑 한림읍 중에 어디가 카페 하기 나아?")
    assert s.regions == ["애월읍", "한림읍"] and "compare" in s.views
    assert a.kpis[0].label.startswith("애월읍")
    assert "한림읍" in a.headline
    assert "애월읍" in a.core and "한림읍" in a.core and a.core not in a.actions     # 핵심 줄 = 비교의 답


def test_jungmun_area_and_nationality_label():
    s, plan, a = ask("중문 호텔 중국인 손님 비중 보고서에 쓸 수치 필요해", "현황자료·보고서")
    assert set(s.regions) == {"중문동", "색달동", "대포동"}
    assert plan.focus_label.startswith("중문 일대")
    assert "중국인" in a.headline and "외국인" not in a.headline
    assert a.kpis[0].value.count(".") == 1                      # 10% 미만은 소수 한 자리(3.3%)


@pytest.mark.parametrize("q,expect", [("노형동 고깃집 몇 시에 손님 많아?", "저녁"),
                                      ("연동 주점 손님 몰리는 시간", "밤"),
                                      ("애월 렌터카 시간대별 매출", "오전")])
def test_time_profile_by_industry(q, expect):
    _, _, a = ask(q)
    t = next(c for c in a.cards if c.key == "time")
    assert expect in t.title + t.grade


def test_view_order_follows_question():
    s, _, a = ask("서귀포시 숙박 성수기랑 비수기 차이 알려줘", "현황자료·보고서")
    assert s.views[0] == "trend"                               # 계절(추이)을 먼저
    assert a.cards[0].key == "season"


def test_multi_region_ranks_are_per_dong():
    """두 동네 이상: 합친 몫에 한 동네 순위를 붙이지 않고, 동네마다 따로 매긴 순위를 적는다."""
    _, _, a = ask("신제주 카페 어때?")
    loc = next(c for c in a.cards if c.key == "location")
    assert "노형동" in loc.vals["rk"] and "연동" in loc.vals["rk"]
    assert "노형동" in loc.title and "연동" in loc.title and "위" in loc.title
    assert "순위는" in loc.report
    k = next(k for k in a.kpis if "매출" in k.label)
    assert k.label.endswith("매출 몫") and "노형동" in k.delta
    _, _, a = ask("중문 호텔 중국인 손님 비중 보고서에 쓸 수치 필요해", "현황자료·보고서")
    loc = next(c for c in a.cards if c.key == "location")
    assert loc.title.startswith("중문 일대 ")


def test_tilde_does_not_become_strikethrough():
    import importlib
    import sys
    app = sys.modules.get("app") or importlib.import_module("app")
    assert "~" not in app.esc("2025.05~2026.04, 2016~2018") and "~" not in app.md("11~14시 14~18시")


def test_lodging_season_question_gets_direct_answer_and_fitting_advice():
    _, _, a = ask("서귀포시 숙박업 성수기는 언제고 비수기엔 얼마나 빠져?", "가게·회사 운영")
    assert a.core.startswith("성수기는 ") and "비수기 매출은 성수기의" in a.core
    joined = " ".join(a.actions)
    assert "쉬는 날" not in joined and "메뉴" not in joined          # 숙박업에는 휴무일·메뉴 조언을 하지 않는다
    _, _, a = ask("노형동 고깃집 하면 몇 시에 제일 붐벼요?")
    assert any("쉬는 날" in x for x in a.actions)                   # 음식점은 그대로


@pytest.mark.parametrize("q", ["카페 하려는데 애월이랑 한림 중 어디가 좋을까?", "카페를 하려고 하는데 애월이랑 구좌 둘 중에 어디가 좋을까?",
                               "애월 vs 한림 카페"])
def test_casual_comparison_phrasings(q):
    s, plan, a = ask(q)
    assert len(s.regions) == 2 and any(st.tool == "region_compare" for st in plan.steps)
    assert a.cards[0].key == "regions"
    rg = a.cards[0]
    if 2 <= rg.vals["gap"] < 5:                                   # 제목이 '높습니다'면 결론도 '비슷'이라 하지 않는다
        assert "조금 더 높지만" in a.core


def test_first_example_card_is_comparison():
    import importlib
    import sys
    app = sys.modules.get("app") or importlib.import_module("app")
    first = app.EXAMPLES["사업계획서·창업"][0]
    s, plan, _ = ask(first)
    assert s.regions == ["애월읍", "한림읍"] and any(st.tool == "region_compare" for st in plan.steps)
