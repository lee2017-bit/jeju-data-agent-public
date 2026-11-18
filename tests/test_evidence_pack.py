import io
from datetime import date

from docx import Document

from jeju_agent.agent import run_plan
from jeju_agent.evidence_pack import build_evidence_pack, implications
from jeju_agent.loader import load_center_csv
from jeju_agent.planner import make_plan, parse
from jeju_agent.programs import Profile, match, parse_item
from jeju_agent.report import build_report
from jeju_agent.synth import generate, load_catalog

CAT = load_catalog()


def test_evidence_pack_psst(tmp_path):
    L = {t: load_center_csv(io.BytesIO(generate(t, "202601-202606", seed=5, cat=CAT).to_csv(index=False).encode()), CAT)
         for t in ("1-08", "1-12", "1-14")}
    plan = make_plan(parse("애월읍에 카페 열면 어때?", CAT, "사업계획서·창업"), CAT)
    b = build_report(plan, run_plan(plan, L), L, tmp_path, synthetic=True)
    progs = match([parse_item({"biz_pbanc_nm": "제주 예비창업 지원", "supt_regin": "제주특별자치도",
                               "pbanc_rcpt_end_dt": "2026-11-30 00:00:00", "biz_enyy": "예비창업자",
                               "aply_mthd_vst_rcpt_istc": "방문"})], Profile(), today=date(2026, 11, 2))
    path = build_evidence_pack(b, plan.slots.question, progs, synthetic=True)
    text = "\n".join(p.text for p in Document(path).paragraphs)
    for h in ("1. 문제인식", "2. 실현가능성", "3. 성장전략", "4. 팀 구성", "부록 1"):
        assert h in text
    assert "→ " in text and "사업계획서 문장 예시" in text      # 시사점·옮겨 쓸 문장
    # 옮겨 쓸 문장은 문어체 한 문장 흐름이어야 한다('구성은 … 나옵니다' 같은 어색한 조합 금지)
    ex = [p.text for p in Document(path).paragraphs if p.text.startswith("사업계획서 문장 예시")]
    assert ex and all("니다" not in e and "구성은" not in e for e in ex), ex
    assert any("결제 비중은" in e and "공략한다" in e for e in ex)
    growth = text[text.index("3. 성장전략"):text.index("4. 팀 구성")]
    assert "1차 목표 고객" in growth and "인력과 대표 메뉴" in growth and "2호점" in growth   # 6개월치라 계절 줄은 없음
    assert "자료: 가상 데이터(제주빅데이터센터 명세서" in text      # 출처 표기(가상이면 가상이라고)
    assert len(Document(path).inline_shapes) >= 4


def test_implications_are_conservative():
    assert implications({"sowhat": "점심에 일손을 모으세요."}) == ["점심에 일손을 모으세요."]
    assert implications({}) == []
