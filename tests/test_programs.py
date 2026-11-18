from datetime import date

from jeju_agent.programs import Profile, match, parse_item

ITEMS = [  # K-Startup 가이드 v2.0 응답 필드 형식의 예시(가상)
    {"biz_pbanc_nm": "제주 예비창업자 사업화 지원", "supt_biz_clsfc": "사업화", "supt_regin": "제주특별자치도",
     "pbanc_rcpt_bgng_dt": "2026-10-20 00:00:00", "pbanc_rcpt_end_dt": "2026-11-12 00:00:00",
     "pbanc_ntrp_nm": "제주창조경제혁신센터", "aply_trgt": "일반인", "biz_enyy": "예비창업자",
     "biz_trgt_age": "만 20세 이상 ~ 만 39세 이하, 만 40세 이상", "aply_mthd_vst_rcpt_istc": "센터 방문 접수",
     "detl_pg_url": "www.k-startup.go.kr/x?pbancSn=1", "pbanc_ctnt": "관광·외식 분야 우대"},
    {"biz_pbanc_nm": "전국 청년 창업 교육", "supt_biz_clsfc": "교육", "supt_regin": "전국",
     "pbanc_rcpt_end_dt": "2026-12-31 00:00:00", "biz_enyy": "예비창업자,1년미만",
     "biz_trgt_age": "만 20세 이상 ~ 만 39세 이하", "aply_mthd_onli_rcpt_istc": "K-Startup 온라인 접수"},
    {"biz_pbanc_nm": "서울 창업 공간", "supt_regin": "서울특별시", "pbanc_rcpt_end_dt": "2026-12-31 00:00:00",
     "biz_enyy": "예비창업자"},
    {"biz_pbanc_nm": "마감된 제주 공고", "supt_regin": "제주특별자치도", "pbanc_rcpt_end_dt": "2026-10-01 00:00:00"},
    {"biz_pbanc_nm": "제주 7년 미만 기업 판로", "supt_regin": "제주특별자치도", "pbanc_rcpt_end_dt": "2026-12-31 00:00:00",
     "biz_enyy": "3년미만,5년미만,7년미만"},
]


def test_match_filters_region_stage_deadline_and_flags_visit():
    progs = [parse_item(i) for i in ITEMS]
    got = match(progs, Profile(stage="예비창업자", age=45, keywords=["관광", "외식"]), today=date(2026, 11, 2))
    titles = [p.title for p in got]
    assert titles == ["제주 예비창업자 사업화 지원"]          # 서울·마감·연령(39세 이하)·창업기간 불일치 제외
    p = got[0]
    assert p.visit_required and p.apply_methods["방문"] == "센터 방문 접수"
    assert any("관련 업종" in r for r in p.reasons) and p.url.startswith("https://")


def test_stage_ranges():
    progs = [parse_item(i) for i in ITEMS]
    # 창업 2년 차(2년 미만)는 '1년미만' 대상 공고에는 해당하지 않고, '3·5·7년미만' 대상에는 해당
    got = match(progs, Profile(stage="2년미만", age=30), today=date(2026, 11, 2))
    assert [p.title for p in got] == ["제주 7년 미만 기업 판로"]
    got = match(progs, Profile(stage="1년미만", age=30), today=date(2026, 11, 2))
    assert {p.title for p in got} == {"전국 청년 창업 교육", "제주 7년 미만 기업 판로"}


def test_bizinfo_item_parsing_and_jeju_priority():
    from jeju_agent.programs import parse_bizinfo_item
    it = {"pblancNm": "[제주] 2026년 소상공인 고용보험료 지원 사업 공고", "jrsdInsttNm": "제주특별자치도",
          "excInsttNm": "직접수행", "pldirSportRealmLclasCodeNm": "경영", "reqstBeginEndDe": "2026-01-02 ~ 2026-12-31",
          "trgetNm": "소상공인", "reqstMthPapersCn": "제주시·서귀포시 해당 부서 방문 접수",
          "pblancUrl": "https://www.bizinfo.go.kr/x", "bsnsSumryCn": "<p>고용보험료 지원</p>"}
    p = parse_bizinfo_item(it)
    assert p.region == "제주" and p.end == "2026-12-31" and p.visit_required and p.org == "제주특별자치도"
    seoul = parse_bizinfo_item({**it, "pblancNm": "서울 청년 공고", "jrsdInsttNm": "서울특별시", "reqstMthPapersCn": "온라인"})
    nat = parse_bizinfo_item({**it, "pblancNm": "전국 공고", "jrsdInsttNm": "중소벤처기업부", "reqstBeginEndDe": "예산 소진시까지"})
    got = match([nat, seoul, p], Profile(stage="3년미만", age=45), today=date(2026, 11, 2))
    assert [g.title for g in got][0].startswith("[제주]") and all("서울" not in g.title for g in got)


def test_shop_does_not_get_food_processing_equipment_programs():
    items = [{"biz_pbanc_nm": "[제주] 2026년 5차 수산식품 가공설비 지원사업", "supt_regin": "제주특별자치도",
              "pbanc_rcpt_end_dt": "2026-12-31 00:00:00"},
             {"biz_pbanc_nm": "[제주] 2026년 식품진흥기금 융자지원 계획 공고", "supt_regin": "제주특별자치도",
              "pbanc_rcpt_end_dt": "2026-12-31 00:00:00"}]
    progs = [parse_item(i) for i in items]
    got = match(progs, Profile(stage="예비창업자", business="카페", keywords=["카페", "식품"]), today=date(2026, 11, 2))
    assert [p.title for p in got] == ["[제주] 2026년 식품진흥기금 융자지원 계획 공고"]   # 가게에 맞는 식품 공고는 남김


def test_failed_fetch_is_remembered_and_busy_fetch_does_not_block(monkeypatch, tmp_path):
    """실시간 조회가 실패하면 5분은 저장본으로(누를 때마다 30초 기다리지 않게), 받는 중이면 기다리지 않는다."""
    import json
    import threading
    from jeju_agent import programs as P
    monkeypatch.setattr(P, "SNAPSHOT", tmp_path / "programs_snapshot.json")
    (tmp_path / "programs_snapshot_X.json").write_text(json.dumps({"fetched_at": "2026-11-01", "items": []}), encoding="utf-8")
    monkeypatch.setattr(P, "_CACHE", {})
    monkeypatch.setattr(P, "_LOCKS", {})
    calls = []

    def bad(key):
        calls.append(1)
        raise OSError("timeout")
    for _ in range(3):
        _, note = P._source_list("X", bad, lambda i: i, "k", 1800)
    assert len(calls) == 1 and "저장본 사용" in note
    P._CACHE.clear()
    lock = P._LOCKS.setdefault("X", threading.Lock())
    lock.acquire()                                         # 다른 스레드가 받는 중
    try:
        _, note = P._source_list("X", bad, lambda i: i, "k", 1800, wait=False)
    finally:
        lock.release()
    assert "받는 중" in note and len(calls) == 1
