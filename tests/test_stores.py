"""공개 상가정보(소상공인시장진흥공단): 동봉 집계·업종 대응·경쟁 카드·새로 받기."""
import io
import json
import zipfile

import pandas as pd

from jeju_agent import stores
from jeju_agent.insight import Card, card_stores
from jeju_agent.planner import make_plan, parse
from jeju_agent.stores import STORES_ID, aggregate, card_biz, load_stores
from jeju_agent.synth import get_table, load_catalog, ref_rows

CAT = load_catalog()


def test_bundled_file_matches_center_places_and_industries():
    lt = load_stores(CAT)
    assert lt is not None and lt.table_id == STORES_ID and not lt.missing
    center_bjd = {r[0] for r in ref_rows(get_table(CAT, "1-08"), "법정동")}
    assert set(lt.df["bjd"]) <= center_bjd                       # 동네 이름이 센터 1-08과 같다
    cafe = lt.df[lt.df["card_biz"] == "비알콜 음료점업"].groupby("bjd")["store_cnt"].sum()
    assert cafe.idxmax() == "애월읍" and cafe.sum() > 2000            # 2026.09: 애월읍 221곳, 제주 2,980곳
    assert "상호명" not in lt.df.columns and "경도" not in lt.df.columns   # 가게 이름·좌표는 넣지 않음


def test_card_biz_mapping():
    assert card_biz("비알코올 ", "카페") == "비알콜 음료점업"
    assert card_biz("한식", "백반/한정식") == "한식 음식점업"
    assert card_biz("일반 숙박", "펜션") == "여관업"                    # 카드 업종 '여관업'에 펜션·게스트하우스가 들어 있음
    assert card_biz("기타 간이", "치킨") == ""


def _plan():
    return make_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)


def test_store_card_with_and_without_center_share():
    from jeju_agent.agent import run_plan
    plan = _plan()
    o = next(o for o in run_plan(plan, {STORES_ID: load_stores(CAT)}) if o.step.tool == "store_rank")
    c = card_stores(0, o, plan, None, "2026.09")
    assert c.public and "애월읍에는 카페가" in c.title and c.vals["r"] == 1 and c.vals["E"] is None
    assert "2026.09" in c.eyebrow and "상가(상권)정보" in c.report
    loc = Card("location", "", "", "", "", "", 0, vals={"S": 3.7})
    c2 = card_stores(0, o, plan, loc, "2026.09")
    assert c2.vals["E"] == round(3.7 / c2.vals["share"], 2) and "가게 하나당 매출" in c2.explain


def test_update_downloads_and_keeps_only_jeju_counts(tmp_path):
    raw = pd.DataFrame({"상호명": ["a", "b", "c"], "시군구명": ["제주시"] * 3, "법정동명": ["애월읍", "애월읍", "노형동"],
                        "상권업종대분류명": ["음식"] * 3, "상권업종중분류명": ["비알코올 "] * 3, "상권업종소분류명": ["카페"] * 3})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("소상공인시장진흥공단_상가(상권)정보_서울_202609.csv", "x\n")
        z.writestr("소상공인시장진흥공단_상가(상권)정보_제주_202609.csv", raw.to_csv(index=False))
    page = "fn_fileDataDown('15083033', 'uddi:abc', '','1', '1')"
    meta = json.dumps({"atchFileId": "FILE_1", "fileDataRegistVO": {"dataNm": "소상공인시장진흥공단_상가(상권)정보_20260930"}})

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(url, timeout=0):
        if "fileData.do" in url:
            return R(page.encode())
        if "selectFileDataDownload" in url:
            return R(meta.encode())
        return R(buf.getvalue())

    out = stores.update(tmp_path, opener=opener)
    df = pd.read_csv(out, dtype={"base_year_month": str})
    assert out.name == "상가정보_제주_202609_동네업종별_가게수.csv"
    assert dict(zip(df["bjd"], df["store_cnt"])) == {"노형동": 1, "애월읍": 2} and set(df["base_year_month"]) == {"202609"}
    assert "상호명" not in df.columns


def test_aggregate_strips_and_counts():
    raw = pd.DataFrame({"시군구명": ["제주시"], "법정동명": [" 애월읍 "], "상권업종대분류명": ["음식"],
                        "상권업종중분류명": ["한식"], "상권업종소분류명": ["국수/칼국수"]})
    g = aggregate(raw, "202609")
    assert g.loc[0, "bjd"] == "애월읍" and g.loc[0, "card_biz"] == "한식 음식점업" and g.loc[0, "store_cnt"] == 1
