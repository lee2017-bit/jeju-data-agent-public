"""실제 제주데이터허브 597 CSV(2016.09~2018.12)로 회귀 테스트.

2026-11-03 사용자 PC 실행에서 나온 문제를 막는다:
'식음료의  가운데', '이 가장 많은 달은'(지표 이름 누락), 출처가 '제주빅데이터센터'·'기간 미상'으로 나옴,
업종 '전체' 행이 없는데 '전체'로 걸러 빈 결과, 연령대 표기 섞임('20 미만'·'20대미만'),
실제 데이터 결과까지 '가상 데이터 예시'로 표시됨.
"""

from pathlib import Path

import pytest

from jeju_agent.agent import run_plan
from jeju_agent.korean import josa
from jeju_agent.loader import from_frame, load_center_csv
from jeju_agent.planner import PUBLIC_ID, make_plan, make_public_plan, parse
from jeju_agent.report import build_report, period_of, source_line
from jeju_agent.synth import generate, load_catalog

CAT = load_catalog()
REAL = Path(__file__).resolve().parents[1] / "data" / "public" / "허브597_내국인관광객_카드이용_201609-201812.csv"


@pytest.fixture(scope="module")
def hub():
    return load_center_csv(REAL, CAT)


def test_real_597_loads_and_normalizes(hub):
    assert hub.table_id == PUBLIC_ID and len(hub.df) == 19573
    assert set(hub.df["ageGroup"]) == {"20대 미만", "20대", "30대", "40대", "50대", "60대이상"}
    assert "전체" not in set(hub.df["marketType"])
    assert period_of(hub) == "2016.09~2018.12"
    src = source_line(hub)
    assert src.startswith("자료: 제주데이터허브") and "597" in src and "빅데이터센터" not in src


def _public(hub) -> dict:
    """앱이 시작할 때 넣는 공개 데이터 전부(597·상가정보·관광공사 방문자 수·행안부 인구)."""
    from jeju_agent.datagokr import POP_ID, VISIT_ID, load_population, load_visitors
    from jeju_agent.hub_district import DISTRICT_ID, load_district
    from jeju_agent.stores import STORES_ID, load_stores
    return {PUBLIC_ID: hub, STORES_ID: load_stores(CAT), VISIT_ID: load_visitors(CAT), POP_ID: load_population(CAT),
            DISTRICT_ID: load_district(CAT)}


@pytest.mark.parametrize("q", ["제주시 관광객 비중 알려줘", "애월읍에 카페 열면 어때?", "서귀포 숙박 매출 추이"])
def test_public_plan_runs_on_real_data(hub, q):
    plan = make_public_plan(parse(q, CAT, "사업계획서·창업"), CAT)
    outs = run_plan(plan, _public(hub))
    assert all(o.result is not None and o.narrative for o in outs)
    cmp_ = outs[0].result.facts["applied"]
    assert cmp_["관심 대상 비중(%)"] == cmp_["관심 대상 비중(%)"]          # NaN 아님
    text = " ".join(x for o in outs for x in o.narrative)
    assert "  " not in text and "의 가운데" not in text and "의  가운데" not in text
    assert "매출이 가장 많은 달은" in text
    if "카페" not in q and "숙박" not in q:                                # 업종을 모르면 업종 조건 없이 전체 합산
        assert "marketType" not in plan.steps[0].params["focus"]


def test_josa():
    assert josa("매출", "이/가") == "이" and josa("결제 건수", "이/가") == "가"
    assert josa("이용자 수", "은/는") == "는" and josa("매출(카드 이용금액)", "은/는") == "은"


def test_mixed_real_and_synthetic_report_labels(hub, tmp_path):
    plan = make_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    pub = make_public_plan(plan.slots, CAT)
    from jeju_agent.datagokr import VISIT_ID
    from jeju_agent.stores import STORES_ID
    loaded = _public(hub)
    for tid in ("1-08", "1-12", "1-14"):
        loaded[tid] = from_frame(generate(tid, "202601-202603", seed=5, cat=CAT), tid, CAT, synthetic=True)
    plan.steps = pub.steps + plan.steps
    b = build_report(plan, run_plan(plan, loaded), loaded, tmp_path)
    pubs = (PUBLIC_ID, STORES_ID, VISIT_ID, "허브-지구")
    pub_secs = [s for s in b.sections if s["table_id"] in pubs]
    syn_secs = [s for s in b.sections if s["table_id"] not in pubs]
    assert any(s["table_id"] == "허브-지구" and s["source"].startswith("자료: 제주데이터허브, 관광지") for s in pub_secs)
    assert any(s["table_id"] == VISIT_ID and "한국관광공사" in s["source"] for s in pub_secs)
    assert any(s["table_id"] == STORES_ID and "상가(상권)정보" in s["source"] for s in pub_secs)
    assert pub_secs and not any(s["synthetic"] for s in pub_secs)
    assert syn_secs and all(s["synthetic"] for s in syn_secs)
    assert all("가상 데이터" in s["source"] for s in syn_secs)
    assert not any("제주 전체 월별 추세" in s["badge"] for s in pub_secs)
    for s in b.sections:                                      # 표 머리글은 한글
        assert not {"dtYearMonth", "ageGroup", "bjd", "user_type", "week", "time"} & set(s["table"].columns)
    html = b.html.read_text(encoding="utf-8")
    assert "실제 데이터 결과" in html and "[가상]" in html
    req = b.request_txt.read_text(encoding="utf-8")
    assert "허브-597" not in req and "공개 데이터(제주데이터허브)" in req
