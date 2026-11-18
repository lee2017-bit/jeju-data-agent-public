"""화면 연기 테스트(Streamlit AppTest): 오류 없이 뜨는지, 체험 경로가 결과까지 가는지, 운영자 페이지가 잠기는지."""
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from jeju_agent import llm

os.environ["JEJU_AGENT_NO_PREFETCH"] = "1"
APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "SETTINGS", tmp_path / "local_settings.json")
    monkeypatch.setattr(llm, "USAGE", tmp_path / "usage.jsonl")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _texts(at):
    return " ".join(m.value for m in at.markdown) + " ".join(str(b.label) for b in at.button)


def test_visitor_demo_reaches_answer():
    at = AppTest.from_file(APP, default_timeout=120).run()
    assert not at.exception
    assert "무엇이 궁금하세요" in " ".join(h.value for h in at.subheader)
    next(b for b in at.button if "예시 결과 바로 보기" in str(b.label)).click().run()
    assert not at.exception
    text = _texts(at)
    assert "[체험] 애월읍 카페는" in text and "그래서 할 일" in text
    assert "운영자" not in " ".join(str(b.label) for b in at.button)      # 방문자 화면에 운영자 입구 없음


def _usage(cost: float):
    import json
    from datetime import datetime
    llm.USAGE.write_text(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "model": "gpt-6-luna",
                                     "purpose": "질문 해석", "in": 0, "out": 0, "cost_usd": cost}) + "\n",
                         encoding="utf-8")


def test_ai_meter_shows_percent_only(monkeypatch):
    """방문자 화면에는 이번 달 한도($10) 대비 사용량을 %로만 보여 주고 금액은 보이지 않는다."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    _usage(3.7)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    text = _texts(at)
    assert "이번 달 사용량" in text and "<b>37%</b>" in text
    assert "$" not in text and "달러" not in text
    assert not at.warning


def test_ai_quota_shows_clear_notice(monkeypatch):
    """한도($10)를 다 쓰면 조용히 규칙 모드로 바뀌지 않고, 화면 위에 'AI 꺼짐'과 100%를 보여 준다."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    _usage(10.0)
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    warn = " ".join(w.value for w in at.warning)
    assert "AI 꺼짐" in warn and "100%" in warn and "정해진 규칙" in warn
    assert "$" not in warn


def test_wipe_deletes_only_my_downloaded_csvs(tmp_path, monkeypatch):
    """퇴실 전 지우기: 이 화면이 읽어 들인 내려받기 폴더의 CSV만 지운다(다른 파일·폴더 밖 파일은 그대로)."""
    import jeju_agent.sources as sources
    dl, other = tmp_path / "Downloads", tmp_path / "elsewhere"
    dl.mkdir()
    other.mkdir()
    mine, keep, outside = dl / "card_1-08.csv", dl / "my_notes.csv", other / "card_1-12.csv"
    for f in (mine, keep, outside):
        f.write_text("a,b\n1,2\n", encoding="utf-8")
    monkeypatch.setattr(sources, "load_config", lambda *a, **k: {"watch_dir": str(dl), "preload_dir": "", "tables": {}})
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["my_downloads"] = [str(mine), str(outside)]
    at.run()
    next(b for b in at.button if "퇴실 전 내 작업 지우기" in str(b.label)).click().run()
    assert "card_1-08.csv" in _texts(at) and "card_1-12.csv" not in _texts(at)
    # 대화상자 안 버튼은 AppTest가 다시 그리지 않으므로, 지우는 부분은 같은 함수로 직접 확인한다
    files = sources.visitor_files([str(mine), str(outside), str(dl / "없는파일.csv")], str(dl))
    assert files == [mine.resolve()]
    assert sources.delete_files(files) == []
    assert not mine.exists() and keep.exists() and outside.exists()


def test_question_order_shows_plain_names_not_tool_ids():
    at = AppTest.from_file(APP, default_timeout=120).run()
    at.text_input(key="q_input").input("애월에 카페 차리려는데, 관광객 장사가 될까요?").run()
    assert not at.exception
    line = next(m.value for m in at.markdown if "이 순서로 알려 드려요" in m.value)
    assert "경쟁 가게 수" in line and "_" not in line.split("</b>")[0]


def test_demo_secrets_reach_env_and_demo_note_shows(monkeypatch):
    monkeypatch.setenv("JEJU_AGENT_DEMO", "")          # 끝나면 원래대로(없음) 돌려 놓기 위해 먼저 등록
    at = AppTest.from_file(APP, default_timeout=120)
    at.secrets["JEJU_AGENT_DEMO"] = "1"                 # 호스팅 'Secrets' 칸에 넣은 값
    at.run()
    assert not at.exception
    assert os.environ.get("JEJU_AGENT_DEMO") == "1"
    assert any("공개 데모" in c.value for c in at.caption)



def test_stale_package_is_reloaded(monkeypatch):
    """무료 호스팅에서 새 코드가 들어왔는데 옛 모듈이 메모리에 남아 있으면 비워서 다시 불러온다."""
    import sys
    import types

    import jeju_agent
    for k, v in list(sys.modules.items()):          # 다른 테스트가 쓰는 모듈은 끝나면 되돌린다
        if k == "jeju_agent" or k.startswith("jeju_agent."):
            monkeypatch.setitem(sys.modules, k, v)
    old = types.ModuleType("jeju_agent")          # 확인 기능이 없던 옛 패키지
    monkeypatch.setitem(sys.modules, "jeju_agent", old)
    monkeypatch.setitem(sys.modules, "jeju_agent.fake_old", types.ModuleType("jeju_agent.fake_old"))
    src = open("app.py", encoding="utf-8").read()
    ns = {"__file__": "app.py"}
    exec(src[src.index("def _forget_stale_package"):src.index("\n\n\n", src.index("def _forget_stale_package"))],
         {"sys": sys, **ns}, ns)
    ns["_forget_stale_package"]()
    assert "jeju_agent" not in sys.modules and "jeju_agent.fake_old" not in sys.modules
    sys.modules["jeju_agent"] = jeju_agent           # 같은 코드면 그대로 둔다
    ns["_forget_stale_package"]()
    assert sys.modules["jeju_agent"] is jeju_agent
