"""지원사업 자격 확인: 내 조건 × 공고문 → '해당 / 확인 필요 / 해당 안 됨'과 이유.

1) 규칙(키 없이도 동작): programs.match가 지역·창업기간·나이·마감으로 먼저 거른다.
   남은 공고는 제목·신청 대상 문장의 '청년·여성·장애인·소상공인·예비창업자' 같은 말로 간단히 판정한다(추정).
2) AI(선택): 공고의 제목·대상·내용 문장과 내가 입력한 조건만 보내 판정과 이유를 받는다.
   센터 데이터·분석 결과는 보내지 않는다. 공고문에 없는 조건을 지어내지 않게 하고, 근거가 없으면 '확인 필요'로 두게 한다.
   AI 답에 없는 공고·이상한 판정은 버리고 규칙 판정을 쓴다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .llm import LLMUnavailable
from .programs import Profile, Program

VERDICTS = ["해당", "확인 필요", "해당 안 됨"]
SHOP_TARGET_WORDS = ("소상공인", "자영업", "골목", "상점", "전통시장")
KINDS = ["자금·사업화 지원", "교육·컨설팅", "행사·공모전", "투자·입주", "기타"]


@dataclass
class Screened:
    program: Program
    verdict: str
    reason: str
    check: list[str] = field(default_factory=list)
    by: str = "규칙(추정)"
    kind: str = ""


def guess_kind(p: Program) -> str:
    t = p.title + " " + p.field
    if re.search(r"행사|세미나|포럼|설명회|데모데이|참관|네트워킹|공모전|경진대회|챌린지|콘테스트", t):
        return "행사·공모전"
    if re.search(r"교육|아카데미|강의|멘토링|컨설팅|코칭|교육생|학교|특강", t):
        return "교육·컨설팅"
    if re.search(r"투자|입주|보육센터|액셀러레이|IR", t):
        return "투자·입주"
    if re.search(r"지원사업|사업화|보조|융자|자금|바우처|지원금|급여|보험료|임대료|수혜기업", t):
        return "자금·사업화 지원"
    return "기타"


def _text(p: Program) -> str:
    return " ".join([p.title, p.target, p.field, p.stage, p.age, p.detail or p.summary])


def rule_screen(p: Program, prof: Profile) -> Screened:
    title_target = p.title + " " + p.target
    text = _text(p)
    traits = set(prof.traits)
    check = []
    if "청년" in p.title and prof.age and prof.age > 39:
        return Screened(p, "해당 안 됨", f"청년 대상 공고인데 나이가 만 {prof.age}세입니다.",
                        ["청년 나이 기준(보통 만 39세 이하)"], kind=guess_kind(p))
    for word, trait in (("여성", "여성"), ("장애인", "장애인")):
        if (word + "기업") in p.title or (word + " 창업") in p.title or (word + "창업") in p.title:
            if trait not in traits:
                return Screened(p, "해당 안 됨", f"{word} 대상 공고입니다.", [], kind=guess_kind(p))
    if prof.stage == "예비창업자" and re.search(r"예비\s*창업자?\s*(?:지원\s*불가|신청\s*불가|제외|불가)", text):
        return Screened(p, "해당 안 됨", "공고문에 예비창업자는 신청할 수 없다고 적혀 있습니다.", [], kind=guess_kind(p))
    if prof.stage == "예비창업자" and re.search(r"(기존|기)\s*사업자|업력\s*\d|사업자등록.*(필수|있는)", title_target):
        check.append("사업자등록이 필요한지")
    reasons = []
    if "제주" in p.region:
        reasons.append("제주 지역 공고")
    if prof.stage == "예비창업자" and "예비" in text:
        reasons.append("예비창업자도 신청 가능")
    if "소상공인" in title_target and prof.stage != "예비창업자":
        reasons.append("소상공인 대상")
        check.append("소상공인 기준(상시 근로자 5인 미만 등)")
    if p.stage:
        reasons.append(f"창업 기간 조건에 맞음({prof.stage})")
    if p.age and prof.age:
        reasons.append("나이 조건에 맞음")
    hits = [k for k in prof.keywords if k and k in text]      # 업종 관련어만(필요한 도움은 판정에 쓰지 않음)
    if hits:
        reasons.append("관련 업종: " + ", ".join(hits[:3]))
    # '해당'은 내 가게와 이어지는 근거(제주 공고·업종 관련어·소상공인 대상)가 있을 때만. 없으면 업종을 확인하게 한다.
    fit = "제주" in p.region or bool(hits) or any(w in title_target for w in SHOP_TARGET_WORDS)
    if not fit and prof.business:
        check.insert(0, f"{prof.business}도 지원 대상인지")
    check.append("공고문의 신청 자격·제외 대상")
    verdict = "해당" if (len(reasons) >= 3 and not check[:-1]) else "확인 필요"
    return Screened(p, verdict, " · ".join(reasons) or "기본 조건(지역·마감)만 맞습니다.", check[:3], kind=guess_kind(p))


SCREEN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"results": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"id": {"type": "integer"}, "verdict": {"type": "string", "enum": VERDICTS},
                       "kind": {"type": "string", "enum": KINDS},
                       "reason": {"type": "string"}, "check": {"type": "array", "items": {"type": "string"}}},
        "required": ["id", "verdict", "kind", "reason", "check"]}}},
    "required": ["results"],
}
SCREEN_SYSTEM = (
    "너는 정부·지자체 지원사업 공고의 신청 자격을 확인해 주는 도우미다. 신청자 조건과 공고 목록을 보고 공고마다 "
    "verdict를 고른다: '해당'(공고문에 적힌 대상 조건에 신청자가 분명히 맞고, 신청자 업종의 가게를 여는 데 실제로 쓸모 "
    "있음), '해당 안 됨'(지역·나이·업력·대상이 분명히 맞지 않거나, IT·바이오 같은 다른 분야나 기술·투자 유치·입주 공간 "
    "중심이라 신청자 업종과 무관하거나, 다른 지역에서 직접 참석해야 함), '확인 필요'(공고문 정보가 부족하거나 신청자 "
    "정보가 없어 판단할 수 없음). 업종과 무관해 '해당 안 됨'이면 reason에 그렇게 적는다. "
    "공고문에 없는 조건을 지어내지 말고, 애매하면 '확인 필요'를 고른다. kind는 공고 성격(자금·사업화 지원, 교육·컨설팅, "
    "행사·공모전, 투자·입주, 기타). reason은 한국어 한 문장(60자 이내)으로 판정 이유, check는 신청자가 공고문에서 직접 "
    "확인할 것 0~3개(각 20자 이내)."
)


def _program_brief(i: int, p: Program) -> dict:
    return {"id": i, "제목": p.title, "기관": p.org, "지역": p.region or "-", "분야": p.field or "-",
            "대상": p.target[:300] or "-", "창업기간 조건": p.stage or "-", "나이 조건": p.age or "-",
            "내용": (p.detail or p.summary)[:700]}


def ai_screen(programs: list[Program], prof: Profile, cfg=None, chat=None) -> list[Screened]:
    """AI 판정. 실패하면 LLMUnavailable/ValueError를 던진다(호출한 쪽이 규칙 판정으로 대신)."""
    from . import llm
    chat = chat or llm.chat
    payload = {"신청자 조건": prof.describe(), "공고": [_program_brief(i, p) for i, p in enumerate(programs)]}
    out = chat([{"role": "system", "content": SCREEN_SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
               cfg, "지원사업 자격 확인", SCREEN_SCHEMA)
    got = {}
    for r in json.loads(out).get("results", []):
        i = r.get("id")
        if isinstance(i, int) and 0 <= i < len(programs) and r.get("verdict") in VERDICTS and i not in got:
            got[i] = Screened(programs[i], r["verdict"], str(r.get("reason", ""))[:120],
                              [str(c)[:40] for c in r.get("check", [])][:3], by="AI",
                              kind=r.get("kind") if r.get("kind") in KINDS else guess_kind(programs[i]))
    if not got:
        raise ValueError("AI 판정 결과가 비어 있습니다.")
    return [got.get(i) or rule_screen(p, prof) for i, p in enumerate(programs)]


def screen(programs: list[Program], prof: Profile, use_ai: bool = False, cfg=None, limit: int = 12,
           chat=None) -> tuple[list[Screened], str]:
    """상위 limit개 공고를 판정해 '해당 → 확인 필요 → 해당 안 됨' 순으로. (목록, 안내 문구)

    '가게를 연 뒤' 공고(예비창업자에게 사업자 대상 제주 공고)는 지금 자격으로 판정하면 모두 '해당 안 됨'이 되므로
    AI에 보내지 않고 '개업 후 확인'으로 따로 둔다(최대 5건).
    """
    later = [p for p in programs if p.after_open][:5]
    top = [p for p in programs if not p.after_open][:limit]
    note = "공고문의 대상 문장으로 자동 판정한 추정입니다. 신청 전에 공고문을 꼭 확인하세요."
    res = None
    if use_ai and top:
        try:
            res = ai_screen(top, prof, cfg, chat)
            note = ("AI가 공고문과 입력한 조건을 대조해 판정했습니다(보낸 정보: 입력한 조건과 공고문만). "
                    "최종 자격은 공고문으로 확인하세요.")
        except Exception as e:  # noqa: BLE001  키 없음·한도·형식 오류 → 규칙 판정
            why = str(e) if isinstance(e, LLMUnavailable) and str(e) else "AI 답을 읽지 못함"
            note = f"AI 판정을 쓰지 못해({why}) 규칙으로 판정했습니다. " + note
    if res is None:
        res = [rule_screen(p, prof) for p in top]
    res += [Screened(p, "확인 필요", "사업자등록(개업) 뒤 신청할 수 있는 제주 공고입니다. "
                     + " · ".join(r for r in p.reasons if r.startswith(("관련 업종", "마감")))[:80],
                     ["개업 후 업력·매출 조건"], kind=guess_kind(p)) for p in later]
    order = {v: i for i, v in enumerate(VERDICTS)}
    res.sort(key=lambda s: (order[s.verdict], -s.program.score, s.program.end or "9999"))
    return res, note


BIZ_KEYWORDS = {  # 질문의 업종 → 공고에서 찾을 관련어
    "카페": ["카페", "외식", "식품", "음료"], "한식당": ["외식", "음식", "식품", "관광"],
    "펜션·게스트하우스": ["숙박", "관광", "농어촌민박"], "호텔": ["숙박", "관광"], "주점": ["외식", "음식"],
    "편의점": ["소매", "유통"], "렌터카": ["관광", "운송"], "기념품": ["관광", "기념품", "공예"],
}


def profile_from_question(prof: Profile, business_labels: list[str], city: str = "") -> Profile:
    """질문에서 찾은 업종·지역으로 빈 칸을 채운다(이미 입력한 값은 그대로)."""
    if not prof.business and business_labels:
        prof.business = business_labels[0]
    if not prof.city and city:
        prof.city = city
    kws = list(prof.keywords)
    for b in business_labels:
        kws += BIZ_KEYWORDS.get(b, [b])
    prof.keywords = list(dict.fromkeys(k for k in kws if k))
    return prof
