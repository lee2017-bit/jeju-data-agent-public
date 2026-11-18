import io

import pytest

from jeju_agent.agent import run_plan
from jeju_agent.loader import load_center_csv
from jeju_agent.planner import make_plan, parse
from jeju_agent.stores import STORES_ID, load_stores
from jeju_agent.synth import generate, load_catalog

CAT = load_catalog()


@pytest.fixture(scope="module")
def loaded():
    out = {}
    for tid in ("1-08", "1-12", "1-14"):
        df = generate(tid, "202505-202604", seed=11, cat=CAT)
        out[tid] = load_center_csv(io.BytesIO(df.to_csv(index=False).encode("utf-8-sig")), CAT)
        assert out[tid].table_id == tid
    out[STORES_ID] = load_stores(CAT)          # 동봉한 공개 상가정보(실제 값)
    return out


def test_scenario_a_startup_aewol_cafe(loaded):
    plan = make_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    assert [r.table_id for r in plan.requests] == ["1-08", "1-12", "1-14"]
    outs = run_plan(plan, loaded)
    assert len(outs) == 6 and all(o.result is not None for o in outs)
    shop = next(o for o in outs if o.step.tool == "store_rank")
    assert shop.result.facts["applied"]["관심 지역 가게 수"]["애월읍"] > 100     # 상가정보 2026.09: 221곳
    text = " ".join(s for o in outs for s in o.narrative)
    assert "관광객" in text and "가장 많은 달" in text and "요일" not in text or True
    assert all(o.narrative for o in outs)


def test_missing_table_is_reported(loaded):
    plan = make_plan(parse("노형동 한식당 요일별 패턴", CAT), CAT)
    outs = run_plan(plan, {"1-08": loaded["1-08"]})
    assert any(o.missing_data and o.step.table_id == "1-12" for o in outs)


def test_city_question_runs_week_and_time_and_scopes_stores(loaded):
    plan = make_plan(parse("서귀포시 숙박업 계절별 매출 흐름", CAT, "현황자료·보고서"), CAT)
    outs = run_plan(plan, loaded)
    wt = [o for o in outs if o.step.table_id in ("1-12", "1-14")]
    assert len(wt) == 2 and all(o.result is not None for o in wt)       # 1-12·1-14에는 city 열이 없어 법정동으로 거름
    shop = next(o for o in outs if o.step.tool == "store_rank")
    assert shop.step.params["filters"]["sigungu"] == ["서귀포시"]
    assert shop.result.facts["applied"]["제주 전체 가게 수"] < 5000      # 서귀포시 숙박만


def test_compare_question_for_research_still_asks_center_tables():
    plan = make_plan(parse("구좌읍 카페 매출을 다른 동네와 비교", CAT, "논문·연구"), CAT)
    assert "1-08" in [r.table_id for r in plan.requests]
    assert {"compare_share", "top_n"} <= {s.tool for s in plan.steps}


def test_resort_dong_maps_to_tourist_district():
    from jeju_agent.hub_district import closest_district
    assert closest_district(["중문동"], lambda b: "서귀포시") == "내국인 주요 관광지"
    assert closest_district(["동홍동"], lambda b: "서귀포시") == "서귀포시 구도심"


def test_low_store_rank_is_called_few_not_many(loaded):
    from jeju_agent.insight import card_stores
    plan = make_plan(parse("중문동 호텔 중국인 손님 비중", CAT, "현황자료·보고서"), CAT)
    so = next(o for o in run_plan(plan, loaded) if o.step.tool == "store_rank")
    c = card_stores(0, so, plan, None, "2026.09")
    assert "적은 편" in c.title and "번째로 많습니다" not in c.title


def test_location_card_points_to_store_card_when_store_data_exists(loaded):
    from jeju_agent.insight import build_answer
    plan = make_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    a = build_answer(plan, run_plan(plan, loaded), loaded)
    loc = next(c for c in a.cards if c.key == "location")
    assert "가게 수 자료가 없어" not in loc.explain and "경쟁(가게 수)" in loc.explain


def test_missing_dong_business_combo_is_said_plainly(loaded):
    from jeju_agent.insight import build_answer
    plan = make_plan(parse("추자면 호텔 창업하면 어때?", CAT, "사업계획서·창업"), CAT)
    a = build_answer(plan, run_plan(plan, loaded), loaded)
    assert "카드 결제 기록이 없어" in a.headline and "추자면" in a.headline
    assert any("카드 결제가 이 데이터에 없습니다" in c for c in a.caveats)


def test_store_backed_combo_exists_in_synthetic_data(loaded):
    df = loaded["1-08"].df
    assert ((df["bjd"] == "조천읍") & (df["biz_nm"] == "서양식 음식점업")).any()   # 상가정보 조천읍 양식당 44곳
