from jeju_agent.alternatives import badge_for, scope_notes
from jeju_agent.planner import make_plan, parse
from jeju_agent.synth import load_catalog

CAT = load_catalog()


def test_center_only_badges():
    b = badge_for("compare_share", "1-08", {"focus": {"bjd": ["애월읍"]}, "seg_col": "tour_type"})
    assert b.center_only and "관광객" in b.reason and "읍면동" in b.reason
    b = badge_for("pattern", "1-14", {"filters": {"bjd": ["노형동"], "biz_nm": ["한식 음식점업"]}})
    assert b.center_only and "시간대" in b.reason
    b = badge_for("trend", "1-08", {"filters": {"biz_nm": ["비알콜 음료점업"]}})
    assert not b.center_only and b.reason == ""   # 이미 센터에 온 사람에게 '다른 데서도 볼 수 있다'고 하지 않는다


def test_no_go_elsewhere_advice():
    """앱 사용자는 이미 센터에 와 있으므로 무료 대체 서비스를 권하지 않는다. 데이터 범위 밖 질문만 알린다."""
    for q in ("제주 카페 매출 추이가 어때?", "애월읍 카페 관광객 비중", "노형동 가게 수가 몇 개야?"):
        plan = make_plan(parse(q, CAT), CAT)
        assert plan.scope_notes == []
    notes = scope_notes("서울이랑 비교하면?")
    assert notes and "제주 밖" in notes[0] and "이용해 주세요" not in notes[0]
