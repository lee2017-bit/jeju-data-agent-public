import io

import pandas as pd
import pytest

from jeju_agent.loader import load_center_csv
from jeju_agent.semantics import by_role, table_roles
from jeju_agent.synth import generate, get_table, load_catalog
from jeju_agent.tools import compare_share, pattern, share_by, top_n, trend

CAT = load_catalog()


@pytest.fixture(scope="module")
def card():
    return generate("1-08", "202505-202604", seed=3, cat=CAT)


def _csv_bytes(df, enc="utf-8-sig", header="name"):
    if header == "label":
        lab = {c["name"]: c["label"] for c in get_table(CAT, "1-08")["columns"]}
        df = df.rename(columns=lab)
    return df.to_csv(index=False).encode(enc)


@pytest.mark.parametrize("enc", ["utf-8-sig", "cp949"])
@pytest.mark.parametrize("header", ["name", "label"])
def test_load_identifies_table_any_encoding_and_header(card, enc, header):
    lt = load_center_csv(io.BytesIO(_csv_bytes(card.head(500), enc, header)), CAT)
    assert lt.table_id == "1-08"
    assert lt.encoding == enc
    assert (lt.df["age"] == "NA").any()          # 'NA' 문자열 보존
    assert pd.api.types.is_numeric_dtype(lt.df["use_amt"])


def test_unknown_csv_is_rejected():
    lt = load_center_csv(io.BytesIO("a,b\n1,2\n".encode()), CAT)
    assert lt.table is None and lt.notes


def test_roles_card():
    roles = table_roles(get_table(CAT, "1-08"))
    assert by_role(roles, "time_month") == ["base_year_month"]
    assert by_role(roles, "region")[-1] == "bjd"
    assert set(by_role(roles, "measure")) == {"user_cnt", "use_cnt", "use_amt"}
    assert "biz_nm" in by_role(roles, "business")


def test_share_sums_to_total(card):
    lt = load_center_csv(io.BytesIO(_csv_bytes(card)), CAT)
    r = share_by(lt.df, "tour_type", "use_amt", filters={"bjd": ["애월읍"]})
    assert abs(r.table["비중(%)"].sum() - 100) < 0.5
    assert "검산: 항목별 합계 = 전체 합계" in r.checks


def test_trend_coverage_and_compare(card):
    lt = load_center_csv(io.BytesIO(_csv_bytes(card)), CAT)
    t = trend(lt.df, "base_year_month", "use_amt", filters={"bjd": ["애월읍"], "biz_nm": ["비알콜 음료점업"]})
    assert any("빠진 달 없음" in c for c in t.checks)
    assert len(t.table) == 12
    c = compare_share(lt.df, {"bjd": ["애월읍"], "biz_nm": ["비알콜 음료점업"]}, "tour_type", ["개별", "단체"],
                      "use_amt", base={"biz_nm": ["비알콜 음료점업"]})
    assert c.facts["applied"]["관심 대상 비중(%)"] > c.facts["applied"]["비교 기준 비중(%)"]  # 가상 데이터: 애월 관광 가중치
    top = top_n(lt.df, "bjd", "use_amt", n=5)
    assert list(top.table["순위"]) == [1, 2, 3, 4, 5]
    p = pattern(lt.df, "user_type", "use_amt")
    assert "가장 많은 시점" in p.facts["applied"]


def test_weekday_pattern_excludes_holiday_double_count():
    df = pd.DataFrame({"week": ["월요일", "토요일", "공휴일"], "use_amt": [100, 300, 50]})
    r = pattern(df, "week", "use_amt", exclude=["공휴일"])
    assert "공휴일" not in set(r.table["week"])
    assert abs(r.table["비중(%)"].sum() - 100) < 0.1 and r.facts["applied"]["가장 많은 시점"] == "토요일"
    assert any("중복 방지" in c for c in r.checks)
