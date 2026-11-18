"""LLM 모드(선택): 자유 질문 해석과 결과 요약 문장 다듬기. 키가 없거나 한도를 넘으면 규칙 모드로 돌아간다.

보내는 것(데이터 경계)
- 질문 해석: 이용자 질문 + 허용 값 목록(법정동·업종 이름). 데이터 값은 보내지 않는다.
- 요약 문장: 응용집계(비중·순위·지수·증감률)와 템플릿 문장. 합계 같은 단순집계·원본 행은 보내지 않는다.
검증
- 해석 결과는 허용 목록에 있는 값만 받아들인다.
- 요약 문장에 입력에 없던 숫자가 나오면 버리고 템플릿 문장을 쓴다(지어낸 수치 차단).
비용
- 호출마다 토큰과 비용을 data/usage_log.jsonl에 남기고, 이번 달 합계가 한도(기본 $10)에 닿으면 호출하지 않는다.
  방문자 화면에는 금액 대신 한도 대비 사용량(%)만 보여 준다.
- OpenAI 호환 API(OpenAI, Nebius 등)를 base_url만 바꿔 쓸 수 있다.
- 기본 모델 gpt-6-luna(입력 $0.10/출력 $0.50, 2026-11-02 가격표): 같은 작업 실측 비교에서
  gpt-5.6-luna 대비 비용 약 절반, 요약 속도 3초 대 9초, 해석·요약 품질은 비슷했다(gpt-5-mini보다도 쌈).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / "config" / "local_settings.json"      # gitignore — 센터 PC에서 운영자가 입력
USAGE = ROOT / "data" / "usage_log.jsonl"

# 100만 토큰당 USD (Standard, 2026-11-02 OpenAI 가격표 확인). 다른 모델은 운영자 설정에서 지정.
# 모델은 gpt-6-luna 하나만 쓴다. 2026-11-03 실측: 질문 해석 15문항 완전 정답 luna 13 = sol 13,
# 지원사업 자격 판정 36건 중 30건 일치(갈린 6건 중 5건은 sol이 '확인 필요'로 더 조심스러웠을 뿐).
# sol(입력 $2.00/출력 $10.00)은 luna의 20배 비용이라 이득이 없다. 결론 판정은 원래 규칙이라 모델과 무관하다.
PRICES = {"gpt-6-luna": (0.10, 0.50)}
DEFAULTS = {"base_url": "https://api.openai.com/v1", "model": "gpt-6-luna", "monthly_budget_usd": 10.0,
            "price_in": None, "price_out": None}


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    monthly_budget_usd: float
    price_in: float
    price_out: float

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)


def load_settings() -> dict:
    s = dict(DEFAULTS)
    if SETTINGS.exists():
        s.update({k: v for k, v in json.loads(SETTINGS.read_text(encoding="utf-8")).items() if v not in ("", None)})
    return s


def save_settings(s: dict) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def get_config() -> LLMConfig:
    s = load_settings()
    key = s.get("api_key") or os.environ.get("OPENAI_API_KEY", "") or os.environ.get("NEBIUS_API_KEY", "")
    base = s.get("base_url") or os.environ.get("OPENAI_BASE_URL", DEFAULTS["base_url"])
    model = DEFAULTS["model"]                    # gpt-6-luna 고정(위 실측 참고)
    pin, pout = PRICES.get(model, (None, None))
    return LLMConfig(key, base.rstrip("/"), model, float(s.get("monthly_budget_usd", 10.0)),
                     float(s.get("price_in") or pin or 1.0), float(s.get("price_out") or pout or 5.0))


_SPENT_CACHE: dict = {}


def month_spent(path: Path | None = None) -> float:
    """이번 달 AI 사용 금액(USD). 파일이 바뀌지 않았으면 다시 읽지 않는다(화면을 그릴 때마다 부르므로)."""
    path = path or USAGE
    if not path.exists():
        return 0.0
    ym = datetime.now().strftime("%Y-%m")
    st_ = path.stat()
    key = (str(path), st_.st_mtime_ns, st_.st_size, ym)
    if key in _SPENT_CACHE:
        return _SPENT_CACHE[key]
    total = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("ts", "").startswith(ym):
            total += float(r.get("cost_usd", 0))
    _SPENT_CACHE.clear()
    _SPENT_CACHE[key] = round(total, 6)
    return _SPENT_CACHE[key]


def usage_pct(cfg: "LLMConfig | None" = None) -> float:
    """이번 달 한도 대비 사용량(%). 화면에는 금액 대신 이 값만 보여 준다. 한도가 0이면 100."""
    cfg = cfg or get_config()
    if cfg.monthly_budget_usd <= 0:
        return 100.0
    return min(100.0, month_spent() / cfg.monthly_budget_usd * 100)


def pct_label(pct: float) -> str:
    if pct >= 100:
        return "100%"
    if 0 < pct < 1:
        return "1% 미만"
    return f"{int(pct)}%"


def _log(cfg: LLMConfig, purpose: str, usage: dict) -> float:
    tin, tout = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
    cost = tin / 1e6 * cfg.price_in + tout / 1e6 * cfg.price_out
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    with USAGE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "model": cfg.model, "purpose": purpose,
                            "in": tin, "out": tout, "cost_usd": round(cost, 6)}, ensure_ascii=False) + "\n")
    return cost


class LLMUnavailable(Exception):
    pass


def ai_state(cfg: "LLMConfig | None" = None) -> tuple[str, str]:
    """AI를 지금 쓸 수 있는지와, 못 쓰면 그 이유를 방문자에게 알릴 문장.

    on / off_nokey(키 없음) / off_admin(운영자가 끔) / quota(이번 달 한도 100% 사용)
    한도는 금액(기본 월 $10) 하나뿐이다. 사람별·하루 횟수 제한은 두지 않는다.
    """
    cfg = cfg or get_config()
    if not cfg.enabled:
        return "off_nokey", "AI가 연결되어 있지 않아 정해진 규칙으로만 답합니다."
    if not load_settings().get("ai_on", True):
        return "off_admin", "운영자가 AI를 꺼 두어 정해진 규칙으로만 답합니다."
    if usage_pct(cfg) >= 100:
        return "quota", "이번 달 AI 사용량을 100% 모두 써서, 지금부터는 정해진 규칙으로만 답합니다."
    return "on", ""


def chat(messages: list[dict], cfg: LLMConfig | None = None, purpose: str = "", schema: dict | None = None,
         timeout: int = 40, opener=urllib.request.urlopen) -> str:
    cfg = cfg or get_config()
    if not cfg.enabled:
        raise LLMUnavailable("API 키가 없습니다.")
    if usage_pct(cfg) >= 100:
        raise LLMUnavailable("이번 달 AI 사용량을 100% 모두 썼습니다.")
    body: dict = {"model": cfg.model, "messages": messages}
    if cfg.model.startswith(("gpt-5", "gpt-6")):
        # gpt-5: minimal 지원 / gpt-5.x·gpt-6: none·low 지원(minimal 거부, 2026-11-02 실측)
        body["reasoning_effort"] = "minimal" if cfg.model.startswith("gpt-5-") or cfg.model == "gpt-5" else "low"
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": schema}}
    req = urllib.request.Request(cfg.base_url + "/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers={"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"})
    last = None
    for i in range(2):
        try:
            with opener(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            _log(cfg, purpose, data.get("usage", {}))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):             # 키 만료·오타·권한 — 다시 해도 같으므로 바로 알린다
                raise LLMUnavailable("AI 키가 맞지 않거나 만료되었습니다. 운영자에게 알려 주세요") from e
            if e.code == 429:
                raise LLMUnavailable("AI 서비스의 사용 한도에 걸렸습니다. 잠시 뒤 다시 해 보세요") from e
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(1.5)
    code = getattr(last, "code", None)
    raise LLMUnavailable(f"AI 서버가 응답하지 않았습니다{f'(코드 {code})' if code else ''}")


# ── 1) 자유 질문 해석 ─────────────────────────────────────────
SEG_KEYS = ["없음", "관광객", "도민", "외국인", "중국인", "일본인", "단체관광"]
VIEWS = ["share", "trend", "weekday", "timeslot", "rank", "compare"]
MEASURES = ["use_amt", "use_cnt", "user_cnt"]


def parse_schema(bjds: list[str], biz: list[str]) -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "regions": {"type": "array", "items": {"type": "string", "enum": bjds}},
            "business": {"type": "array", "items": {"type": "string", "enum": biz}},
            "segment": {"type": "string", "enum": SEG_KEYS},
            "measure": {"type": "string", "enum": MEASURES},
            "views": {"type": "array", "items": {"type": "string", "enum": VIEWS}},
        },
        "required": ["regions", "business", "segment", "measure", "views"],
    }


PARSE_SYSTEM = (
    "너는 제주 카드 매출 데이터 분석 질문을 구조화하는 도우미다. 질문에 나온 지역을 법정동 목록에서, 업종을 업종 목록에서 고른다. "
    "'아라동'처럼 여러 법정동(아라일동·아라이동)을 뜻하면 모두 고른다. 없으면 빈 목록. "
    "segment: 관광객/도민/외국인 등 대상이 있으면 고르고 없으면 '없음'. measure: 매출·금액=use_amt, 결제·건수=use_cnt, 손님·고객·사람=user_cnt, 모르면 use_amt. "
    "views: share(비중), trend(추이·성수기·변화), weekday(요일·주말), timeslot(시간대·점심·저녁), rank(어디·순위·가장 많은 곳), compare(비교·평균 대비). 해당 없으면 빈 목록."
)


def parse_question(question: str, bjds: list[str], biz: list[str], cfg: LLMConfig | None = None) -> dict:
    out = chat([{"role": "system", "content": PARSE_SYSTEM}, {"role": "user", "content": question}],
               cfg, "질문 해석", parse_schema(bjds, biz))
    d = json.loads(out)
    d["regions"] = [r for r in d.get("regions", []) if r in bjds]
    d["business"] = [b for b in d.get("business", []) if b in biz]
    return d


PHRASE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "place_phrases": {"type": "array", "items": {"type": "string"}},
        "business_phrases": {"type": "array", "items": {"type": "string"}},
        "segment": {"type": "string", "enum": SEG_KEYS},
        "measure": {"type": "string", "enum": MEASURES},
        "views": {"type": "array", "items": {"type": "string", "enum": VIEWS}},
    },
    "required": ["place_phrases", "business_phrases", "segment", "measure", "views"],
}
PHRASE_SYSTEM = (
    "질문에서 장소를 가리키는 표현과 업종(가게 종류)을 가리키는 표현을 질문에 쓰인 말 그대로 뽑아라. "
    "예: '협재 쪽 게하' → place_phrases ['협재'], business_phrases ['게하']. 지명을 다른 지명으로 바꾸거나 추측하지 마라. "
    "segment: 관광객/도민/외국인/중국인/일본인/단체관광 중 질문에 나온 대상, 없으면 '없음'. "
    "measure: 매출·금액=use_amt, 결제·건수=use_cnt, 손님·고객·사람=user_cnt, 모르면 use_amt. "
    "views: share(비중), trend(추이·성수기·변화), weekday(요일·주말·평일), timeslot(시간대·점심·저녁·언제), "
    "rank(어디·순위·가장 많은 곳), compare(비교·평균 대비). 질문에 드러난 것만."
)


def extract_phrases(question: str, cfg: LLMConfig | None = None) -> dict:
    return json.loads(chat([{"role": "system", "content": PHRASE_SYSTEM}, {"role": "user", "content": question}],
                           cfg, "질문 해석", PHRASE_SCHEMA))


# ── 2) 결과 요약 문장 ─────────────────────────────────────────
SUMMARY_SYSTEM = (
    "너는 코딩을 모르는 제주 도민에게 데이터 분석 결과를 설명한다. 주어진 '분석 문장'과 '수치'만 근거로 "
    "3~5문장의 쉬운 한국어 요약을 쓴다. 새로운 숫자를 만들거나 계산하지 말고, 주어진 숫자는 그대로 옮긴다. "
    "추측·과장('반드시', '확실히')을 쓰지 말고 '~로 보입니다', '~할 수 있습니다'처럼 쓴다. "
    "마지막 문장은 활용 목적에 맞춘 다음 행동 한 가지를 제안한다. 목록 기호 없이 문단으로 쓴다."
)
NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUM.findall(text)}


def summarize(question: str, purpose: str, sections: list[dict], cfg: LLMConfig | None = None) -> tuple[str, list[str]]:
    """(요약문, 검사 메모). sections: [{title, narrative:[...], applied:{...}}] — 응용집계만."""
    payload = {"질문": question, "활용 목적": purpose or "-",
               "분석": [{"제목": s["title"], "분석 문장": s["narrative"], "수치": s["applied"]} for s in sections]}
    text = chat([{"role": "system", "content": SUMMARY_SYSTEM},
                 {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}], cfg, "결과 요약").strip()
    allowed = _numbers(json.dumps(payload, ensure_ascii=False))
    new = sorted(n for n in _numbers(text) if n not in allowed and not re.fullmatch(r"[1-9]", n))
    if new:
        raise LLMUnavailable(f"요약에 입력에 없는 수치가 있어 버렸습니다: {', '.join(new[:5])}")
    return text, ["요약 문장의 수치가 모두 분석 결과와 일치함을 자동 확인했습니다."]


def payload_for(outcomes) -> list[dict]:
    """StepOutcome 목록 → LLM에 보낼 응용집계만."""
    out = []
    for o in outcomes:
        if o.result is None:
            continue
        out.append({"title": o.step.why, "narrative": o.narrative,
                    "applied": {k: v for k, v in o.result.facts.get("applied", {}).items() if v is not None}})
    return out
