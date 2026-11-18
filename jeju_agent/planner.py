"""질문 → 슬롯(지역·업종·대상·지표·관점) → 분석 계획과 필요한 데이터 목록.

키(LLM) 없이도 동작하는 규칙 기반 해석기. LLM 모드에서는 LLM이 같은 Slots 구조를 채우고,
이후 계획·분석은 동일한 코드가 수행한다(결과 재현성 확보).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .alternatives import scope_notes
from .synth import get_table, ref_rows

PURPOSES = ["사업계획서·창업", "가게·회사 운영", "현황자료·보고서", "논문·연구"]
STAGES_KO = {"예비창업자": "아직 창업 전(예비창업자)", "1년미만": "창업 1년 미만", "2년미만": "창업 2년 미만",
             "3년미만": "창업 3년 미만", "5년미만": "창업 5년 미만", "7년미만": "창업 7년 미만", "10년미만": "창업 10년 미만"}

# 일상어 → 카드 데이터 업종명(1-08 등 42개 업종)
BIZ_SYNONYMS = {
    "카페": "비알콜 음료점업", "커피": "비알콜 음료점업", "찻집": "비알콜 음료점업", "디저트": "비알콜 음료점업",
    "식당": "한식 음식점업", "한식": "한식 음식점업", "밥집": "한식 음식점업", "고깃집": "한식 음식점업",
    "흑돼지": "한식 음식점업", "횟집": "한식 음식점업", "국밥": "한식 음식점업",
    "중식": "중식 음식점업", "중국집": "중식 음식점업", "일식": "일식 음식점업", "초밥": "일식 음식점업",
    "양식": "서양식 음식점업", "레스토랑": "서양식 음식점업", "파스타": "서양식 음식점업",
    "피자": "피자, 햄버거, 샌드위치 및 유사 음식점업", "햄버거": "피자, 햄버거, 샌드위치 및 유사 음식점업",
    "술집": "기타 주점업", "호프": "기타 주점업", "주점": "기타 주점업", "포차": "기타 주점업",
    "빵집": "빵 및 과자류 소매업", "베이커리": "빵 및 과자류 소매업",
    "편의점": "체인화 편의점", "마트": "슈퍼마켓", "슈퍼": "슈퍼마켓",
    "호텔": "호텔업", "모텔": "여관업", "펜션": "여관업", "게스트하우스": "여관업", "게하": "여관업", "민박": "여관업",
    "해장국": "한식 음식점업", "국수": "한식 음식점업", "고기국수": "한식 음식점업", "브런치": "서양식 음식점업",
    "콘도": "휴양콘도 운영업", "리조트": "휴양콘도 운영업",
    "렌터카": "자동차 임대업", "렌트카": "자동차 임대업", "기념품": "관광 민예품 및 선물용품 소매업",
    "화장품": "화장품 및 방향제 소매업", "골프": "골프장 운영업", "택시": "택시 운송업", "주유소": "차량용 주유소 운영업",
    "여행사": "여행사업", "마사지": "마사지업", "목욕탕": "욕탕업", "사우나": "욕탕업",
}
# 여러 업종을 한 말로 부르는 경우(예: '숙박' = 호텔·여관(펜션·게하)·콘도)
BIZ_GROUPS = {
    "숙박": ["호텔업", "여관업", "휴양콘도 운영업"], "숙소": ["호텔업", "여관업", "휴양콘도 운영업"],
    "음식점": ["한식 음식점업", "중식 음식점업", "일식 음식점업", "서양식 음식점업", "기타 외국식 음식점업"],
    "외식": ["한식 음식점업", "중식 음식점업", "일식 음식점업", "서양식 음식점업", "기타 외국식 음식점업",
             "비알콜 음료점업"],
}
# 자주 쓰는 제주 지명·관광지 → 법정동(명세서 1-08의 73개 법정동 이름). 확실한 것만 넣는다.
PLACE_ALIASES = {
    "협재": ["한림읍"], "금능": ["한림읍"], "한림": ["한림읍"], "곽지": ["애월읍"], "한담": ["애월읍"],
    "함덕": ["조천읍"], "조천": ["조천읍"], "월정": ["구좌읍"], "김녕": ["구좌읍"], "세화": ["구좌읍"], "평대": ["구좌읍"],
    "성산일출봉": ["성산읍"], "섭지코지": ["성산읍"], "광치기": ["성산읍"], "성산": ["성산읍"], "표선": ["표선면"],
    "모슬포": ["대정읍"], "가파도": ["대정읍"], "마라도": ["대정읍"], "대정": ["대정읍"], "산방산": ["안덕면"],
    "사계": ["안덕면"], "화순": ["안덕면"], "안덕": ["안덕면"], "위미": ["남원읍"], "남원": ["남원읍"],
    "중문관광단지": ["색달동", "중문동"], "우도": ["우도면"], "추자": ["추자면"], "한경": ["한경면"], "고산": ["한경면"],
    "신창": ["한경면"], "판포": ["한경면"], "이호테우": ["이호일동"], "제주공항": ["용담이동"], "공항": ["용담이동"], "동문시장": ["이도일동"],
    "올레시장": ["서귀동"], "신제주": ["연동", "노형동"], "서귀포 시내": ["서귀동"], "탑동": ["삼도이동"],
}
SEGMENTS = {  # 일상어 → (컬럼, 값들, 표시명)
    "관광객": ("tour_type", ["개별", "단체"], "관광객(개별+단체)"),
    "여행객": ("tour_type", ["개별", "단체"], "관광객(개별+단체)"),
    "단체 관광객": ("tour_type", ["단체"], "단체 관광객"), "단체관광": ("tour_type", ["단체"], "단체 관광객"),
    "외지인": ("tour_type", ["개별", "단체"], "관광객(개별+단체)"), "육지 손님": ("tour_type", ["개별", "단체"], "관광객(개별+단체)"),
    "도민": ("tour_type", ["도민"], "도민"),
    "외국인": ("user_type", ["중국", "일본", "동남아", "기타외국"], "외국인"),
    "중국인": ("user_type", ["중국"], "중국인"),
    "일본인": ("user_type", ["일본"], "일본인"),
}
MEASURES = [("매출", "use_amt"), ("금액", "use_amt"), ("돈", "use_amt"), ("결제", "use_cnt"), ("건수", "use_cnt"),
            ("손님", "user_cnt"), ("고객", "user_cnt"), ("이용자", "user_cnt"), ("사람", "user_cnt")]
VIEW_WORDS = {
    "share": ["비중", "비율", "몇 %", "몇%", "차지", "얼마나"],
    "trend": ["추이", "추세", "변화", "월별", "성수기", "비수기", "계절", "늘", "줄"],
    "weekday": ["요일", "주말", "평일"],
    "timeslot": ["시간대", "몇 시", "점심", "저녁", "오전", "오후", "밤"],
    "rank": ["어디", "어느 동", "어느 지역", "순위", "가장 많", "top", "TOP", "상위"],
    "compare": ["평균", "대비", "비교", "다른 지역", "보다"],
}
WEEK_ORDER = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
SLOT_ORDER = ["오전", "점심", "오후", "저녁", "밤"]


@dataclass
class Slots:
    question: str = ""
    purpose: str = ""
    regions: list[str] = field(default_factory=list)       # 법정동
    city: list[str] = field(default_factory=list)          # 시 단위로 물을 때(서귀포·제주시) — 법정동을 모를 때만
    business: list[str] = field(default_factory=list)      # 카드 업종명
    biz_label: str = ""                                    # 여러 업종을 묶어 부른 말(예: 숙박)
    segment: tuple | None = None                           # (col, values, label)
    measure: str = "use_amt"
    views: list[str] = field(default_factory=list)
    unknown_words: list[str] = field(default_factory=list)


@dataclass
class Step:
    tool: str
    table_id: str
    params: dict
    why: str


@dataclass
class DataRequest:
    table_id: str
    table_name: str
    export_ok: bool
    columns: list[str]
    conditions: list[str]
    why: str


@dataclass
class Plan:
    slots: Slots
    steps: list[Step]
    requests: list[DataRequest]
    notes: list[str]
    scope_notes: list[str] = field(default_factory=list)   # 데이터 범위 밖 질문 안내(제주 밖 비교 등)
    focus_label: str = ""                                   # 화면·결론에 쓰는 이름(예: 애월읍 카페)


CITY_WORDS = {"서귀포시": "서귀포시", "서귀포": "서귀포시", "제주시": "제주시"}   # '제주'만 쓰면 섬 전체
AMBIGUOUS_BASES = {"해안"}   # '해안도로', '풍차해안'처럼 일상어와 겹치는 동 이름 앞부분은 '해안동'으로 써야만 인정


def _region_aliases(cat: dict) -> dict[str, list[str]]:
    bjds = [r[0] for r in ref_rows(get_table(cat, "1-08"), "법정동")]
    alias: dict[str, list[str]] = {}
    for b in bjds:
        alias.setdefault(b, []).append(b)
        base = re.sub(r"(일동|이동|삼동|동|읍|면)$", "", b)
        if len(base) >= 2 and base not in AMBIGUOUS_BASES:
            alias.setdefault(base, []).append(b)
            alias.setdefault(base + "동", []).append(b)
    return {k: sorted(set(v)) for k, v in alias.items()}


def parse(question: str, cat: dict, purpose: str = "") -> Slots:
    q = question.strip()
    s = Slots(question=q, purpose=purpose)
    for key in sorted(PLACE_ALIASES, key=len, reverse=True):   # '서귀포 시내'·'올레시장' 같은 구체 지명 먼저
        if key in q:
            for b in PLACE_ALIASES[key]:
                if b not in s.regions:
                    s.regions.append(b)
            q = q.replace(key, " ")
    if re.search(r"중문(?![동관])", q):              # '중문'만 말하면 중문관광단지 일대(호텔 대부분이 색달동에 있음)
        s.regions += [b for b in ("중문동", "색달동", "대포동") if b not in s.regions]
        q = re.sub(r"중문(?![동관])", " ", q)
    for key in sorted(CITY_WORDS, key=len, reverse=True):      # '서귀포'는 서귀동이 아니라 서귀포시 전체
        if key in q:
            if CITY_WORDS[key] not in s.city:
                s.city.append(CITY_WORDS[key])
            q = q.replace(key, " ")
    aliases = _region_aliases(cat)
    for key in sorted(aliases, key=len, reverse=True):
        if key in q and not any(key in r for r in s.regions):
            for b in aliases[key]:
                if b not in s.regions:
                    s.regions.append(b)
            q_masked = q.replace(key, " ")
            q = q_masked
    if s.regions:
        s.city = []                                            # 동네를 찾았으면 동네 기준

        def _at(r):                                            # 질문에 나온 순서대로(비교할 때 왼쪽부터)
            hits = [question.find(x) for x in (r, r[:-1]) if len(x) >= 2 and x in question]
            return min(hits) if hits else 999
        s.regions.sort(key=_at)
    biz_names = [r[1] for r in ref_rows(get_table(cat, "1-08"), "업종")]
    for name in biz_names:
        if name in question and name not in s.business:
            s.business.append(name)
    for word, names in BIZ_GROUPS.items():
        if word in question and not s.business:
            s.business += [n for n in names if n not in s.business]
            s.biz_label = word
    for word, name in BIZ_SYNONYMS.items():
        if word in question and name not in s.business:
            s.business.append(name)
    for word in sorted(SEGMENTS, key=len, reverse=True):     # 긴 말 먼저('단체 관광객'이 '관광객'보다 먼저)
        if word in question:
            s.segment = SEGMENTS[word]
            break
    for word, m in MEASURES:
        if word in question:
            s.measure = m
            break
    question_cmp = any(w in question for w in (" vs ", "VS", "어디가 나", "어디가 좋", "어디가 더", "어느 쪽", "어느 곳",
                                               "어느 동네", "중에 어디", "중 어디", "둘 중"))   # 비교를 돌려 말한 표현
    found = []                                       # 질문에 먼저 나온 관점부터(카드 순서가 이 순서를 따름)
    for view, words in VIEW_WORDS.items():
        pos = [question.find(w) for w in words if w in question]
        if pos:
            found.append((min(pos), view))
    s.views.extend(v for _, v in sorted(found))
    if question_cmp and "compare" not in s.views:
        s.views.append("compare")
    if s.segment and "share" not in s.views:
        s.views.insert(0, "share")
    return s


def _request(cat, tid, slots: Slots, extra_cols: list[str], why: str) -> DataRequest:
    t = get_table(cat, tid)
    cond = []
    if slots.regions and any(c["name"] == "bjd" for c in t["columns"]):
        cond.append(f"법정동(bjd) = {', '.join(slots.regions)}  (비교용으로는 전체 지역 필요)")
    elif slots.city:
        cond.append(f"시군구 = {', '.join(slots.city)}  (비교용으로는 전체 지역 필요)")
    if slots.business:
        cond.append(f"업종명(biz_nm) = {', '.join(slots.business)}")
    cond.append("기간: 최근 12개월 이상 권장(전년 같은 달 비교는 24개월)")
    base_cols = ["base_year_month", "bjd", "biz_nm", "tour_type", "user_type", "use_amt", "use_cnt", "user_cnt"]
    cols = [c["name"] for c in t["columns"] if c["name"] in set(base_cols + extra_cols)]
    return DataRequest(tid, t["name"], t["raw_export_allowed"], cols, cond, why)


BIZ_SHORT = {v: k for k, v in reversed(list(BIZ_SYNONYMS.items()))}
BIZ_SHORT.update({"비알콜 음료점업": "카페", "한식 음식점업": "한식당", "여관업": "펜션·게스트하우스",
                  "호텔업": "호텔", "휴양콘도 운영업": "콘도·리조트", "체인화 편의점": "편의점",
                  "기타 주점업": "주점", "자동차 임대업": "렌터카", "골프장 운영업": "골프장",
                  "일식 음식점업": "일식당", "중식 음식점업": "중식당", "서양식 음식점업": "양식당"})


def _short_biz(business: list[str], label: str = "") -> str:
    if label:
        return label
    for word, names in BIZ_GROUPS.items():
        if business and set(business) == set(names):
            return word
    return "·".join(BIZ_SHORT.get(b, b) for b in business[:2])


def _short_region(regions: list[str]) -> str:
    if not regions:
        return ""
    if set(regions) == {"중문동", "색달동", "대포동"}:
        return "중문 일대"
    bases = list(dict.fromkeys(re.sub(r"(일동|이동|삼동)$", "동", r) for r in regions))
    if len(bases) == 1:                       # 용담일동·용담이동·용담삼동 → 용담동
        return bases[0]
    return "·".join(bases) if len(bases) <= 2 else f"{bases[0]} 외 {len(bases) - 1}곳"


def make_plan(slots: Slots, cat: dict) -> Plan:
    steps: list[Step] = []
    reqs: list[DataRequest] = []
    notes: list[str] = []
    focus = {}
    if slots.regions:
        focus["bjd"] = slots.regions
    elif slots.city:
        focus["city"] = slots.city
    if slots.business:
        focus["biz_nm"] = slots.business
    base = {"biz_nm": slots.business} if slots.business else None
    # 요일(1-12)·시간대(1-14) 표에는 city 열이 없다 → 시 단위 질문은 그 시의 법정동 목록으로 거른다
    focus_bjd = dict(focus)
    if "city" in focus_bjd:
        from .synth import _city_of
        emd = [r[1] for r in ref_rows(get_table(cat, "4-11"), "행정동")]
        dongs = [r[0] for r in ref_rows(get_table(cat, "1-08"), "법정동")]
        cities = focus_bjd.pop("city")
        focus_bjd["bjd"] = [d for d in dongs if _city_of(d, emd) in cities]
    m = slots.measure
    biz_short = _short_biz(slots.business, slots.biz_label)
    place = _short_region(slots.regions) or "·".join(slots.city)
    focus_label = " ".join(x for x in [place, biz_short] if x) or "관심 대상"
    base_label = f"제주 전체 {biz_short}".strip() if biz_short else "제주 전체"
    labels = {"focus_label": focus_label, "base_label": base_label}
    handled = {"share", "trend", "rank", "weekday", "timeslot", "compare"}
    full_report = (slots.purpose in ("사업계획서·창업", "가게·회사 운영", "현황자료·보고서") or not slots.views
                   or not set(slots.views) & handled)

    if not slots.regions and not slots.city and "rank" not in slots.views:
        notes.append("지역을 찾지 못했습니다. 동·읍·면 이름(예: 애월읍, 노형동)을 넣으면 더 정확합니다.")
    if not slots.business:
        notes.append("업종을 찾지 못했습니다. 업종(예: 카페, 한식당)을 넣으면 더 정확합니다.")

    card = "1-08"
    if len(slots.regions) >= 2 and "compare" in slots.views:      # '연동이랑 노형동 비교' → 합치지 말고 나란히
        seg = slots.segment or ("tour_type", ["개별", "단체"], "관광객(개별+단체)")
        steps.append(Step("region_compare", card, {"regions": list(slots.regions), "measure": m, "seg_col": seg[0],
                                                   "seg_values": seg[1], "filters": base, "label": seg[2]},
                          "동네끼리 손님 구성·시장 크기·계절을 나란히 비교"))
    if slots.segment and ("share" in slots.views or full_report):
        col, vals, label = slots.segment
        steps.append(Step("compare_share", card, {"focus": focus, "seg_col": col, "seg_values": vals,
                                                  "measure": m, "base": base, "label": label, **labels},
                          f"{label} 비중을 제주 전체 같은 업종과 비교"))
    elif full_report or "compare" in slots.views:          # '다른 동네와 비교'도 제주 평균 대비 몫부터
        steps.append(Step("compare_share", card, {"focus": focus, "seg_col": "tour_type", "seg_values": ["개별", "단체"],
                                                  "measure": m, "base": base, "label": "관광객(개별+단체)", **labels},
                          "관광객 매출 비중을 제주 전체 같은 업종과 비교"))
    if "trend" in slots.views or full_report:
        steps.append(Step("trend", card, {"time_col": "base_year_month", "measure": m, "filters": focus},
                          "월별 매출 흐름과 성수기·비수기"))
    if "rank" in slots.views or "compare" in slots.views or (full_report and slots.business):
        steps.append(Step("top_n", card, {"by": "bjd", "measure": m, "n": 10, "filters": base,
                                          "highlight": list(slots.regions)},
                          "같은 업종에서 매출이 큰 지역 순위(입지 비교)"))
    if "share" in slots.views and not slots.segment:
        steps.append(Step("share_by", card, {"by": "user_type", "measure": m, "filters": focus},
                          "이용자 구분별 비중"))
    if "weekday" in slots.views or full_report:
        reqs.append(_request(cat, "1-12", slots, ["week"], "요일별 카드 매출"))
        steps.append(Step("pattern", "1-12", {"cat_col": "week", "measure": m, "order": WEEK_ORDER, "filters": focus_bjd,
                                              "exclude": ["공휴일"]},
                          "요일별 매출 분포(영업일·인력 계획)"))
    if "timeslot" in slots.views or full_report:
        from .tools import _slot_hours
        hours = {r[0]: _slot_hours(r[1]) for r in ref_rows(get_table(cat, "1-14"), "시간대") if len(r) > 1}
        reqs.append(_request(cat, "1-14", slots, ["time"], "시간대별 카드 매출"))
        steps.append(Step("pattern", "1-14", {"cat_col": "time", "measure": m, "order": SLOT_ORDER, "filters": focus_bjd,
                                              "hours": {k: v for k, v in hours.items() if v}},
                          "시간대별 매출 분포(영업시간 계획)"))
    st_ = store_step(slots, full_report)
    if st_:
        steps.append(st_)
    if any(st.table_id == card for st in steps):
        reqs.insert(0, _request(cat, card, slots, [], "지역·업종별 월간 카드 매출과 이용자 구분(관광객/도민)"))
    return Plan(slots, steps, reqs, notes, scope_notes(slots.question), focus_label=focus_label)


def visitor_steps(cities: list[str]) -> list[Step]:
    """공개 방문자 수(한국관광공사, 최근 12개월): 그 시의 외지인 방문자 월별 흐름과 요일 분포."""
    from .datagokr import VISIT_ID
    f = {"tou_div": ["외지인"], **({"sigungu": list(cities)} if cities else {})}
    return [Step("trend", VISIT_ID, {"time_col": "base_year_month", "measure": "tou_num", "filters": f},
                 "[공개 데이터] 최근 외지인 방문자 월별 흐름 — 한국관광공사"),
            Step("pattern", VISIT_ID, {"cat_col": "daywk", "measure": "tou_num", "order": WEEK_ORDER, "filters": f},
                 "[공개 데이터] 최근 외지인 방문자 요일 분포 — 한국관광공사")]


def store_step(slots: Slots, full_report: bool = True) -> Step | None:
    """공개 상가정보(동봉)로 같은 업종 가게 수 순위 — 업종이 상가정보 업종과 이어질 때만."""
    from .stores import MID_TO_CARD, SMALL_TO_CARD, STORES_ID
    known = set(SMALL_TO_CARD.values()) | set(MID_TO_CARD.values())
    biz = [b for b in slots.business if b in known]
    if not biz or not (full_report or "rank" in slots.views or slots.regions):
        return None
    f = {"card_biz": biz, **({"sigungu": list(slots.city)} if slots.city and not slots.regions else {})}
    return Step("store_rank", STORES_ID, {"by": "bjd", "count": "store_cnt", "n": 10, "filters": f,
                                         "highlight": list(slots.regions)},
                "[공개 데이터] 같은 업종 가게 수(경쟁) — 소상공인 상가정보")


# ── 제주데이터허브 공개 데이터(597)로 같은 질문을 '거칠게' 보기 ─────────────────
PUBLIC_ID = "허브-597"
BIZ_TO_MARKET = {  # 카드 42업종 → 공개 데이터 업종 8종(교통, 기타, 소매, 쇼핑, 숙박, 유흥, 문화/레져, 식음료)
    "한식 음식점업": "식음료", "중식 음식점업": "식음료", "일식 음식점업": "식음료", "서양식 음식점업": "식음료",
    "기타 외국식 음식점업": "식음료", "피자, 햄버거, 샌드위치 및 유사 음식점업": "식음료", "비알콜 음료점업": "식음료",
    "빵 및 과자류 소매업": "식음료", "일반유흥 주점업": "유흥", "기타 주점업": "유흥",
    "호텔업": "숙박", "여관업": "숙박", "휴양콘도 운영업": "숙박",
    "버스 운송업": "교통", "택시 운송업": "교통", "내항 여객 운송업": "교통", "정기 항공 운송업": "교통",
    "자동차 임대업": "교통", "차량용 주유소 운영업": "교통", "차량용 가스 충전업": "교통",
    "면세점": "쇼핑", "화장품 및 방향제 소매업": "쇼핑", "관광 민예품 및 선물용품 소매업": "쇼핑",
    "슈퍼마켓": "소매", "체인화 편의점": "소매", "기타 대형 종합 소매업": "소매", "기타음식료품위주종합소매업": "소매",
    "골프장 운영업": "문화/레져", "그외 기타 스포츠시설 운영업": "문화/레져", "기타 수상오락 서비스업": "문화/레져",
    "스포츠 및 레크레이션 용품 임대업": "문화/레져", "여행사업": "문화/레져",
}


def make_public_plan(slots: Slots, cat: dict) -> Plan:
    """센터 데이터 없이 공개 데이터로 볼 수 있는 범위: 시군구 × 도심/읍면 × 업종 8종 × 관광객/도민.

    실제 597 데이터에는 업종 '전체' 합계 행이 없다(2016.09~2018.12 확인). 업종을 모르면 업종 조건을 걸지 않고
    모든 업종을 더한다. 혹시 '전체' 행이 들어 있어도 불러올 때 빼므로(loader.normalize_values) 두 번 세지 않는다.
    """
    from .synth import _city_of
    emd_names = [r[1] for r in ref_rows(get_table(cat, "4-11"), "행정동")]
    t = get_table(cat, PUBLIC_ID)
    focus: dict[str, list[str]] = {}
    notes = ["공개 데이터는 제주시·서귀포시와 도심/읍면, 업종 8종 단위까지만 나뉘고 기간도 "
             f"{t.get('period', '').split('(')[0].strip() or '과거 일부 기간'}입니다. "
             "동네(읍면동)·세부 업종·최근 달은 센터 데이터에서 볼 수 있습니다."]
    if slots.regions:
        focus["sigungu"] = sorted({_city_of(b, emd_names) for b in slots.regions})
        focus["cityGubun"] = sorted({"읍면" if b.endswith(("읍", "면")) else "도심" for b in slots.regions})
    elif slots.city:
        focus["sigungu"] = list(slots.city)
    markets = sorted({BIZ_TO_MARKET[b] for b in slots.business if b in BIZ_TO_MARKET})
    if markets:
        focus["marketType"] = markets
    base = {"marketType": markets} if markets else None
    place = " ".join(focus.get("sigungu", []))
    if focus.get("cityGubun"):
        place += " " + "·".join(focus["cityGubun"]) + " 지역"
    mk = "·".join(markets)
    labels = {"focus_label": " ".join(x for x in (place.strip(), mk) if x) or "제주 전체",
              "base_label": f"제주 전체 {mk}".strip()}
    m = "useCost"
    steps = [
        Step("compare_share", PUBLIC_ID, {"focus": focus, "seg_col": "userType", "seg_values": ["내국인관광객"],
                                         "measure": m, "base": base, "label": "내국인 관광객", **labels},
             "[공개 데이터] 내국인 관광객 매출 비중(시 단위)"),
        Step("trend", PUBLIC_ID, {"time_col": "dtYearMonth", "measure": m, "filters": focus},
             "[공개 데이터] 월별 매출 흐름(시 단위)"),
        Step("share_by", PUBLIC_ID, {"by": "ageGroup", "measure": m,
                                    "filters": {**focus, "userType": ["내국인관광객"]}},
             "[공개 데이터] 내국인 관광객 연령대별 비중"),
        Step("group_share", PUBLIC_ID, {"groups": ["sigungu", "cityGubun"], "seg_col": "userType",
                                       "seg_values": ["내국인관광객"], "measure": m, "filters": base},
             "[공개 데이터] 시·도심/읍면 4그룹의 내국인 관광객 비중"),
        Step("season_by", PUBLIC_ID, {"time_col": "dtYearMonth", "by": "userType", "measure": m, "filters": focus},
             "[공개 데이터] 관광객·도민 매출의 계절 차이"),
    ]
    st_ = store_step(slots)
    if st_:
        steps.append(st_)
    steps += visitor_steps(focus.get("sigungu") or list(slots.city))
    from .hub_district import DISTRICT_ID, closest_district
    steps.append(Step("district_profile", DISTRICT_ID,
                      {"focus": closest_district(list(slots.regions), lambda b: _city_of(b, emd_names))},
                      "[공개 데이터] 지구 유형별 요일·시간대·손님 구성 — 제주데이터허브"))
    req = DataRequest(PUBLIC_ID, t["name"], True, [c["name"] for c in t["columns"]],
                      ["제주데이터허브 Open API(프로젝트키 필요) 또는 받아 둔 CSV"], "센터 방문 전 공개 데이터로 미리 보기")
    return Plan(slots, steps, [req], notes, [])


def map_place(phrase: str, cat: dict) -> list[str]:
    for key in sorted(PLACE_ALIASES, key=len, reverse=True):
        if key in phrase:
            return PLACE_ALIASES[key]
    aliases = _region_aliases(cat)
    for key in sorted(aliases, key=len, reverse=True):
        if key in phrase:
            return aliases[key]
    return []


def map_business(phrase: str, cat: dict) -> list[str]:
    biz_names = [r[1] for r in ref_rows(get_table(cat, "1-08"), "업종")]
    hits = [b for b in biz_names if b in phrase]
    hits += [v for k, v in BIZ_SYNONYMS.items() if k in phrase and v not in hits]
    return hits


def parse_hybrid(question: str, cat: dict, purpose: str = "", use_llm: bool = True) -> tuple[Slots, str]:
    """규칙 해석이 비어 있는 칸만 LLM으로 채운다. LLM은 '표현'만 뽑고, 법정동·업종 대응은 사전으로 한다."""
    s = parse(question, cat, purpose)
    if not use_llm:
        return s, "기본 모드(규칙)로 질문을 해석했습니다."
    from .llm import LLMUnavailable, extract_phrases, get_config
    cfg = get_config()
    if not cfg.enabled:
        return s, "기본 모드(규칙)로 질문을 해석했습니다."
    try:
        d = extract_phrases(question, cfg)
    except (LLMUnavailable, ValueError, KeyError) as e:
        return s, f"AI 해석을 쓰지 못해 기본 모드로 해석했습니다({e})."
    unknown = []
    if not s.regions and not s.city:
        for ph in d.get("place_phrases", []):
            city = next((CITY_WORDS[k] for k in sorted(CITY_WORDS, key=len, reverse=True) if k in ph), "")
            if city and not any(k in ph for k in PLACE_ALIASES):
                s.city += [city] if city not in s.city else []
                continue
            got = map_place(ph, cat)
            s.regions += [g for g in got if g not in s.regions]
            if not got:
                unknown.append(ph)
    if not s.business:
        for ph in d.get("business_phrases", []):
            got = map_business(ph, cat)
            s.business += [g for g in got if g not in s.business]
            if not got:
                unknown.append(ph)
    if not s.segment and d.get("segment") in SEGMENTS:
        s.segment = SEGMENTS[d["segment"]]
    if s.measure == "use_amt" and not any(w in question for w, m in MEASURES if m == "use_amt"):
        s.measure = d.get("measure", s.measure)
    for v in d.get("views", []):
        if v not in s.views:
            s.views.append(v)
    if s.segment and "share" not in s.views:
        s.views.insert(0, "share")
    s.unknown_words = unknown
    note = f"AI({cfg.model})가 질문 해석을 도왔습니다(질문 문장만 전송, 지역·업종 대응은 내장 사전으로 확인)."
    if unknown:
        note += " 확인이 필요한 표현: " + ", ".join(unknown)
    return s, note
