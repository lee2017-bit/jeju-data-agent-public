"""센터 전용 수치 표시(1번)와 데이터 범위 밖 질문 안내.

근거: docs/03_why-visit-center.md, docs/research/2026-11-02_visit-value_alternatives.md
- 한국관광 데이터랩: 제주시·서귀포시 2개 단위, 현지인/외지인(내국인), 2020~
- 소상공인365: 행정동 단위 업소 수·점포당 매출·유동인구, 관광객 구분 없음(추정)
- 제주도 월간 소비동향(BC카드): 제주 전체, 내·외국인 — 매달 무료 발표
이 앱을 쓰는 사람은 이미 센터에 와 있다. 그래서 '온라인으로도 볼 수 있다'는 안내는 하지 않고(11/15 결정),
센터 데이터로 답할 수 없는 질문(제주 밖 비교 등)만 미리 알린다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Badge:
    center_only: bool
    reason: str


def badge_for(tool: str, table_id: str, params: dict) -> Badge:
    if table_id == "허브-지구":
        return Badge(False, "공개 데이터(제주데이터허브): 지구 유형 5종 단위·2016.09~2017.11 자료입니다. "
                            "동네·업종 단위 요일·시간대는 센터 데이터로만 볼 수 있습니다.")
    if table_id.startswith("허브-"):
        return Badge(False, "공개 데이터(제주데이터허브): 시 단위·업종 8종·2016~2018년 자료입니다. "
                            "동네 단위·최근 기간은 센터 데이터로 봅니다.")
    if table_id.startswith("공개-"):
        return Badge(False, "공개 데이터(공공데이터포털) 실제 값입니다. 앱에 들어 있어 따로 받을 필요가 없습니다.")
    focus = params.get("focus") or params.get("filters") or {}
    has_dong = "bjd" in focus or params.get("by") == "bjd" or bool(params.get("regions"))
    seg_col = params.get("seg_col")
    reasons = []
    if seg_col == "tour_type":
        reasons.append("관광객(개별·단체)과 도민을 나눈 카드 매출")
    if seg_col == "user_type" or params.get("by") == "user_type":
        reasons.append("외국인 국적 그룹별 카드 매출")
    if table_id == "1-14" and has_dong:
        reasons.append("동 × 업종 × 시간대 매출")
    if table_id == "1-12" and has_dong:
        reasons.append("동 × 업종 × 요일 매출")
    if has_dong and table_id.startswith("1-"):
        reasons.append("읍면동 단위 카드 매출(데이터랩은 제주시·서귀포시 2개 단위)")
    if table_id in {"1-18", "1-19", "1-24", "1-26", "1-27", "1-28", "1-29"}:
        reasons.append("외식업 메뉴·POS 매출")
    if reasons:
        return Badge(True, "센터에서만 나오는 수치: " + ", ".join(dict.fromkeys(reasons)))
    return Badge(False, "")


def scope_notes(question: str) -> list[str]:
    """센터 데이터로 답할 수 없는 질문이면 미리 알린다(대체 서비스 권유는 하지 않음)."""
    if any(w in question for w in ("전국", "서울", "부산", "다른 도시", "육지")):
        return ["제주 밖 지역과의 비교는 센터 데이터에 없어 답할 수 없습니다. 제주 안의 동네·업종끼리는 비교할 수 있습니다."]
    return []
