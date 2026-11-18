from jeju_agent.programs import Profile
from jeju_agent.synth import load_catalog
from jeju_agent.visit_prep import from_csv, is_prep_csv, make_prep, to_csv_bytes, to_html

CAT = load_catalog()


def test_prep_roundtrip_and_html():
    p = make_prep("애월읍 카페 창업, 관광객 비중과 요일별 매출", "예비창업패키지 신청",
                  Profile(stage="예비창업자", age=34, keywords=["카페", "관광"]), CAT)
    raw = to_csv_bytes(p)
    assert is_prep_csv(raw[:200])
    back = from_csv(raw)
    assert back["question"] == p.question and back["profile"].age == 34 and back["profile"].keywords == ["카페", "관광"]
    h = to_html(p)
    assert "1-08" in h and "1-12" in h and "센터에서만" not in h.split("<h2>1.")[0]
    assert "애월읍" in h and "준비물" in h
