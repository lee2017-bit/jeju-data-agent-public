import json

import pytest

from jeju_agent import admin, llm


@pytest.fixture(autouse=True)
def tmp_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "SETTINGS", tmp_path / "local_settings.json")
    monkeypatch.setattr(llm, "USAGE", tmp_path / "usage.jsonl")


def test_pin_hash_only_and_check(tmp_path):
    assert not admin.has_pin() and not admin.check_pin("123456")      # PIN이 없으면 열리지 않음
    admin.set_pin("482193")
    raw = (tmp_path / "local_settings.json").read_text(encoding="utf-8")
    assert "482193" not in raw and json.loads(raw)["operator_pin_hash"]
    assert admin.check_pin("482193") and not admin.check_pin("000000")


def test_pin_rules_and_overwrite_needs_current():
    with pytest.raises(ValueError):
        admin.set_pin("1234")                                          # 6자리 미만
    admin.set_pin("555555")
    with pytest.raises(PermissionError):
        admin.set_pin("666666")                                        # 현재 PIN 없이 덮어쓰기 금지
    admin.set_pin("666666", current="555555")
    assert admin.check_pin("666666")


def test_lockout_persists_and_escalates():
    admin.set_pin("555555")
    for _ in range(admin.MAX_TRIES):
        assert not admin.check_pin("111111")
    left = admin.locked_for()
    assert 0 < left <= admin.LOCK_STEPS[0] and not admin.check_pin("555555")   # 잠긴 동안은 맞아도 안 열림
    s = llm.load_settings()
    assert s["operator_pin_lock_level"] == 1                          # 파일에 남아 재시작해도 유지


def test_reset_wipes_pin_and_keys(tmp_path):
    admin.set_pin("555555")
    s = llm.load_settings()
    s.update(api_key="sk-test", data_go_kr_key="k")
    llm.save_settings(s)
    admin.reset()
    s = llm.load_settings()
    assert not admin.has_pin() and "api_key" not in s and "data_go_kr_key" not in s
    assert "초기화" in (tmp_path / "usage.jsonl").read_text(encoding="utf-8")
