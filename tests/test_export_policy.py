import pandas as pd

from jeju_agent.export_policy import (
    Kind,
    Verdict,
    code_has_data_print,
    find_small_values,
    judge,
    suppress_small_values,
)

CARD = {"id": "1-08", "name": "카드 이용 현황(읍면동)_v02", "raw_export_allowed": False}
BUS = {"id": "3-02", "name": "버스 노선별 이용 현황", "raw_export_allowed": True}


def test_open_data_always_ok():
    assert judge(Kind.RAW, [BUS], ".csv").verdict == Verdict.OK


def test_restricted_raw_blocked():
    assert judge(Kind.RAW, [CARD], ".csv").verdict == Verdict.BLOCKED
    assert judge(Kind.EXTRACT, [CARD, BUS], ".csv").verdict == Verdict.BLOCKED


def test_restricted_chart_must_be_image():
    assert judge(Kind.CHART, [CARD], ".html").verdict == Verdict.BLOCKED
    assert judge(Kind.CHART, [CARD], ".png").verdict == Verdict.CONDITIONAL


def test_applied_agg():
    assert judge(Kind.APPLIED_AGG, [CARD], ".png").verdict == Verdict.OK
    assert judge(Kind.APPLIED_AGG, [CARD], ".csv").verdict == Verdict.CONDITIONAL


def test_simple_agg_is_conditional():
    assert judge(Kind.SIMPLE_AGG, [CARD], ".png").verdict == Verdict.CONDITIONAL


def test_suppress_mask_and_drop():
    df = pd.DataFrame({"동": ["애월읍", "한림읍", "구좌읍"], "건수": [120, 7, 0], "금액": [5_000_000, 90_000, 0]})
    assert find_small_values(df, ["건수", "금액"]) == 3
    m = suppress_small_values(df, ["건수", "금액"], method="mask")
    assert m.suppressed_cells == 3
    assert m.data.loc[1, "건수"] == "10 미만"
    assert m.data.loc[1, "금액"] == 90_000
    d = suppress_small_values(df, ["건수", "금액"], method="drop")
    assert d.dropped_rows == 2 and list(d.data["동"]) == ["애월읍"]


def test_code_data_print_detection():
    assert code_has_data_print("df = pd.read_csv('a.csv')\ndf.head()")
    assert code_has_data_print("print(df)")
    assert not code_has_data_print("summary = df.groupby('bjd')['use_amt'].sum()\nsummary.plot()")
