import time

from jeju_agent.demo import demo_tables
from jeju_agent.planner import PUBLIC_ID, make_plan, parse
from jeju_agent.synth import load_catalog

CAT = load_catalog()


def test_demo_tables_fast_and_labeled():
    plan = make_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    t = time.time()
    got = demo_tables(plan, CAT)
    assert time.time() - t < 15            # 예전 30초+ → 표 3개 + 공개 데이터를 몇 초 안에
    assert set(got) == {"1-08", "1-12", "1-14", PUBLIC_ID}
    assert all(got[t].synthetic for t in ("1-08", "1-12", "1-14")) and not got[PUBLIC_ID].synthetic
    again = demo_tables(plan, CAT, have=set(got))
    assert again == {}


def test_demo_golden_values():
    """체험 수치 고정: 생성기를 바꾸면 이 테스트가 깨져서 README·캡처 수치와 어긋나는 것을 막는다."""
    from jeju_agent.agent import run_plan
    from jeju_agent.insight import build_answer
    plan = make_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    L = demo_tables(plan, CAT)
    by = {c.key: c for c in build_answer(plan, run_plan(plan, L), L).cards}
    assert by["customers"].vals["T"] == 60.3 and by["customers"].vals["B"] == 47.6
    assert by["season"].vals["R"] == 1.6
    assert (by["location"].vals["r"], by["location"].vals["N"]) == (4, 71)
    assert by["week"].vals["W"] == 34.3 and by["time"].grade == "점심 집중형"
