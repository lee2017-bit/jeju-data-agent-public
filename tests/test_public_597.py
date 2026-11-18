import io
import json

import pandas as pd

from jeju_agent.agent import run_plan
from jeju_agent.datahub_api import fetch_all
from jeju_agent.loader import load_center_csv
from jeju_agent.planner import PUBLIC_ID, make_public_plan, parse
from jeju_agent.synth import get_table, load_catalog

CAT = load_catalog()
# API 가이드 예시 형식(값 앞 공백 포함)의 가상 응답
def _rows():
    out = []
    for ym in ("201901", "201902", "201903"):
        for sg in (" 제주시", " 서귀포시"):
            for cg in (" 도심", " 읍면"):
                for mt, base in ((" 식음료", 100), (" 숙박", 300), (" 전체", 400)):
                    for ut, w in ((" 내국인관광객", 3), (" 제주도민", 2)):
                        for ag in ("20대", "40 대"):
                            out.append({"sido": " 제주도", "sigungu": sg, "cityGubun": cg, "marketType": mt, "userType": ut,
                                        "ageGroup": ag, "gender": " 여", "dtYearMonth": ym,
                                        "userCount": base * w, "useCount": base * w + 5, "useCost": base * w * 10000})
    return out


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_all_paginates_and_strips():
    rows = _rows()
    pages = [rows[i:i + 100] for i in range(0, len(rows), 100)]
    calls = []

    def opener(url, timeout=30):
        n = int(url.split("number=")[1].split("&")[0])
        calls.append(url)
        body = {"totCnt": len(rows), "hasMore": n < len(pages), "data": pages[n - 1]}
        return _Resp(json.dumps(body).encode())

    df = fetch_all(get_table(CAT, PUBLIC_ID), app_key="TESTKEY", opener=opener, pause=0)
    assert len(df) == len(rows) and len(calls) == len(pages)
    assert df["sigungu"].iloc[0] == "제주시" and "TESTKEY" in calls[0]


def test_public_plan_on_csv_avoids_total_double_count():
    df = pd.DataFrame(_rows())
    lt = load_center_csv(io.BytesIO(df.to_csv(index=False).encode("utf-8-sig")), CAT)
    assert lt.table_id == PUBLIC_ID and lt.df["sigungu"].iloc[0] == "제주시"
    plan = make_public_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    assert plan.steps[0].params["focus"] == {"sigungu": ["제주시"], "cityGubun": ["읍면"], "marketType": ["식음료"]}
    outs = run_plan(plan, {PUBLIC_ID: lt})
    assert all(o.result is not None for o in outs if o.step.table_id == PUBLIC_ID)
    assert outs[0].result.facts["applied"]["관심 대상 비중(%)"] == 60.0     # 3:2 → 60%
    assert "전체" not in set(outs[1].result.table.columns)
