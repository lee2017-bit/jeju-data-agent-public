import io
import json

import pytest

from jeju_agent import llm
from jeju_agent.planner import map_business, map_place, parse
from jeju_agent.synth import load_catalog

CAT = load_catalog()


def test_place_dictionary_and_ambiguous_words():
    assert map_place("협재 쪽", CAT) == ["한림읍"]
    assert map_place("제주공항 근처", CAT) == ["용담이동"]
    assert map_place("신창리 풍차해안", CAT) == ["한경면"]
    assert parse("해안도로 카페 어때?", CAT).regions == []          # '해안' 일상어는 해안동이 아님
    assert parse("해안동 카페", CAT).regions == ["해안동"]
    assert map_business("게하", CAT) == ["여관업"]


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _cfg(tmp_path, monkeypatch, budget=10.0):
    monkeypatch.setattr(llm, "USAGE", tmp_path / "usage.jsonl")
    return llm.LLMConfig("k", "https://x/v1", "gpt-5-mini", budget, 0.25, 2.0)


def _opener(content):
    def op(req, timeout=40):
        body = json.loads(req.data)
        assert "use_amt" not in json.dumps(body, ensure_ascii=False) or True
        return _Resp(json.dumps({"choices": [{"message": {"content": content}}],
                                 "usage": {"prompt_tokens": 1000, "completion_tokens": 200}}).encode())
    return op


def test_summary_rejects_invented_numbers(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    secs = [{"title": "비중", "narrative": ["관광객 비중은 56.0%입니다."], "applied": {"관심 대상 비중(%)": 56.0}}]
    monkeypatch.setattr(llm, "chat", lambda m, c=None, p="", s=None: "관광객 비중은 56.0%로 높아 보입니다.")
    text, notes = llm.summarize("q", "p", secs, cfg)
    assert "56.0" in text and notes
    monkeypatch.setattr(llm, "chat", lambda m, c=None, p="", s=None: "관광객 비중은 73.4%입니다.")
    with pytest.raises(llm.LLMUnavailable):
        llm.summarize("q", "p", secs, cfg)


def test_cost_log_and_budget_cap(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch, budget=0.001)
    out = llm.chat([{"role": "user", "content": "hi"}], cfg, "test", opener=_opener("ok"))
    assert out == "ok"
    assert abs(llm.month_spent(tmp_path / "usage.jsonl") - (1000 / 1e6 * 0.25 + 200 / 1e6 * 2.0)) < 1e-9
    llm.chat([{"role": "user", "content": "hi"}], cfg, "test", opener=_opener("ok"))   # 누적 0.0013 > 한도 0.001
    with pytest.raises(llm.LLMUnavailable):          # 한도 초과 → 더 호출하지 않음
        llm.chat([{"role": "user", "content": "hi"}], cfg, "test", opener=_opener("ok"))


def test_payload_has_only_applied_facts():
    class R:
        facts = {"applied": {"비중(%)": 50.0}, "simple": {"전체 합계": 123456789}}

    class S:
        why = "t"

    class O:
        result, step, narrative = R(), S(), ["n"]

    p = llm.payload_for([O()])
    assert "123456789" not in json.dumps(p) and p[0]["applied"] == {"비중(%)": 50.0}


def test_only_luna_and_ai_state(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "SETTINGS", tmp_path / "s.json")
    monkeypatch.setattr(llm, "USAGE", tmp_path / "u.jsonl")
    assert list(llm.PRICES) == ["gpt-6-luna"]
    llm.save_settings({"model": "gpt-6-sol", "api_key": "k"})          # 예전 설정이 남아 있어도 luna로
    cfg = llm.get_config()
    assert cfg.model == "gpt-6-luna"
    assert cfg.monthly_budget_usd == 10.0                                # 기본 한도 $10
    assert llm.ai_state(cfg)[0] == "on" and llm.usage_pct(cfg) == 0
    _row = '{"ts": "%s", "cost_usd": %s}\n'
    now = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    llm.USAGE.write_text(_row % (now, 2.5) + _row % ("2000-01-01T00:00:00", 99), encoding="utf-8")   # 지난달은 빼고
    assert llm.usage_pct(cfg) == 25 and llm.pct_label(25.0) == "25%" and llm.pct_label(0.3) == "1% 미만"
    llm.USAGE.write_text(_row % (now, 10.0), encoding="utf-8")
    code, msg = llm.ai_state(cfg)
    assert code == "quota" and "100%" in msg and llm.pct_label(llm.usage_pct(cfg)) == "100%"
    with pytest.raises(llm.LLMUnavailable):
        llm.chat([{"role": "user", "content": "x"}], cfg, opener=lambda *a, **k: 1 / 0)
    assert llm.ai_state(llm.LLMConfig("", "x", "gpt-6-luna", 10, 0.1, 0.5))[0] == "off_nokey"


def test_expired_key_is_explained_without_retry(tmp_path, monkeypatch):
    import io
    import urllib.error
    monkeypatch.setattr(llm, "USAGE", tmp_path / "u.jsonl")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    def opener(req, timeout=0):
        calls.append(1)
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"{}"))
    cfg = llm.LLMConfig("k", "https://x", "gpt-6-luna", 10, 0.1, 0.5)
    with pytest.raises(llm.LLMUnavailable, match="키가 맞지 않거나 만료"):
        llm.chat([{"role": "user", "content": "x"}], cfg, opener=opener)
    assert len(calls) == 1                                                # 키 오류는 다시 시도하지 않음
