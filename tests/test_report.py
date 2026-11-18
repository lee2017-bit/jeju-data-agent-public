import io
import zipfile

import pytest

from jeju_agent.agent import run_plan
from jeju_agent.loader import load_center_csv
from jeju_agent.planner import make_plan, parse
from jeju_agent.report import build_report, exportable
from jeju_agent.synth import generate, load_catalog

CAT = load_catalog()


@pytest.fixture(scope="module")
def run():
    L = {t: load_center_csv(io.BytesIO(generate(t, "202601-202606", seed=5, cat=CAT).to_csv(index=False).encode()), CAT)
         for t in ("1-08", "1-12", "1-14")}
    plan = make_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    return plan, run_plan(plan, L), L


def test_export_tables_have_only_applied_aggregates(run):
    plan, outs, L = run
    for o in outs:
        if o.result is None:            # 동봉 상가정보를 넣지 않은 실행: 그 단계는 '데이터 없음'
            continue
        t = exportable(o)
        assert "use_amt" not in t.columns and "use_cnt" not in t.columns and "user_cnt" not in t.columns


def test_bundle_contents(run, tmp_path):
    plan, outs, L = run
    b = build_report(plan, outs, L, tmp_path, purpose="시장 분석", synthetic=True)
    assert len(b.charts) == 5 and all(c.suffix == ".png" for c in b.charts)
    assert b.answer is not None and b.answer.headline.startswith("[체험]")
    names = zipfile.ZipFile(b.zip).namelist()
    assert "분석보고서.docx" in names and "반출신청서_초안.txt" in names
    assert not any(n.endswith((".csv", ".xlsx")) for n in names)   # 텍스트·엑셀 원자료는 패키지에 넣지 않는다
    req = b.request_txt.read_text(encoding="utf-8")
    assert "분석보고서.docx" in req and "카드 이용 현황(읍면동)_v02" in req
