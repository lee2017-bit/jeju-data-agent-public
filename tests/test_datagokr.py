"""공공데이터포털 공개 데이터: 관광공사 방문자 수·행안부 법정동 인구 받기와 카드."""
import io
import json
from datetime import date

from jeju_agent import datagokr
from jeju_agent.agent import run_plan
from jeju_agent.datagokr import POP_ID, VISIT_ID, load_population, load_visitors
from jeju_agent.insight import card_stores, card_visitors
from jeju_agent.planner import make_plan, parse, visitor_steps
from jeju_agent.stores import STORES_ID, load_stores
from jeju_agent.synth import get_table, load_catalog, ref_rows

CAT = load_catalog()


class R(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_visitors_keeps_only_jeju_and_labels():
    item = lambda code, nm, div, n: {"signguCode": code, "signguNm": nm, "daywkDivNm": "수요일", "touDivCd": div,  # noqa: E731
                                     "touNum": str(n), "baseYmd": "20251001"}
    body = {"response": {"body": {"items": {"item": [item("11110", "종로구", "2", 9), item("50110", "제주시", "2", 143496.5),
                                                       item("50130", "서귀포시", "3", 27178.57)]}}}}
    df = datagokr.fetch_visitors(date(2025, 10, 1), date(2025, 10, 1), key="k",
                                 opener=lambda url, timeout=0: R(json.dumps(body).encode()))
    assert list(df["sigungu"]) == ["제주시", "서귀포시"] and list(df["tou_div"]) == ["외지인", "외국인"]
    assert df.loc[0, "base_year_month"] == "202510"


def test_fetch_population_sums_ri_into_beopjeongdong():
    rows = [{"sggNm": "제주시", "stdgNm": "애월읍", "liNm": "하귀1리", "totNmprCnt": "6661", "hhCnt": "2800"},
            {"sggNm": "제주시", "stdgNm": "애월읍", "liNm": "애월리", "totNmprCnt": "2342", "hhCnt": "1000"},
            {"sggNm": "제주시", "stdgNm": "노형동", "liNm": None, "totNmprCnt": "51388", "hhCnt": "20000"}]
    calls = []

    def opener(url, timeout=0):
        calls.append(url)
        return R(json.dumps({"Response": {"items": {"item": rows if len(calls) == 1 else []}}}).encode())
    df = datagokr.fetch_population("202609", key="k", opener=opener)
    assert dict(zip(df["bjd"], df["pop"])) == {"노형동": 51388, "애월읍": 9003}


def test_bundled_files_load_and_match_center_places():
    v, p = load_visitors(CAT), load_population(CAT)
    assert v is not None and p is not None and not v.missing and not p.missing
    assert set(v.df["sigungu"]) == {"제주시", "서귀포시"} and set(v.df["tou_div"]) == {"현지인", "외지인", "외국인"}
    assert v.df["base_year_month"].nunique() == 12
    center = {r[0] for r in ref_rows(get_table(CAT, "1-08"), "법정동")}
    assert set(p.df["bjd"]) == center and 600_000 < p.df["pop"].sum() < 750_000


def test_visitor_card_and_population_line():
    plan = make_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    plan.steps = visitor_steps(["제주시"]) + plan.steps
    L = {VISIT_ID: load_visitors(CAT), STORES_ID: load_stores(CAT), POP_ID: load_population(CAT)}
    outs = run_plan(plan, L)
    tr = next((i, o) for i, o in enumerate(outs) if o.step.table_id == VISIT_ID and o.step.tool == "trend")
    wk = next((i, o) for i, o in enumerate(outs) if o.step.table_id == VISIT_ID and o.step.tool == "pattern")
    c = card_visitors(tr, wk, plan, "2025.10~2026.09")
    assert c and c.public and c.title.startswith("최근 1년 제주시 외지인 방문자는") and "년" in c.vals["hi"]
    assert "매출과는 다릅니다" in c.explain and "한국관광공사" in c.report and c.vals["W"] is not None
    so = next(o for o in outs if o.step.tool == "store_rank")
    s = card_stores(0, so, plan, None, "2026.09", L[POP_ID])
    assert s.vals["per1000"] and s.vals["per1000_all"] and "도민 1,000명당" in s.explain
