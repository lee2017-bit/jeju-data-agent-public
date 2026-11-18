import json
from datetime import date

from jeju_agent.eligibility import guess_kind, profile_from_question, rule_screen, screen
from jeju_agent.programs import Profile, Program, match


def _p(title, target="", region="제주", stage="", age="", detail="", end="2026-12-31", org="기관", field=""):
    return Program(title=title, field=field, region=region, start="", end=end, org=org, target=target, stage=stage,
                   age=age, apply_methods={}, url="", detail=detail)


def test_rule_screen_excludes_clear_mismatch():
    s = rule_screen(_p("제주 청년 창업 지원"), Profile(age=45))
    assert s.verdict == "해당 안 됨" and "45" in s.reason
    s = rule_screen(_p("여성기업 판로 지원"), Profile(age=30))
    assert s.verdict == "해당 안 됨"
    assert rule_screen(_p("여성기업 판로 지원"), Profile(age=30, traits=["여성"])).verdict != "해당 안 됨"


def test_other_region_in_target_is_filtered():
    progs = [_p("2026 동네창업학교 교육생 모집", target="충청남도 내 창업 예정인 청년 예비창업자", region="전국"),
             _p("[구리시 청년내일센터] 창업아이디어 경진대회", region="전국"),
             _p("전국 예비창업자 교육", target="예비창업자 누구나", region="전국")]
    got = match(progs, Profile(age=30), today=date(2026, 11, 3))
    assert [g.title for g in got] == ["전국 예비창업자 교육"]


def test_ai_screen_uses_only_valid_answers_and_sorts():
    progs = [_p("A 지원사업"), _p("B 세미나"), _p("C 지원사업")]
    sent = {}

    def fake_chat(messages, cfg, purpose, schema):
        sent["payload"] = json.loads(messages[1]["content"])
        return json.dumps({"results": [
            {"id": 0, "verdict": "해당 안 됨", "kind": "자금·사업화 지원", "reason": "업력 조건 불충족", "check": []},
            {"id": 1, "verdict": "해당", "kind": "행사·공모전", "reason": "누구나 참가", "check": ["참가 신청"]},
            {"id": 9, "verdict": "해당", "kind": "기타", "reason": "없는 공고", "check": []}]})

    prof = profile_from_question(Profile(age=35), ["카페"], "제주시")
    res, note = screen(progs, prof, use_ai=True, chat=fake_chat)
    assert [r.program.title for r in res][0] == "B 세미나" and res[0].by == "AI" and res[0].kind == "행사·공모전"
    assert res[-1].verdict == "해당 안 됨"
    assert any(r.by.startswith("규칙") for r in res)                 # AI가 빠뜨린 공고(C)는 규칙 판정
    assert "카페" in " ".join(sent["payload"]["신청자 조건"]) and "AI" in note
    assert prof.keywords[:2] == ["카페", "외식"] and prof.city == "제주시"


def test_ai_failure_falls_back_to_rules():
    def broken(*a, **k):
        raise RuntimeError("down")
    res, note = screen([_p("A 지원사업")], Profile(), use_ai=True, chat=broken)
    assert res[0].by.startswith("규칙") and "규칙으로" in note


def test_guess_kind():
    assert guess_kind(_p("2026 M&A 전략 세미나")) == "행사·공모전"
    assert guess_kind(_p("소상공인 고용보험료 지원")) == "자금·사업화 지원"


def test_shop_founder_does_not_get_tech_investment_or_ads():
    """2026-11-03 실측: 카페 예비창업자에게 AI 플랫폼·위치정보 교육·TIPS·투자·입주·전자책 강의·해외 판촉전이 나왔다."""
    noise = [_p("[ 모 집 ] GVC AI Platform Startup Enabling Program 및 스마트워크·쇼핑몰", region="전국"),
             _p("2026년 위치정보 보호조치 교육 (7차)", region="전국"),
             _p("2026년 팁스(TIPS) 창업기업 지원계획 수정 공고", region="전국"),
             _p("[한국투자액셀러레이터] 바른동행 4차 모집｜선발 시 최대 5억원 투자", region="전국"),
             _p("2026년 제4차 관악S밸리 창업 공간 신규 입주기업 모집 공고", region="전국"),
             _p("[온라인·무료] 코딩·사업자 없이 여는 내 강의·전자책 판매 사이트", region="전국"),
             _p("2026년 하얼빈 빙설축제 유망 소비재 판촉전 모집 공고", region="전국"),
             _p("[창업] 합격하는 창업 사업계획서 실전", region="전국", org="마포청년창업취업지원센터"),
             _p("2026 의왕시 청년e-Room 창업아이디어 공모전", region="전국"),
             _p("한동 알럼나이 파운더스", region="전국", target="한동대학교 출신 창업가"),
             _p("제주 창업-BuS 프로그램 참여기업 모집", detail="직접 투자, TIPS 추천 검토, 액셀러레이팅 지원"),
             _p("스타트업 육성 공간", region="전국", field="시설ㆍ공간ㆍ보육")]
    keep = [_p("2026년 소상공인 투자연계 지원사업 립스(LIPS) 프로그램", region="전국"),
            _p("2026년 여성기업 육성사업 공고", region="전국", detail="교육·액셀러레이팅"),
            _p("제주 예비창업자 사업화 지원"),
            _p("전국 예비창업자 창업 교육", target="예비창업자 누구나", region="전국")]
    prof = profile_from_question(Profile(stage="예비창업자", age=35), ["카페"], "제주시")
    stats: dict = {}
    got = [g.title for g in match(noise + keep, prof, today=date(2026, 11, 3), stats=stats)]
    assert got and set(got) == {k.title for k in keep}, got
    assert stats["dropped"]["기술·투자·입주 중심 공고(가게 창업과 무관)"] >= 9


def test_rule_says_해당_only_with_a_link_to_the_shop():
    prof = profile_from_question(Profile(stage="예비창업자", age=35, traits=["청년(만 39세 이하)"]), ["카페"], "제주시")
    generic = _p("예비 초기 스타트업 교육", region="전국", stage="예비창업자", age="만 39세 이하", target="예비창업자")
    s = rule_screen(generic, prof)
    assert s.verdict == "확인 필요" and "카페도 지원 대상인지" in s.check
    food = _p("예비창업자 외식 창업 교육", region="전국", stage="예비창업자", age="만 39세 이하", target="예비창업자")
    assert rule_screen(food, prof).verdict == "해당"
    no_pre = _p("혁신창업기업 모집", region="전국", detail="업력 7년 이내 중소기업 예비창업자 지원불가")
    assert rule_screen(no_pre, prof).verdict == "해당 안 됨"
