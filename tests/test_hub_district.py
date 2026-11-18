"""제주데이터허브 '관광지 및 상업지구' 카드 데이터(사용자가 PC에서 받아 첨부, 2016.09~2017.11) — 지구 유형 비교 카드."""
from jeju_agent.agent import run_plan
from jeju_agent.hub_district import DISTRICT_ID, closest_district, load_district
from jeju_agent.insight import card_district
from jeju_agent.planner import make_public_plan, parse
from jeju_agent.synth import load_catalog

CAT = load_catalog()


def test_bundled_district_table():
    lt = load_district(CAT)
    assert lt is not None and not lt.missing
    assert set(lt.df["dim"]) == {"요일", "시간대", "이용자"} and lt.df["districtType"].nunique() == 5
    assert lt.df["dtYearMonth"].min() == "201609" and lt.df["dtYearMonth"].max() == "201711"


def test_closest_district_mapping():
    city = lambda b: "서귀포시" if b in ("서귀동", "중문동") else "제주시"   # noqa: E731
    assert closest_district(["애월읍"], city) == "내국인 주요 관광지"
    assert closest_district(["노형동"], city) == "상업지"
    assert closest_district(["일도이동"], city) == "제주시 구도심"
    assert closest_district(["서귀동"], city) == "서귀포시 구도심"
    assert closest_district([], city) is None


def _card(q):
    plan = make_public_plan(parse(q, CAT, "사업계획서·창업"), CAT)
    outs = run_plan(plan, {DISTRICT_ID: load_district(CAT)})
    i, o = next((i, o) for i, o in enumerate(outs) if o.step.tool == "district_profile")
    return card_district(i, o, plan)


def test_district_card_real_values():
    c = _card("애월읍에 카페 열면 어때?")
    assert c.public and c.vals["focus"] == "내국인 주요 관광지" and c.vals["lead"] == "오후"
    assert c.vals["W"] == 33.3 and "추정" in c.explain and "2016.09~2017.11" in c.eyebrow
    assert "낮 장사" in c.sowhat
    c2 = _card("서귀포 올레시장 근처 주점")
    assert c2.vals["focus"] == "서귀포시 구도심" and c2.vals["lead"] == "저녁" and "저녁 장사" in c2.sowhat
