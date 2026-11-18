"""제주 사장님 상권비서 — 센터 방문자용 화면(4단계) + 숨은 운영자 페이지(/admin, PIN).

실행: streamlit run app.py
흐름: ① 질문 → ② 데이터 준비(받으면 자동으로 넘어감) → ③ 결과(결론 먼저) → ④ 가져가기(반출 묶음·지원사업)
"""

from __future__ import annotations

import hashlib
import html
import io
import os
import secrets
import shutil
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def _forget_stale_package() -> None:
    """무료 호스팅은 새 코드를 받아도 이미 불러온 jeju_agent 모듈을 메모리에 그대로 둘 수 있다.
    그러면 새 app.py와 옛 모듈이 어긋나 오류가 난다. 디스크 코드가 바뀌었으면 모듈을 비워 다시 불러오게 한다."""
    pkg = sys.modules.get("jeju_agent")
    if pkg is None:
        return
    try:
        stale = pkg.LOADED_SIG != pkg.code_signature()
    except AttributeError:  # 이 확인 기능이 없던 옛 코드가 메모리에 있음
        stale = True
    if stale:
        for name in [m for m in sys.modules if m == "jeju_agent" or m.startswith("jeju_agent.")]:
            del sys.modules[name]


_forget_stale_package()

from jeju_agent.env import load_dotenv  # noqa: E402

load_dotenv()  # 앱 폴더의 .env(선택)를 먼저 읽는다


def _secrets_to_env() -> None:
    """무료 호스팅(Streamlit Community Cloud) 공개 데모: 'Secrets' 칸에 넣은 키를 환경변수로 옮긴다.
    센터 설치본에는 secrets 파일이 없으므로 아무 일도 하지 않는다. 키 값은 화면·기록에 남기지 않는다."""
    try:
        for k in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "DATA_GO_KR_KEY", "JEJUDATAHUB_APP_KEY", "JEJU_AGENT_DEMO"):
            if not os.environ.get(k) and k in st.secrets:
                os.environ[k] = str(st.secrets[k])
    except Exception:  # noqa: BLE001  secrets 파일이 없으면 그대로
        pass


_secrets_to_env()

from jeju_agent import admin as admin_mod  # noqa: E402
from jeju_agent import llm as llm_mod  # noqa: E402
from jeju_agent.agent import run_plan  # noqa: E402
from jeju_agent.charts import LEGEND, render  # noqa: E402
from jeju_agent.demo import load_public, synthetic_table  # noqa: E402
from jeju_agent.eligibility import KINDS, profile_from_question, screen  # noqa: E402
from jeju_agent.evidence_pack import build_evidence_pack  # noqa: E402
from jeju_agent.insight import VERDICT_RULES, _hours_label, build_answer  # noqa: E402
from jeju_agent.loader import load_center_csv  # noqa: E402
from jeju_agent.planner import (PUBLIC_ID, PURPOSES, SEGMENTS, Plan, _short_biz, make_plan,  # noqa: E402
                                make_public_plan, parse_hybrid)
from jeju_agent.programs import Profile, load_programs, match  # noqa: E402
from jeju_agent.stores import STORES_ID  # noqa: E402
from jeju_agent.report import build_report, period_of, source_line  # noqa: E402
from jeju_agent.sources import (delete_files, guide_for, load_config, preloaded, recent_downloads,  # noqa: E402
                                save_config, visitor_files)
from jeju_agent.synth import GENERATORS, get_table, load_catalog, ref_rows  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
APP_NAME = "제주 사장님 상권비서"

st.set_page_config(page_title=APP_NAME, page_icon=":material/insights:", layout="wide",
                   initial_sidebar_state="collapsed")

PURPOSE_LABEL = {"사업계획서·창업": "가게 열기·사업계획서", "가게·회사 운영": "가게 운영",
                 "현황자료·보고서": "현황자료·보고서", "논문·연구": "논문·연구"}
EXAMPLES = {
    "사업계획서·창업": ["카페 하려는데 애월이랑 한림 중 어디가 좋을까?", "애월읍에 카페 열면 어때?",
                    "노형동 한식당 창업, 요일·시간대별 매출은?"],
    "가게·회사 운영": ["연동 한식당 매출 추이랑 성수기 알려줘", "애월 카페 손님은 언제 많아? 시간대", "중문동 편의점 외국인 손님 비중"],
    "현황자료·보고서": ["카페는 어느 동이 가장 많이 팔려?", "구좌읍 숙박 관광객 비중", "서귀포 렌터카 매출 추이"],
    "논문·연구": ["애월읍 카페 관광객 비중이 얼마나 돼?", "한림읍 편의점 요일별 패턴", "용담 일식 매출 순위"],
}
STEP_NAMES = {"compare_share": "손님", "trend": "계절", "season_by": "계절", "top_n": "다른 동네",
              "share_by": "손님층", "group_share": "동네 그룹", "store_rank": "경쟁 가게 수",
              "district_profile": "지구 유형", "region_compare": "동네 비교"}


def step_names(steps) -> list[str]:
    """분석 단계를 방문자에게 보여 줄 짧은 이름으로(도구 이름은 화면에 내보내지 않음)."""
    names = []
    for stp in steps:
        n = STEP_NAMES.get(stp.tool) or {"week": "요일", "time": "시간대"}.get(stp.params.get("cat_col"))
        if n and n not in names:
            names.append(n)
    return names


FRIENDLY = {"1-07": "동네·업종별 월 카드 매출(옛 형식)", "1-08": "동네·업종별 월 카드 매출(관광객·도민 구분)",
            "1-12": "요일별 카드 매출", "1-14": "시간대별 카드 매출", PUBLIC_ID: "공개 데이터: 관광객 카드 이용(시 단위)",
            "공개-상가": "공개 데이터: 동네·업종별 가게 수(상가정보)",
            "공개-방문자": "공개 데이터: 제주시·서귀포시 방문자 수(관광공사)", "공개-인구": "공개 데이터: 법정동 인구(행안부)",
            "허브-지구": "공개 데이터: 지구 유형별 요일·시간대(제주데이터허브)"}
CORE_TABLE = "1-08"
STEPS = ["질문", "데이터 준비", "결과", "가져가기"]
CSS = """<style>
.block-container{max-width:1080px;padding-top:3.0rem;padding-bottom:4rem}
[data-testid="stHeader"]{background:transparent;height:2.6rem}
.stApp{font-size:17px}
h1,h2,h3{letter-spacing:-0.01em}
.brand{font-weight:800;font-size:19px;color:#1D4ED8;margin:2px 0 0}
.demo-chip{display:inline-block;background:#FEF3C7;color:#92400E;border-radius:999px;padding:3px 12px;font-size:14px;font-weight:700}
/* 단계 표시 */
[class*="st-key-step_"] button{border-radius:999px;min-height:42px;font-weight:700}
/* ① 질문 */
.st-key-qstep h3{font-size:34px !important;font-weight:800;letter-spacing:-0.02em;padding-bottom:4px}
.sec{font-size:15px;font-weight:800;color:#64748B;margin:14px 0 6px;letter-spacing:.01em}
.st-key-purpose_pill button{font-size:17px !important;padding:8px 18px !important;border-radius:12px !important}
[class*="st-key-ex"] button{min-height:92px;border-radius:18px;border:2px solid #E2E8F0;background:#fff;justify-content:flex-start;
  text-align:left;padding:14px 18px;box-shadow:0 1px 3px rgba(15,23,42,.06)}
[class*="st-key-ex"] button p{font-size:18px !important;font-weight:700;line-height:1.35;white-space:normal !important;text-align:left}
[class*="st-key-ex"] button:hover{border-color:#1D4ED8;color:#1D4ED8;background:#F8FAFF}
.st-key-q_input input{font-size:19px;padding:14px 16px}
.st-key-understood{background:#F0F7FF;border:2px solid #BFDBFE;border-radius:18px;padding:16px 20px}
.understood-h{font-size:20px;font-weight:800;color:#0F172A}
[class*="st-key-chip_"] button{border-radius:999px;background:#fff;border:2px solid #93C5FD;padding:4px 16px;min-height:44px}
[class*="st-key-chip_"] button p{font-size:19px !important;font-weight:800}
.views{font-size:15.5px;color:#334155;margin-top:4px}
.views span{display:inline-block;background:#fff;border:1px solid #CBD5E1;border-radius:999px;padding:2px 11px;margin:3px 2px;font-weight:700}
.views i{font-style:normal;color:#94A3B8;margin:0 1px}
.need-line{font-size:14.5px;color:#64748B;margin-top:4px}
.st-key-start button,.st-key-to_result button,.st-key-to_take button,.st-key-make_bundle button{min-height:58px;border-radius:14px}
.st-key-start button p,.st-key-to_result button p,.st-key-to_take button p,.st-key-make_bundle button p{font-size:19px !important;font-weight:800}
/* ② 데이터 준비 */
.dtile{border-radius:18px;padding:16px 12px;text-align:center;border:2px solid #E2E8F0;background:#fff;height:100%}
.dtile.ok{border-color:#86EFAC;background:#F0FDF4}
.dtile .i{font-size:34px;line-height:1.2}
.dtile b{display:block;font-size:17px;margin-top:4px;line-height:1.35}
.dtile span{font-size:14px;color:#64748B;font-weight:600}
.dtile.ok span{color:#047857}
.st-key-howto{background:#F8FAFC;border:2px solid #E2E8F0;border-radius:18px;padding:16px 20px}
.howto-h{font-size:19px;font-weight:800}
.st-key-howto ol{font-size:17px;line-height:1.7;margin:6px 0 0 0}
/* ③ 결과 */
.st-key-answer{background:#EFF6FF;border:2px solid #BFDBFE;border-radius:20px;padding:22px 26px}
.st-key-answer-real{background:#F0FDF4;border:2px solid #BBF7D0;border-radius:20px;padding:18px 24px;margin-bottom:6px}
.tag{display:inline-block;font-size:13.5px;font-weight:800;border-radius:999px;padding:2px 10px}
.tag.real{background:#DCFCE7;color:#047857}.tag.demo{background:#FEF3C7;color:#92400E}
.qline{font-size:14px;color:#64748B;font-weight:600;margin-left:6px}
.verdict{font-size:29px;font-weight:800;line-height:1.38;color:#0F172A;margin:8px 0 6px}
.verdict.small{font-size:23px}
.core{font-size:18px;color:#1E3A8A;font-weight:800;margin:0 0 8px}
.market{font-size:16px;color:#334155;margin:0 0 6px}
[data-testid="stMetricValue"]{font-size:38px !important;font-weight:800}
.acts{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:6px}
.acts div{background:#fff;border-radius:14px;padding:12px 14px;font-size:16px;line-height:1.5;border:1px solid #DBEAFE}
.acts i{font-style:normal;display:inline-flex;width:26px;height:26px;border-radius:50%;background:#1D4ED8;color:#fff;font-weight:800;
  align-items:center;justify-content:center;margin-right:6px;font-size:14px}
.trust{font-size:14.5px;color:#047857;font-weight:700}
.eyebrow{font-size:13.5px;font-weight:700;color:#64748B;letter-spacing:.01em}
.card-title{font-size:21px;font-weight:800;line-height:1.45;margin:2px 0 8px;color:#0F172A}
.explain{font-size:16.5px;line-height:1.65;color:#1E293B}
.sowhat{background:#FFF7ED;border-left:5px solid #EA580C;border-radius:10px;padding:10px 14px;margin:10px 0;font-size:16.5px}
.foot{font-size:13px;color:#64748B}
.demo-band{background:#FEF3C7;color:#92400E;border-radius:12px;padding:10px 14px;font-weight:700;margin:6px 0 10px}
.muted{color:#64748B;font-size:14.5px}
.ai-meter{display:flex;align-items:center;justify-content:flex-end;gap:10px;font-size:13.5px;color:#64748B;margin:-6px 0 2px}
.ai-meter .track{display:inline-block;width:96px;height:6px;background:#E2E8F0;border-radius:3px;overflow:hidden}
.ai-meter .track i{display:block;height:100%;background:#1D4ED8;border-radius:3px}
.ai-meter.high .track i{background:#D97706}
.rowline{font-size:16.5px}
.st-key-scroller{position:absolute !important;width:0;height:0;overflow:hidden;margin:0;padding:0}
[class*="st-key-card-"]{border-radius:18px;background:#fff;box-shadow:0 1px 2px rgba(16,24,40,.04)}
div[data-testid="stVerticalBlockBorderWrapper"]{background:#fff;border-radius:16px}
div[data-testid="stExpander"] details{background:#fff;border-radius:12px}
div[data-testid="stMetric"]{background:#fff;border-radius:14px}
/* ④ 가져가기 */
.get3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:6px 0 10px}
.get3>div{border-radius:16px;background:#FFF7ED;border:2px solid #FED7AA;padding:14px;text-align:center}
.get3 .i{font-size:32px;line-height:1.2}
.get3 b{display:block;font-size:17px;margin-top:2px}
.get3 span{font-size:14px;color:#9A3412}
.reason-line{font-size:16px;color:#334155}
.pc-title{font-size:17.5px;font-weight:800;line-height:1.4}
.pc-meta span{display:inline-block;font-size:13.5px;font-weight:700;border-radius:999px;padding:1px 10px;margin:2px 4px 2px 0;background:#F1F5F9;color:#334155}
.pc-meta span.d{background:#FEE2E2;color:#B91C1C}
.pc-why{font-size:16px;margin-top:4px}
[data-testid="stFileUploaderDropzoneInstructions"]{display:none}
[data-testid="stFileUploaderDropzone"] button p{font-size:0}
[data-testid="stFileUploaderDropzone"] button p::after{content:"파일 고르기";font-size:16px}
</style>"""


# ── 공통 준비 ───────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def catalog():
    return load_catalog()


@st.cache_resource(show_spinner=False)
def demo_table(tid: str):
    """체험용 가상 표(앱 실행 중 1번만 만든다, 약 1초)."""
    return synthetic_table(tid, catalog())


@st.cache_resource(show_spinner=False)
def public_table():
    return load_public(catalog())


@st.cache_resource(show_spinner=False)
def open_tables() -> dict:
    """동봉한 공공데이터포털 자료(관광공사 방문자 수, 행안부 법정동 인구). 없으면 빈 dict."""
    from jeju_agent.datagokr import POP_ID, VISIT_ID, load_population, load_visitors
    from jeju_agent.hub_district import DISTRICT_ID, load_district
    out = {}
    for tid, fn in ((VISIT_ID, load_visitors), (POP_ID, load_population), (DISTRICT_ID, load_district)):
        try:
            lt = fn(catalog())
        except Exception:  # noqa: BLE001
            lt = None
        if lt is not None:
            out[tid] = lt
    return out


@st.cache_resource(show_spinner=False)
def stores_table():
    """동봉한 상가정보(동네·업종별 가게 수, 실제 공개 데이터)."""
    from jeju_agent.stores import load_stores
    return load_stores(catalog())


@st.cache_resource(show_spinner=False)
def warm_demo():
    """체험 모드: 앱이 켜질 때 가상 표 3개를 뒤에서 미리 만들어 둔다(버튼을 누르면 바로)."""
    import threading
    if os.environ.get("JEJU_AGENT_NO_PREFETCH") or app_mode() != "체험":
        return None
    t = threading.Thread(target=lambda: [demo_table(x) for x in ("1-08", "1-12", "1-14")], daemon=True)
    t.start()
    return t


@st.cache_resource(show_spinner=False)
def prefetch_programs():
    """지원사업 공고(실시간 1,500건 안팎)를 앱이 켜질 때 뒤에서 미리 받아 둔다(30분 캐시)."""
    import threading
    if os.environ.get("JEJU_AGENT_NO_PREFETCH"):      # 테스트·오프라인
        return None
    t = threading.Thread(target=load_programs, daemon=True)
    t.start()
    return t


@st.cache_data(show_spinner=False)
def load_path(path: str, mtime: float):
    return load_center_csv(path, catalog())


def ss(key, default):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


def session_dir() -> Path:
    d = OUT / ss("sid", time.strftime("%Y%m%d_%H%M%S") + "_" + secrets.token_hex(3))   # 공개 데모에서 동시 접속이 겹치지 않게
    d.mkdir(parents=True, exist_ok=True)
    return d


def settings() -> dict:
    return llm_mod.load_settings()


def app_mode() -> str:
    return settings().get("app_mode", "체험")


def esc(x) -> str:
    # '~'가 두 번 나오면 마크다운이 취소선으로 그린다(예: 2025.05~2026.04 … 2016~2018) → 문자 그대로
    return html.escape(str(x)).replace("~", "&#126;")


def md(x) -> str:
    """st.caption·st.markdown에 그대로 넣는 글(HTML 아님)에서 '~' 취소선 막기."""
    return str(x).replace("~", "&#126;")


def go(step: int, auto_ok: bool = True):
    st.session_state["step"] = step
    st.session_state["auto_ok"] = auto_ok


cat = catalog()
CSS_DONE = False


def inject_css():
    st.html(CSS)


def scroll_to(selector: str = ""):
    """Streamlit은 화면을 다시 그려도 스크롤 위치를 그대로 둔다. 단계가 바뀌면 맨 위로, 질문을 알아들으면 그 칸으로 옮긴다."""
    n = st.session_state["_scroll_n"] = st.session_state.get("_scroll_n", 0) + 1
    with st.container(key="scroller"):
        components.html(f"""<script>/* {n} */
const d = window.parent.document, sel = {selector!r};
// 서버가 화면을 조각조각 늦게 그리면 부드러운 스크롤이 중간에 끊긴다 → 즉시 이동을 4초 동안 다시 맞춘다.
// 사용자가 직접 스크롤·클릭·키를 누르면 바로 멈춘다(손으로 움직인 화면을 되돌리지 않음).
let stop = false;
const off = () => {{ stop = true; }};
['wheel', 'touchstart', 'keydown', 'mousedown'].forEach(e => d.addEventListener(e, off, {{once: true, passive: true}}));
const go = (k) => {{
  if (stop) return;
  const m = d.querySelector('[data-testid="stMain"]'); if (!m) return;
  if (!sel) {{ if (m.scrollTop > 0) m.scrollTo({{top: 0, behavior: 'auto'}}); return; }}
  const el = d.querySelector(sel); if (!el) return;
  const r = el.getBoundingClientRect(), h = window.parent.innerHeight;
  if (r.top >= 0 && r.bottom <= h) return;                       // 이미 다 보이면 그대로
  el.scrollIntoView({{behavior: k === 0 ? 'smooth' : 'auto', block: 'center'}});
}};
[60, 250, 600, 1000, 1600, 2500].forEach((t, k) => setTimeout(() => go(k), t));
// 화면 조각이 더 늦게 도착해도(느린 서버) 4초 동안은 바뀔 때마다 다시 맞춘다
const main = d.querySelector('[data-testid="stMain"]');
if (main) {{
  let q = 0;
  const ob = new MutationObserver(() => {{ if (!q) q = setTimeout(() => {{ q = 0; go(9); }}, 120); }});
  ob.observe(main, {{childList: true, subtree: true}});
  setTimeout(() => ob.disconnect(), 4000);
}}
</script>""", height=0)


# ── 방문자 화면 ─────────────────────────────────────────────
def visitor():
    inject_css()
    prefetch_programs()
    warm_demo()
    st.session_state.pop("admin_at", None)      # 방문자 화면으로 오면 운영자 세션을 닫는다
    loaded: dict = ss("loaded", {})
    sources: dict = ss("sources", {})
    ss("step", 1)
    # 공개 데이터(동봉 597)는 시작할 때 자동으로 준비
    if PUBLIC_ID not in loaded:
        pub = public_table()
        if pub is not None:
            loaded[PUBLIC_ID], sources[PUBLIC_ID] = pub, "동봉한 제주데이터허브 공개 데이터(2016.09~2018.12)"
    if STORES_ID not in loaded:
        shops = stores_table()
        if shops is not None:
            loaded[STORES_ID], sources[STORES_ID] = shops, "동봉한 소상공인 상가(상권)정보(동네·업종별 가게 수)"
    for tid, lt in open_tables().items():
        if tid not in loaded:
            loaded[tid], sources[tid] = lt, "동봉한 공공데이터포털 자료(" + lt.table.get("provider", "") + ")"
    # 운영자가 미리 넣어 둔 데이터
    cfg = load_config()
    for tid, ff in preloaded(cfg, cat).items():
        if tid not in loaded or loaded[tid].synthetic:
            loaded[tid] = load_path(str(ff.path), ff.mtime)
            sources[tid] = f"센터 준비 데이터 · {ff.period}"

    c1, c2 = st.columns([5, 1])
    c1.markdown(f"<div class='brand'>🏪 {APP_NAME}</div>", unsafe_allow_html=True)
    if c2.button("처음부터", icon=":material/restart_alt:", type="tertiary", key="restart"):
        for k in ("question", "plan", "slots", "parsed_key", "result", "bundle", "pack", "progs"):
            st.session_state.pop(k, None)
        go(1)
        st.rerun()
    stepper()
    if os.environ.get("JEJU_AGENT_DEMO"):
        st.caption("🧪 공개 데모 — 센터 PC 설치본과 같은 프로그램 · 센터 데이터 자리는 체험용 가상 데이터, 공개 데이터는 실제 값")
    banner = st.container()          # 사용량은 이번 실행의 AI 호출까지 반영하도록 맨 끝에 채운다
    step = st.session_state["step"]
    if st.session_state.get("_last_step") != step:  # 단계가 바뀌면 맨 위부터(느린 단계도 바로 올라가게 앞에서)
        st.session_state["_last_step"] = step
        scroll_to("")
    if step == 1:
        step_question(loaded)
    elif step == 2:
        step_data(loaded, sources, cfg)
    elif step == 3:
        step_result(loaded, sources)
    else:
        step_takeout(loaded)
    st.divider()
    if st.button("퇴실 전 내 작업 지우기", icon=":material/delete:", type="tertiary", key="wipe"):
        confirm_wipe()
    if st.session_state.get("wipe_failed"):
        st.warning("이 파일은 지우지 못했습니다(다른 프로그램에서 열려 있을 수 있음). 직접 지워 주세요: "
                   + ", ".join(st.session_state.pop("wipe_failed")), icon=":material/warning:")
    with banner:
        ai_banner()
    target = st.session_state.pop("_scroll_target", None)
    if target:
        scroll_to(target)


def stepper():
    cur = st.session_state["step"]
    have_plan = "plan" in st.session_state
    have_result = "result" in st.session_state
    reach = {1: True, 2: have_plan, 3: have_plan and have_result, 4: have_result}
    cols = st.columns(4)
    for i, name in enumerate(STEPS, 1):
        done = i < cur
        label = f"{'✓ ' if done else ''}{i}. {name}"
        if cols[i - 1].button(label, key=f"step_{i}", width="stretch",
                              type="primary" if i == cur else "secondary",
                              disabled=(i != cur and not reach[i])):
            go(i, auto_ok=False)
            st.rerun()


@st.dialog("퇴실 전 내 작업 지우기")
def confirm_wipe():
    files = visitor_files(st.session_state.get("my_downloads", []), load_config().get("watch_dir", "~/Downloads"))
    st.write("이 PC에 남은 내 질문·분석 결과·반출 묶음을 지웁니다. 센터 규정에 따라 퇴실 전에 지워 주세요.")
    if files:
        st.markdown(f"내려받기 폴더에서 이 화면이 읽어 들인 **센터 데이터 CSV {len(files)}개**도 함께 지웁니다:")
        for f in files:
            st.markdown(f"- {esc(f.name)}")
    if st.session_state.get("uploaded_names"):
        st.caption("직접 끌어다 넣은 파일(" + ", ".join(st.session_state["uploaded_names"]) + ")은 원래 있던 폴더에서 지워 주세요.")
    if st.button("모두 지우기", type="primary"):
        failed = delete_files(files)
        shutil.rmtree(OUT / st.session_state.get("sid", "_none_"), ignore_errors=True)
        for k in list(st.session_state.keys()):
            if not k.startswith("admin"):
                del st.session_state[k]
        if failed:
            st.session_state["wipe_failed"] = failed
        st.rerun()


PURPOSE_ICON = {"사업계획서·창업": "🏪", "가게·회사 운영": "🛠️", "현황자료·보고서": "📊", "논문·연구": "🎓"}
WORD_ICON = (("카페", "☕\ufe0f"), ("커피", "☕\ufe0f"), ("음료", "☕\ufe0f"), ("흑돼지", "🐷"), ("고깃", "🥩"), ("한식", "🍚"), ("일식", "🍣"),
             ("중식", "🥟"), ("양식", "🍝"), ("브런치", "🥞"), ("제과", "🥐"), ("빵", "🥐"), ("주점", "🍺"), ("호텔", "🏨"),
             ("숙박", "🏨"), ("펜션", "🏡"), ("편의점", "🏪"), ("렌터카", "🚗"), ("식당", "🍽️"), ("음식", "🍽️"))
VIEW_ICON = {"손님": "👥", "손님층": "👥", "계절": "📅", "다른 동네": "🗺️", "동네 그룹": "🗺️", "요일": "🗓️", "시간대": "⏰",
             "경쟁 가게 수": "🏪", "지구 유형": "📍", "동네 비교": "⚖️"}
SHORT_DATA = {"1-07": "동네·업종별 월 매출", "1-08": "동네·업종별 월 매출", "1-12": "요일별 매출", "1-14": "시간대별 매출"}


def icon_for(text: str, default: str = "💬") -> str:
    return next((i for w, i in WORD_ICON if w in (text or "")), default)


# ① 질문 ────────────────────────────────────────────────────
def step_question(loaded: dict):
    with st.container(key="qstep"):
        st.subheader("무엇이 궁금하세요?")
    st.markdown("<div class='sec'>어디에 쓰실 건가요?</div>", unsafe_allow_html=True)
    purpose = st.pills("어디에 쓰실 건가요?", PURPOSES, default=st.session_state.get("purpose", PURPOSES[0]),
                       format_func=lambda p: f"{PURPOSE_ICON[p]} {PURPOSE_LABEL[p]}", key="purpose_pill",
                       label_visibility="collapsed") or PURPOSES[0]
    st.session_state["purpose"] = purpose
    st.markdown("<div class='sec'>눌러서 바로 시작</div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for i, ex in enumerate(EXAMPLES[purpose]):
        if cols[i].button(f"{icon_for(ex)}  {ex}", key=f"ex{i}", width="stretch"):
            st.session_state["question"] = ex
            st.session_state["q_input"] = ex
    if app_mode() == "체험":
        if st.button("예시 결과 바로 보기 (체험 데이터, 약 3초)", icon=":material/bolt:", type="tertiary", key="demo_fast"):
            st.session_state.update(purpose="사업계획서·창업", question="애월읍에 카페 열면 어때?",
                                    q_input="애월읍에 카페 열면 어때?")
            slots, note = parse_hybrid("애월읍에 카페 열면 어때?", cat, "사업계획서·창업", use_llm=False)
            plan = make_plan(slots, cat)
            st.session_state.update(slots=slots, plan=plan, parse_note=note,
                                    parsed_key=f"애월읍에 카페 열면 어때?|사업계획서·창업|False")
            fill_demo(plan, loaded, ss("sources", {}))
            st.session_state.pop("result", None)
            go(3)
            st.rerun()
    st.markdown("<div class='sec'>또는 평소 말로 묻기</div>", unsafe_allow_html=True)
    ss("q_input", st.session_state.get("question", ""))
    q = st.text_input("질문", key="q_input", placeholder="💬 예: 함덕에 브런치 가게 열면 관광객이 많이 올까?",
                      label_visibility="collapsed")
    st.session_state["question"] = q
    if not q:
        return
    use_ai = ai_enabled()
    pkey = f"{q}|{purpose}|{use_ai}"
    if st.session_state.get("parsed_key") != pkey:
        with st.spinner("질문을 이해하는 중…"):
            slots, note = parse_hybrid(q, cat, purpose, use_llm=use_ai)
        st.session_state.update(parsed_key=pkey, slots=slots, parse_note=note)
        st.session_state["_scroll_target"] = ".st-key-understood"
        for k in ("result", "bundle", "pack"):
            st.session_state.pop(k, None)
    slots = st.session_state["slots"]
    plan = make_plan(slots, cat)
    st.session_state["plan"] = plan
    with st.container(key="understood"):
        st.markdown("<div class='understood-h'>✅ 이렇게 이해했어요 <span class='muted'>· 눌러서 고칠 수 있어요</span></div>",
                    unsafe_allow_html=True)
        bjds = [r[0] for r in ref_rows(get_table(cat, "1-08"), "법정동")]
        bizs = [r[1] for r in ref_rows(get_table(cat, "1-08"), "업종")]
        seg_map = {v[2]: v for v in SEGMENTS.values()}
        hk = hashlib.md5(pkey.encode()).hexdigest()[:8]
        short = _short_biz(slots.business, slots.biz_label)
        where = ", ".join(slots.regions) or ", ".join(slots.city) or "동네 고르기"
        seg_now = slots.segment[2] if slots.segment else "전체 손님"
        with st.container(horizontal=True, gap="small"):
            with st.popover(f"📍 {where}", key="chip_r"):
                new_r = st.multiselect("동네(법정동)", bjds, default=[r for r in slots.regions if r in bjds], key=f"er_{hk}")
            with st.popover(f"{icon_for(short, '🏬')} {short or '업종 고르기'}", key="chip_b"):
                new_b = st.multiselect("업종", bizs, default=[b for b in slots.business if b in bizs], key=f"eb_{hk}")
                if len(slots.business) == 1 and short != slots.business[0]:
                    st.caption(f"카드 업종: {slots.business[0]}")
            with st.popover(f"🧳 {seg_now}", key="chip_s"):
                opts = ["전체 손님"] + list(seg_map)
                new_s = st.radio("누구의 매출을 볼까요?", opts, index=opts.index(seg_now) if seg_now in opts else 0,
                                 key=f"es_{hk}")
        if new_r != slots.regions or new_b != slots.business or new_s != seg_now:
            slots.regions, slots.business = new_r, new_b
            if new_r:
                slots.city = []
            slots.biz_label = ""
            slots.segment = seg_map.get(new_s)
            if slots.segment and "share" not in slots.views:
                slots.views.insert(0, "share")
            st.session_state.pop("result", None)
            st.rerun()
        note = st.session_state.get("parse_note", "")
        code, msg = ai_status()
        if "쓰지 못해" in note:
            st.warning(note.replace("기본 모드", "정해진 규칙"), icon=":material/power_off:")
        elif code == "on" or "AI(" in note:
            st.caption("🤖 AI가 질문 해석을 도왔어요 · AI에는 질문 문장만 보냅니다")
        elif code != "quota":
            st.caption(msg)
        if slots.unknown_words:
            st.warning("어느 동·업종인지 확인이 필요한 표현: " + ", ".join(slots.unknown_words))
        names = step_names(plan.steps)
        st.markdown("<div class='views'><b>이 순서로 알려 드려요</b> "
                    + "<i>→</i>".join(f"<span>{VIEW_ICON.get(n, '•')} {esc(n)}</span>" for n in names) + "</div>"
                    f"<div class='need-line'>📦 센터 데이터 {len(plan.requests)}개를 받아 봅니다 · 공개 데이터는 자동으로 함께</div>",
                    unsafe_allow_html=True)
        for a in plan.scope_notes:
            st.info(a, icon=":material/info:")
        for n in plan.notes:
            st.caption(n)
    ok = bool(slots.business or slots.regions or slots.city or "rank" in slots.views)
    ready = all(r.table_id in loaded for r in plan.requests)
    label = "바로 분석하기 →" if ready else "이 질문으로 시작 →"
    if not ok:
        st.caption("동네나 업종을 하나 이상 골라 주세요(위 칩을 누르면 고를 수 있어요).")
    if st.button(label, type="primary", disabled=not ok, key="start"):
        st.session_state.pop("result", None)
        go(3 if ready else 2)
        st.rerun()
    if ready:
        st.caption("필요한 데이터가 이미 준비돼 있어 데이터 단계를 건너뜁니다.")


def ai_status() -> tuple[str, str]:
    return llm_mod.ai_state(llm_mod.get_config())


def ai_enabled() -> bool:
    return ai_status()[0] == "on"


AI_OFF_EFFECT = ("자유로운 말투의 질문은 동네·업종을 잘못 알아들을 수 있고, 지원사업 자격의 AI 확인도 쓸 수 없습니다. "
                 "결론 판정은 원래 규칙으로 하므로 그대로입니다. 동네·업종 이름을 또렷하게 적어 주세요.")


def ai_banner():
    """AI 사용량(이번 달 한도 대비 %)을 보여 주고, 100%면 모든 단계 위에 'AI 꺼짐'을 분명히 알린다.
    금액은 보여 주지 않는다(운영자 페이지에서만)."""
    code, msg = ai_status()
    if code == "quota":
        st.warning(f"**AI 꺼짐 — {msg}** {AI_OFF_EFFECT}", icon=":material/power_off:")
    elif code == "on":
        pct = llm_mod.usage_pct()
        bar = max(pct, 2.0) if pct > 0 else 0.0
        st.markdown(f"<div class='ai-meter{' high' if pct >= 80 else ''}'><span>AI 도움 켜짐 · 이번 달 사용량 "
                    f"<b>{llm_mod.pct_label(pct)}</b></span><span class='track'><i style='width:{bar:.1f}%'></i>"
                    "</span></div>", unsafe_allow_html=True)


def fill_demo(plan: Plan, loaded: dict, sources: dict):
    for r in plan.requests:
        if r.table_id in GENERATORS and (r.table_id not in loaded or loaded[r.table_id].synthetic):
            loaded[r.table_id] = demo_table(r.table_id)
            sources[r.table_id] = "체험용 가상 데이터(명세서 형식, 수치 의미 없음)"


# ② 데이터 준비 ──────────────────────────────────────────────
def step_data(loaded: dict, sources: dict, cfg: dict):
    plan: Plan = st.session_state["plan"]
    need = [r for r in plan.requests]
    have = [r for r in need if r.table_id in loaded]
    st.subheader("필요한 데이터 준비")
    cols = st.columns(len(need) or 1)
    for col, r in zip(cols, need):
        ok = r.table_id in loaded
        col.markdown(f"<div class='dtile{' ok' if ok else ''}'><div class='i'>{'✅' if ok else '⏳'}</div>"
                     f"<b>{esc(SHORT_DATA.get(r.table_id, FRIENDLY.get(r.table_id, r.table_name)))}</b>"
                     f"<span>{'준비됨' if ok else '기다리는 중'}</span></div>", unsafe_allow_html=True)
    st.progress(len(have) / max(1, len(need)), text=f"{len(need)}개 중 {len(have)}개 준비됨")
    if app_mode() == "체험":
        if st.button("체험용 데이터로 한 번에 채우기", type="primary", icon=":material/science:", key="fill_demo"):
            with st.spinner("체험용 데이터를 준비하는 중…"):
                fill_demo(plan, loaded, sources)
            st.session_state["just_ready"] = True
            st.rerun()
        st.caption("🧪 명세서와 같은 형식의 가상 데이터(수치 의미 없음) · 센터 PC에서는 아래처럼 실제 CSV를 받습니다")
    last = pd.Period(date.today(), "M") - 1
    to_ym, from_ym = last.strftime("%Y%m"), (last - 11).strftime("%Y%m")
    missing = [r for r in need if r.table_id not in loaded]
    if missing:
        r = missing[0]
        with st.container(key="howto"):
            st.markdown(f"<div class='howto-h'>📥 {esc(SHORT_DATA.get(r.table_id, FRIENDLY.get(r.table_id, r.table_name)))}"
                        f" 받는 법</div><div class='muted'>센터 표 {r.table_id} · {esc(r.table_name)}</div>",
                        unsafe_allow_html=True)
            g = guide_for(get_table(cat, r.table_id), cfg, from_ym, to_ym, plan.slots.regions, plan.slots.business)
            st.markdown("<ol>" + "".join(f"<li>{esc(line)}</li>" for line in g.steps) + "</ol>", unsafe_allow_html=True)
            if g.url:
                st.link_button("데이터 화면 바로 열기", g.url, icon=":material/open_in_new:")
            if g.query:
                st.code(g.query, language="sql")
            st.caption("✨ 받기만 하면 이 화면이 알아서 넣고, 모두 모이면 결과로 넘어갑니다")
        if len(missing) > 1:
            with st.expander(f"나머지 {len(missing) - 1}개 받는 법"):
                for r2 in missing[1:]:
                    g2 = guide_for(get_table(cat, r2.table_id), cfg, from_ym, to_ym, plan.slots.regions,
                                   plan.slots.business)
                    st.markdown(f"**{esc(SHORT_DATA.get(r2.table_id, r2.table_name))}** (센터 표 {r2.table_id})")
                    st.markdown("\n".join(f"{i}. {line}" for i, line in enumerate(g2.steps, 1)))
                    if g2.url:
                        st.link_button("데이터 화면 바로 열기", g2.url, icon=":material/open_in_new:")
    if have:
        with st.expander(f"준비된 데이터 {len(have)}개 보기 · 바꾸기"):
            for r in have:
                c_a, c_b = st.columns([4, 1])
                c_a.markdown(f"✅ **{esc(SHORT_DATA.get(r.table_id, r.table_name))}** — "
                             f"<span class='muted'>{esc(sources.get(r.table_id, ''))}</span>", unsafe_allow_html=True)
                if c_b.button("바꾸기", type="tertiary", key=f"swap_{r.table_id}"):
                    loaded.pop(r.table_id, None)
                    sources.pop(r.table_id, None)
                    st.session_state.pop("result", None)
                    st.session_state["auto_ok"] = False
                    st.rerun()
    with st.expander("받은 파일을 직접 넣기", expanded=bool(missing) and app_mode() != "체험"):
        ups = st.file_uploader("받은 CSV를 여기에 끌어다 놓아도 됩니다(여러 개 가능)", type=["csv"],
                               accept_multiple_files=True, key="ups")
    for upf in ups or []:
        key = f"up_{upf.name}_{upf.size}"
        if st.session_state.get(key):
            continue
        lt = load_center_csv(io.BytesIO(upf.getvalue()), cat)
        st.session_state[key] = True
        if lt.table_id:
            loaded[lt.table_id], sources[lt.table_id] = lt, f"넣은 파일 {upf.name}"
            ss("uploaded_names", []).append(upf.name)
            st.toast(f"{FRIENDLY.get(lt.table_id, lt.table['name'])} 파일을 넣었어요")
            st.session_state["just_ready"] = True
        else:
            st.error(f"{upf.name}: 명세서의 어느 표인지 알아보지 못했습니다. " + " ".join(lt.notes))
    if missing:
        watch_downloads(cfg, need)
        if st.button("내려받기 폴더 지금 확인", type="tertiary", icon=":material/refresh:", key="scan_now"):
            st.rerun()

    all_ready = all(r.table_id in loaded for r in need)
    if all_ready and st.session_state.get("auto_ok", True) and st.session_state.pop("just_ready", False):
        st.toast(f"데이터 {len(need)}개가 모두 준비돼 결과로 넘어갑니다")
        st.session_state.pop("result", None)
        go(3)
        st.rerun()
    st.session_state.pop("just_ready", None)
    b1, _, b3 = st.columns([1, 1, 2])
    if b1.button("← 질문 고치기", key="back1"):
        go(1)
        st.rerun()
    in_plan = {r.table_id for r in need}
    core = (CORE_TABLE in loaded) if CORE_TABLE in in_plan else any(t in loaded for t in in_plan)
    label = "결과 보기 →" if all_ready else "지금 있는 데이터로 먼저 보기 →"
    if b3.button(label, type="primary", disabled=not core, width="stretch", key="to_result"):
        st.session_state.pop("result", None)
        go(3)
        st.rerun()
    if not all_ready and core:
        miss = [SHORT_DATA.get(r.table_id, r.table_name) for r in need if r.table_id not in loaded]
        b3.caption("빠지는 분석: " + ", ".join(miss))
    elif not core:
        b3.caption(f"남은 일: {SHORT_DATA[CORE_TABLE]} 파일 — 받으면 자동으로 넘어갑니다.")


@st.fragment(run_every="3s")
def watch_downloads(cfg: dict, need):
    """내려받기 폴더를 3초마다 훑어, 맞는 CSV가 생기면 바로 넣는다."""
    loaded, sources = st.session_state["loaded"], st.session_state["sources"]
    seen = ss("seen_files", set())
    for ff in recent_downloads(cfg, cat):
        key = f"{ff.path}|{ff.modified}"
        if key in seen or not ff.table_id or ff.table_id not in {r.table_id for r in need}:
            continue
        seen.add(key)
        loaded[ff.table_id] = load_path(str(ff.path), ff.modified)
        sources[ff.table_id] = f"내려받은 파일 {ff.path.name}"
        ss("my_downloads", []).append(str(ff.path))
        st.session_state["just_ready"] = True
        st.toast(f"{FRIENDLY.get(ff.table_id, ff.table_name)} 파일을 찾아 넣었어요")
        st.rerun(scope="app")


# ③ 결과 ─────────────────────────────────────────────────────
def fingerprint(plan: Plan, loaded: dict) -> str:
    parts = [plan.slots.question, plan.slots.purpose, ",".join(plan.slots.regions), ",".join(plan.slots.city),
             ",".join(plan.slots.business), str(plan.slots.segment), ",".join(plan.slots.views)]
    for tid in sorted(loaded):
        lt = loaded[tid]
        parts.append(f"{tid}:{len(lt.df)}:{period_of(lt)}:{'가상' if lt.synthetic else '실제'}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def analyze(plan: Plan, loaded: dict, fp: str) -> dict:
    log = []
    s = plan.slots
    log.append(("질문 해석", f"동네 {', '.join(s.regions or s.city) or '전체'} · 업종 "
                            f"{_short_biz(s.business, s.biz_label) or '전체'} · 목적 {PURPOSE_LABEL.get(s.purpose, s.purpose)}"))
    pub = make_public_plan(s, cat) if PUBLIC_ID in loaded else None
    extra = [x for x in (pub.steps if pub else [])            # 같은 공개 단계(상가정보)는 한 번만
             if not any(x.tool == y.tool and x.table_id == y.table_id for y in plan.steps)]
    run = Plan(s, plan.steps + extra, plan.requests + (pub.requests if pub else []),
               plan.notes, plan.scope_notes, focus_label=plan.focus_label)
    n_pub = sum(1 for x in run.steps if x.table_id.startswith(("허브-", "공개-")))
    log.append(("분석 계획", f"검증된 분석 도구 {len(run.steps)}개(센터 {len(run.steps) - n_pub} · 공개 {n_pub})"))
    outs = run_plan(run, loaded)
    done = [o for o in outs if o.result is not None]
    miss = [o for o in outs if o.result is None]
    log.append(("도구 실행", f"{len(done)}개 완료" + (f", 데이터가 없어 {len(miss)}개 건너뜀" if miss else "")))
    checks = [c for o in done for c in o.result.checks]
    log.append(("자동 검산", f"{sum(1 for c in checks if c.startswith(('검산', '기간 확인', '중복 방지')))}건 통과"
                + (" · 주의 " + str(sum(1 for c in checks if c.startswith(('주의', '기간 누락')))) + "건"
                   if any(c.startswith(('주의', '기간 누락')) for c in checks) else "")))
    verdicts = {o.export_verdict for o in done}
    log.append(("반출 기준 점검", "모든 결과가 비중·지수·순위(응용집계) → " + "·".join(sorted(verdicts))))
    answer = build_answer(run, outs, loaded)
    log.append(("결론 정리", "공개 규칙표로 판정(손님·계절·시장 크기·경쟁·요일·시간대·최근 방문객·지구 유형) — AI는 판정에 쓰지 않음"))
    folder = session_dir() / f"view_{fp[:8]}"
    charts = {}
    hl = _hours_label()
    for c in answer.cards + ([answer.public_card] if answer.public_card else []):
        o = outs[c.step_index]
        fl = o.step.params.get("focus_label", "")
        if c.key == "public":
            fl = next((x.step.params.get("focus_label", "") for x in outs
                       if x.step.table_id == PUBLIC_ID and x.step.tool == "compare_share"), "")
        charts[c.key] = render(c, o, folder / f"{c.key}.png", focus=s.regions, focus_label=fl, hours_label=hl,
                               dpi=130)
    rid = f"R-{date.today():%Y%m%d}-{fp[:6]}"
    pub_answer = None
    if answer.synthetic and pub:              # 체험: 실제 공개 데이터(597·상가정보)만으로 본 답을 먼저 보여 준다
        real = {k: v for k, v in loaded.items() if k.startswith(("허브-", "공개-"))}
        pub_answer = build_answer(pub, run_plan(pub, real), real)
    return {"fp": fp, "run": run, "outs": outs, "answer": answer, "charts": charts, "log": log, "rid": rid,
            "pub_answer": pub_answer}


def step_result(loaded: dict, sources: dict):
    plan: Plan = st.session_state.get("plan")
    if plan is None:
        go(1)
        st.rerun()
    fp = fingerprint(plan, loaded)
    res = st.session_state.get("result")
    if not res or res["fp"] != fp:
        with st.status("Agent가 분석하고 있어요", expanded=True) as status:
            t0 = time.time()
            res = analyze(plan, loaded, fp)
            for name, detail in res["log"]:
                st.write(f"**{name}** — {detail}")
            status.update(label=f"Agent 작업 완료 · {len(res['log'])}단계 · {time.time() - t0:.1f}초 · 재현 번호 {res['rid']}",
                          state="complete", expanded=False)
        st.session_state["result"] = res
        for k in ("bundle", "pack"):
            st.session_state.pop(k, None)
    else:
        with st.status(f"Agent 작업 완료 · {len(res['log'])}단계 · 재현 번호 {res['rid']}", state="complete"):
            for name, detail in res["log"]:
                st.write(f"**{name}** — {detail}")
    a = res["answer"]
    if a.synthetic and res.get("pub_answer"):
        real_answer_card(res["pub_answer"])
    if a.synthetic:
        st.markdown("<div class='demo-band'>🧪 아래는 센터 데이터 자리에 체험(가상) 데이터를 넣은 예시예요 · "
                    "경쟁·최근 방문객·지구 유형·공개 데이터 확인 카드는 실제 값</div>", unsafe_allow_html=True)
    answer_card(a, res)
    outs = res["outs"]
    miss = [o for o in outs if o.result is None]
    if miss:
        names = sorted({FRIENDLY.get(o.step.table_id, o.step.table_id) for o in miss})
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"<span class='muted'>데이터가 없어 빠진 분석: {esc(', '.join(names))}</span>", unsafe_allow_html=True)
        if c2.button("데이터 넣기", key="add_data"):
            go(2, auto_ok=False)
            st.rerun()
    for i, c in enumerate(a.cards):
        evidence_card(c, res, i)
    if a.public_card:
        evidence_card(a.public_card, res, 99)
    with st.expander(f"주의할 점 {len(a.caveats)}가지", icon=":material/warning:"):
        for line in a.caveats:
            st.markdown(f"- {line}")
    b1, b2, b3 = st.columns([1, 1, 2])
    if b1.button("← 데이터 바꾸기", key="back2"):
        go(2, auto_ok=False)
        st.rerun()
    if b2.button("다른 질문 하기", key="newq"):
        st.session_state.pop("result", None)
        go(1)
        st.rerun()
    if b3.button("결과 가져가기 →", type="primary", width="stretch", key="to_take"):
        go(4)
        st.rerun()


def answer_card(a, res):
    with st.container(key="answer"):
        st.markdown(f"<div class='qline' style='margin:0'>{esc(a.question_line)}</div><div class='verdict'>{esc(a.headline)}</div>"
                    + (f"<div class='core'>{esc(a.core)}</div>" if a.core else "")
                    + (f"<div class='market'>{esc(a.market)}</div>" if a.market else ""), unsafe_allow_html=True)
        if a.kpis:
            cols = st.columns(len(a.kpis))
            for col, k in zip(cols, a.kpis):
                col.metric(k.label, k.value, k.delta or None, delta_color="off", delta_arrow="off",
                           help=k.help or None, border=True)
        if a.badges:
            st.markdown(" ".join(f":{'blue' if c == 'blue' else 'gray'}-badge[{esc(t)}]" for t, c in a.badges))
        if a.actions:
            st.markdown("<div class='eyebrow' style='margin-top:8px'>그래서 할 일</div><div class='acts'>"
                        + "".join(f"<div><i>{n}</i>{esc(x)}</div>" for n, x in enumerate(a.actions, 1)) + "</div>",
                        unsafe_allow_html=True)
        if a.report_sentences:
            st.markdown("<div class='eyebrow' style='margin-top:6px'>보고서에 쓸 문장</div>", unsafe_allow_html=True)
            st.code("\n".join(a.report_sentences), language=None, wrap_lines=True)
            st.caption(md("인용 표기: " + a.citation))
        t1, t2 = st.columns([4, 1])
        t1.markdown("<div class='trust'>✓ 자동 검산 · 반출 점검 통과 · 판정은 공개 규칙(AI 아님)</div>", unsafe_allow_html=True)
        with t2.popover("판정 기준 보기", icon=":material/rule:"):
            st.markdown("**이번 결과에서 확인한 것** — " + " · ".join(esc(x) for x in a.trust))
            st.markdown("판정은 AI가 아니라 아래 **공개 규칙**으로 코드가 합니다. 같은 데이터면 늘 같은 결론입니다.")
            for name, rule, why in VERDICT_RULES:
                st.markdown(f"**{name}** — {rule}" + (f"  \n<span class='muted'>{esc(why)}</span>" if why else ""),
                            unsafe_allow_html=True)


def real_answer_card(a):
    """실제 공개 데이터(제주데이터허브 597 · 상가정보)만으로 본 답. 체험 화면에서 가상 예시보다 먼저 보여 준다."""
    with st.container(key="answer-real"):
        st.markdown("<span class='tag real'>실제 공개 데이터</span><span class='qline'>누구나 확인할 수 있는 값으로 먼저 본 답</span>"
                    f"<div class='verdict small'>{esc(a.headline)}</div>"
                    + (f"<div class='market'>{esc(a.market)}</div>" if a.market else ""), unsafe_allow_html=True)
        if a.kpis:
            cols = st.columns(len(a.kpis))
            for col, k in zip(cols, a.kpis):
                col.metric(k.label, k.value, k.delta or None, delta_color="off", delta_arrow="off",
                           help=k.help or None, border=True)
        with st.popover("출처 · 범위 보기", icon=":material/description:"):
            st.markdown(esc(" · ".join(a.basis)))
            st.caption("공개 데이터는 시 단위(597, 2016~2018)와 동네별 가게 수(상가정보)까지입니다. "
                       "동네 매출·요일·시간대는 센터 데이터로만 볼 수 있습니다.")


def evidence_card(c, res, i: int):
    outs = res["outs"]
    o = outs[c.step_index]
    with st.container(border=True, key=f"card-{i}"):
        st.markdown(f"<div class='eyebrow'>{esc(c.eyebrow)}{' · 가상 데이터' if c.synthetic else ''}</div>"
                    f"<div class='card-title'>{esc(c.title)}</div>", unsafe_allow_html=True)
        left, right = st.columns([3, 2], gap="medium")
        png = res["charts"].get(c.key)
        if png:
            left.image(str(png), width="stretch")
            if LEGEND.get(c.key):
                left.caption(LEGEND[c.key])
        if res["answer"].neutral and c.report:
            right.markdown(f"<div class='explain'>{esc(c.explain)}</div>", unsafe_allow_html=True)
            right.markdown("<div class='eyebrow'>보고서에 쓸 문장</div>", unsafe_allow_html=True)
            right.code(c.report, language=None, wrap_lines=True)
        else:
            right.markdown(f"<div class='explain'>{esc(c.explain)}</div><div class='sowhat'><b>그래서</b> {esc(c.sowhat)}</div>",
                           unsafe_allow_html=True)
        lt = st.session_state["loaded"].get(o.step.table_id)
        with right.container(horizontal=True, gap="small"):
            with st.popover("숫자 표", icon=":material/table:"):
                from jeju_agent.korean import korean_table
                from jeju_agent.report import exportable
                st.dataframe(korean_table(exportable(o), lt.table if lt else None), hide_index=True)
                st.caption("비중·순위·지수만 보여 줍니다(합계·원자료 없음).")
            with st.popover("출처 · 참고", icon=":material/info:"):
                for e in c.extra:
                    st.markdown(f"- {esc(e)}")
                if lt is not None:
                    st.caption(md(source_line(lt)))


# ④ 가져가기 ──────────────────────────────────────────────────
def step_takeout(loaded: dict):
    res = st.session_state.get("result")
    plan: Plan = st.session_state.get("plan")
    if not res or plan is None:
        go(3)
        st.rerun()
    a = res["answer"]
    st.subheader("결과 가져가기")
    startup = plan.slots.purpose in ("사업계획서·창업", "가게·회사 운영")
    st.markdown("<div class='get3'>"
                "<div><div class='i'>📄</div><b>분석 보고서</b><span>결론 · 근거 · 출처</span></div>"
                + ("<div><div class='i'>📝</div><b>사업계획서 근거팩</b><span>항목별 문장 · 그림</span></div>" if startup else
                   "<div><div class='i'>🖼️</div><b>근거 그림</b><span>PNG · 출처 표기</span></div>")
                + "<div><div class='i'>📦</div><b>반출 신청 묶음</b><span>버튼 한 번 · 신청 문구까지</span></div>"
                "</div>", unsafe_allow_html=True)
    bundle_box = st.container(border=True)          # 묶음 버튼을 맨 위에 보이고, 내용은 공고 선택 뒤에 채운다
    # 1) 지원사업(창업·운영 목적) — 고른 공고가 근거팩·활용 사유에 들어간다
    chosen = programs_section(plan) if startup else []
    if not startup:
        with st.expander("지원사업 찾기(선택)"):
            chosen = programs_section(plan, inner=True)
    # 2) 활용 사유 — 자동으로 채우고, 바꾸고 싶을 때만 고친다
    why = {"사업계획서·창업": "창업 사업계획서 작성", "가게·회사 운영": "가게 운영 계획 수립",
           "현황자료·보고서": "현황 보고서 작성", "논문·연구": "연구 논문 작성"}.get(plan.slots.purpose, "사업계획 수립")
    default_reason = (f"「{chosen[0].title}」 신청서 시장분석 근거" if chosen else
                      f"{plan.focus_label} {why}을 위한 시장 분석" if plan.focus_label else f"{why}을 위한 시장 분석")
    if st.session_state.get("reason_auto") != default_reason:      # 공고 선택이 바뀌면 기본 문구도 바꾼다
        st.session_state["reason_auto"] = default_reason
        st.session_state["use_purpose_in"] = default_reason
    ss("use_purpose_in", default_reason)
    # 3) 묶음 만들기
    with bundle_box:
        st.markdown("<div class='howto-h'>📦 반출 신청 묶음</div>"
                    + ("<span class='muted'>아래 지원사업에서 '근거팩에 넣기'를 고르면 근거팩에 함께 들어가요</span>"
                       if startup else ""), unsafe_allow_html=True)
        r1, r2 = st.columns([5, 1])
        r1.markdown(f"<div class='reason-line'>활용 사유: <b>{esc(st.session_state['use_purpose_in'])}</b></div>",
                    unsafe_allow_html=True)
        with r2.popover("바꾸기", icon=":material/edit:"):
            st.text_input("활용 사유", key="use_purpose_in")
        reason = st.session_state["use_purpose_in"]
        key = hashlib.sha256(f"{res['fp']}|{reason}|{','.join(p.title for p in chosen)}".encode()).hexdigest()[:12]
        b = st.session_state.get("bundle")
        stale = b is not None and st.session_state.get("bundle_key") != key
        label = "묶음 다시 만들기(조건이 바뀜)" if stale else "반출 신청 묶음 만들기"
        if (b is None or stale) and st.button(label, type="primary", icon=":material/inventory_2:", key="make_bundle",
                                              width="stretch"):
            with st.spinner("보고서와 그림을 만드는 중…"):
                folder = session_dir() / f"take_{key}"
                b = build_report(res["run"], res["outs"], loaded, folder, purpose=reason, answer=a, use_purpose=reason)
                pack = build_evidence_pack(b, plan.slots.question, chosen, reason) if startup else None
            st.session_state.update(bundle=b, pack=pack, bundle_key=key)
            st.rerun()
        if b is not None and not stale:
            c1, c2, c3 = st.columns(3)
            c1.download_button("반출 묶음(zip)", b.zip.read_bytes(), b.zip.name, type="primary",
                               icon=":material/download:", width="stretch")
            c2.download_button("분석 보고서(DOCX)", b.docx.read_bytes(), b.docx.name, icon=":material/description:",
                               width="stretch")
            if st.session_state.get("pack"):
                pk = st.session_state["pack"]
                c3.download_button("사업계획서용 근거팩(DOCX)", pk.read_bytes(), pk.name, icon=":material/description:",
                                   width="stretch")
            st.markdown("**센터 반출 신청 화면에 묶음을 올리고, 아래 문구를 복사해 붙여 넣으세요.** "
                        "<span class='muted'>승인되면(최대 5일) 제주데이터허브에서 받습니다.</span>", unsafe_allow_html=True)
            st.code(b.request_txt.read_text(encoding="utf-8"), language=None, wrap_lines=True, height=200)
            with st.expander("가져갈 수 있는지 자동 점검(센터 직원용)"):
                for s_ in b.sections:
                    if s_["missing"]:
                        continue
                    st.markdown(f"- {esc(s_['title'])} — 수치 종류: 비중·순위·지수(응용집계) · 판정: "
                                f"{esc(s_.get('verdict') or '공개 데이터(반출 심사 대상 아님)')}")
                st.caption("원본 데이터·데이터 미리보기는 묶음에 넣지 않습니다. 그림은 PNG만 씁니다(반출 정책).")
    if st.button("← 결과로", key="back3"):
        go(3, auto_ok=False)
        st.rerun()


STATUS = {"창업 준비 중": "예비창업자", "운영 1년 미만": "1년미만", "운영 1~3년": "3년미만", "운영 3년 이상": "7년미만"}
AGES = {"말하지 않음": None, "39세 이하": 35, "40대": 45, "50대": 55, "60세 이상": 62}
NEEDS = {"돈(융자·보증)": ["융자", "자금", "보증", "대출", "이차보전"], "배우기(교육·컨설팅)": ["교육", "컨설팅", "멘토링"],
         "사람(인건비·보험료)": ["인건비", "고용", "보험료", "채용"], "알리기(홍보·판로)": ["홍보", "판로", "마케팅"],
         "가게 꾸미기(시설)": ["시설", "환경개선", "리모델링", "간판"]}


def programs_section(plan: Plan, inner: bool = False) -> list:
    """프로필 칩을 바꾸면 바로 다시 거른다(규칙 판정, AI 없음). 반환: 근거팩에 넣기로 고른 공고."""
    box = st.container() if inner else st.container(border=True)
    with box:
        st.markdown(("" if inner else "<div class='howto-h'>🎁 신청해 볼 지원사업</div>") + "<span class='muted'>칩을 고르면 바로 다시 찾아요</span>", unsafe_allow_html=True)
        s = plan.slots
        biz = _short_biz(s.business, s.biz_label)
        from jeju_agent.synth import _city_of
        emd = [r[1] for r in ref_rows(get_table(cat, "4-11"), "행정동")]
        city = s.city[0] if s.city else (_city_of(s.regions[0], emd) if s.regions else "제주시")
        stage = st.segmented_control("지금 상태", list(STATUS), default="창업 준비 중"
                                     if s.purpose == "사업계획서·창업" else "운영 1~3년", key="pg_stage")
        c2, c3 = st.columns([3, 2])
        age = c2.segmented_control("대표자 나이대", list(AGES), default="말하지 않음", key="pg_age")
        where = c3.segmented_control("가게 위치", ["제주시", "서귀포시"], default=city, key="pg_city")
        with st.expander("더 정확하게(선택): 필요한 도움 · 해당 사항"):
            needs = st.pills("필요한 도움(여럿 선택, 순서에만 반영)", list(NEEDS), selection_mode="multi", key="pg_needs")
            t1, t2, t3, t4 = st.columns(4)
            traits = [t for t, on in (("여성", t1.checkbox("여성 대표", key="pg_f")),
                                      ("장애인", t2.checkbox("장애인", key="pg_d")),
                                      ("재창업", t3.checkbox("재창업", key="pg_r"))) if on]
            show_events = t4.checkbox("행사·교육도 보기", key="pg_ev")
        prof = Profile(stage=STATUS.get(stage or "창업 준비 중", "예비창업자"), age=AGES.get(age or "말하지 않음"),
                       needs=[k for n in (needs or []) for k in NEEDS[n]], city=where or "", traits=list(traits))
        if prof.age and prof.age <= 39:
            prof.traits.append("청년(만 39세 이하)")
        if prof.stage != "예비창업자":
            prof.traits.append("소상공인")
        prof = profile_from_question(prof, [biz] if biz else [], where or "")
        progs, src = load_programs(wait=False)       # 미리 받는 중이면 저장본으로 바로(화면이 멈추지 않게)
        stats: dict = {}
        got = match(progs, prof, stats=stats)
        from jeju_agent.eligibility import guess_kind
        from jeju_agent.programs import _d
        got = [p for p in got if not (_d(p.end) and _d(p.end) <= date.today())]     # 오늘 마감은 숨김
        events = [p for p in got if guess_kind(p) == "행사·공모전"]
        if not show_events:
            got = [p for p in got if p not in events]
        ai_key = f"{prof}|{show_events}"
        ai = st.session_state.get("pg_ai") if st.session_state.get("pg_ai_key") == ai_key else None
        res, note = ai if ai else screen(got, prof, use_ai=False, limit=12)
        now = [x for x in res if x.verdict == "해당" and not x.program.after_open]
        after = [x for x in res if x.program.after_open and x.verdict != "해당 안 됨"]
        check = [x for x in res if x.verdict == "확인 필요" and not x.program.after_open]
        no = [x for x in res if x.verdict == "해당 안 됨"]
        dropped = sum(stats.get("dropped", {}).values())
        st.markdown(f"<span class='muted'>모집 중 {stats.get('total', 0):,}건 → 조건으로 {dropped:,}건 거름 → "
                    f"{len(got):,}건 중 상위 {len(res)}건 판정 (업종: {esc(biz or '없음')}, 질문에서 가져옴)</span>",
                    unsafe_allow_html=True)
        with st.popover("거른 이유 보기", icon=":material/filter_alt:"):
            for k_, v_ in stats.get("dropped", {}).items():
                st.markdown(f"- {k_}: {v_:,}건")
            if not show_events:
                st.markdown(f"- 행사·공모전(숨김): {len(events):,}건")
            st.caption("오늘 마감인 공고도 숨겼습니다.")
        code, msg = ai_status()
        if not ai and code != "on" and code != "off_nokey":
            st.caption(f"AI 자격 대조를 쓸 수 없습니다 — {msg} 아래 판정은 공고문 대상 문장으로 정한 규칙 추정입니다.")
        if code == "on" and not ai and st.button("AI로 공고문과 자격 대조하기(선택, 10초 안팎)", type="tertiary",
                                                   icon=":material/fact_check:", key="pg_ai_btn"):
            with st.spinner("공고문의 신청 자격을 확인하는 중…"):
                st.session_state["pg_ai"] = screen(got, prof, use_ai=True, limit=12)
                st.session_state["pg_ai_key"] = ai_key
            st.rerun()
        if not now:
            st.info(f"지금 바로 신청할 수 있다고 판정한 공고는 없습니다(모집 중 {stats.get('total', 0):,}건 기준). "
                    "아래 '조건 확인' 공고와 '가게를 연 뒤' 공고를 확인해 보세요.", icon=":material/info:")
        chosen = []
        for title, group in (("지금 신청할 수 있어요", now), ("가게를 연 뒤 받을 수 있어요", after),
                             ("조건 확인이 필요해요", check)):
            if group:
                st.markdown(f"**{title}** ({len(group)}건)")
                for x in group[:3]:
                    if program_card(x):
                        chosen.append(x.program)
        if no:
            with st.expander(f"해당하지 않는 공고 {len(no)}건(이유)"):
                for x in no:
                    st.markdown(f"- {esc(x.program.title)} — {esc(x.reason)}")
        st.caption(md(note + f" · 공고 출처: {src} · 공공누리 제3유형(출처표시·변경금지)"))
    return chosen


def program_card(x) -> bool:
    p = x.program
    with st.container(border=True):
        from jeju_agent.programs import _d
        e = _d(p.end)
        when = f"D-{(e - date.today()).days} · {e.isoformat()} 마감" if e else (p.period_text or "예산 소진 시까지")
        chips = [f"<span class='{'d' if e else ''}'>{esc(when)}</span>"]
        chips += [f"<span>{esc(t)}</span>" for t in (x.kind, "방문 접수" if p.visit_required else "", p.org) if t]
        st.markdown(f"<div class='pc-title'>{esc(p.title)}</div><div class='pc-meta'>{''.join(chips)}</div>"
                    f"<div class='pc-why'>{esc(x.reason)}</div>"
                    + (f"<div class='muted'>확인할 것: {esc(', '.join(x.check))}</div>" if x.check else ""),
                    unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 2, 1])
        meth = ", ".join(p.apply_methods) or "공고 확인"
        c1.markdown(f"<span class='muted'>신청: {esc(meth)} · 판정: {esc(x.by)}</span>", unsafe_allow_html=True)
        pick = c2.checkbox("근거팩에 넣기", key=f"pick_{hashlib.md5(p.title.encode()).hexdigest()[:10]}")
        if p.url:
            c3.link_button("공고 보기", p.url, icon=":material/open_in_new:")
        return pick


# ── 운영자 페이지(/admin, PIN) ───────────────────────────────
LOCK_MIN = 15


def admin_page():
    inject_css()
    st.markdown(f"<div class='brand'>{APP_NAME} · 운영자</div>", unsafe_allow_html=True)
    ok_at = st.session_state.get("admin_at", 0)
    if ok_at and time.time() - ok_at > LOCK_MIN * 60:
        st.session_state.pop("admin_at", None)
        ok_at = 0
    if not ok_at:
        if not admin_mod.has_pin():
            st.warning("운영자 PIN이 아직 없습니다. 프로그램 폴더의 set_pin.bat(또는 `python -m jeju_agent.admin set-pin`)으로 "
                       "PIN을 정한 뒤 다시 여세요. PIN을 정하기 전에는 운영자 설정이 열리지 않습니다.")
            return
        if os.environ.get("JEJU_AGENT_DEMO"):
            st.info("공개 데모에서는 운영자 설정을 열 수 없습니다. 센터 설치본에서 PIN으로 엽니다.")
            return
        left = admin_mod.locked_for()
        if left:
            st.error(f"PIN을 여러 번 틀려 잠겼습니다. {left // 60 + 1}분 뒤 다시 시도하세요.")
        with st.form("pin"):
            pin = st.text_input("운영자 PIN(숫자 6~12자리)", type="password")
            if st.form_submit_button("열기", type="primary"):
                if admin_mod.check_pin(pin.strip()):
                    st.session_state["admin_at"] = time.time()
                    st.rerun()
                left = admin_mod.locked_for()
                st.error(f"PIN이 맞지 않습니다." + (f" {left // 60 + 1}분 뒤 다시 시도하세요." if left else ""))
        return
    st.session_state["admin_at"] = time.time()
    c1, c2 = st.columns([4, 1])
    c1.caption(f"{LOCK_MIN}분 동안 아무것도 하지 않으면 잠깁니다.")
    if c2.button("잠그기", icon=":material/lock:"):
        st.session_state.pop("admin_at", None)
        st.rerun()
    sett = llm_mod.load_settings()
    cfg = load_config()

    st.subheader("실행 모드")
    mode = st.segmented_control("모드", ["체험", "센터"], default=sett.get("app_mode", "체험"), key="adm_mode")
    st.caption("체험: 센터 밖 시연용(가상 데이터 버튼을 위에 보여 줌). 센터: 센터 PC용(실제 센터 CSV 위주, 연습 버튼은 접어 둠).")

    st.subheader("데이터 폴더")
    cfg["preload_dir"] = st.text_input("센터가 미리 넣어 둔 데이터 폴더", cfg.get("preload_dir", ""),
                                       placeholder=r"C:\JejuDataAgent\data\preloaded")
    cfg["watch_dir"] = st.text_input("방문자 내려받기 폴더(자동 감지)", cfg.get("watch_dir", "~/Downloads"))
    st.markdown("**표별 바로가기**")
    rows = [{"표": t["id"], "데이터": t["name"], "url": cfg.get("tables", {}).get(t["id"], {}).get("url", ""),
             "path": cfg.get("tables", {}).get(t["id"], {}).get("path", ""),
             "query": cfg.get("tables", {}).get(t["id"], {}).get("query", "")} for t in cat["tables"]]
    ed = st.data_editor(pd.DataFrame(rows), hide_index=True, disabled=["표", "데이터"], width="stretch",
                        height=280)
    st.caption("url·query에 {from_ym} {to_ym} {from_year} {to_year} {bjd} {biz_nm}를 쓰면 질문에 맞게 채워집니다.")

    st.subheader("AI·외부 API")
    st.caption("키는 이 PC의 config/local_settings.json에만 저장되고, 화면에는 끝 4자리만 보입니다. 제출물·저장소에는 들어가지 않습니다.")
    model = llm_mod.DEFAULTS["model"]
    a1, a2, a3 = st.columns(3)
    a1.text_input("AI 모델(고정)", model, disabled=True,
                  help="상위 모델(gpt-6-sol)과 비교해 정확도 차이가 없어 비용이 20분의 1인 이 모델만 씁니다.")
    base = a2.text_input("API 주소(OpenAI 호환)", sett.get("base_url", "https://api.openai.com/v1"))
    budget = a3.number_input("월 사용 한도(달러)", min_value=0.0, value=float(sett.get("monthly_budget_usd", 10.0)), step=1.0)
    ai_on = st.toggle("방문자 화면에서 AI 도움 쓰기(질문 해석·지원사업 자격 확인)", value=sett.get("ai_on", True))

    def tail(v):
        return f"…{v[-4:]} 저장됨" if v else "없음"

    k1, k2, k3 = st.columns(3)
    new_llm = k1.text_input("AI API 키", type="password", placeholder="변경할 때만 입력",
                            help=tail(sett.get("api_key", "")))
    k1.caption("AI API 키: " + tail(sett.get("api_key", "")) + (" · 환경변수 있음" if os.environ.get("OPENAI_API_KEY") else ""))
    new_dh = k2.text_input("제주데이터허브 프로젝트키", type="password", placeholder="변경할 때만 입력")
    k2.caption("데이터허브 키: " + tail(sett.get("jejudatahub_app_key", "")))
    new_dg = k3.text_input("공공데이터포털 인증키", type="password", placeholder="변경할 때만 입력")
    k3.caption("공공데이터포털 키: " + tail(sett.get("data_go_kr_key", "")))
    if st.button("모두 저장", type="primary", icon=":material/save:"):
        if base.rstrip("/") != sett.get("base_url", "https://api.openai.com/v1").rstrip("/") and not new_llm.strip() \
                and sett.get("api_key"):
            st.error("API 주소를 바꾸면 키가 그 주소로 전송됩니다. 안전을 위해 AI API 키를 다시 입력해 주세요.")
        else:
            cfg["tables"] = {r["표"]: {k: r[k] for k in ("url", "path", "query") if r[k]}
                             for _, r in ed.iterrows() if r["url"] or r["path"] or r["query"]}
            save_config(cfg)
            sett.update(model=model, base_url=base, monthly_budget_usd=budget, ai_on=ai_on, app_mode=mode or "체험")
            for name, v in (("api_key", new_llm), ("jejudatahub_app_key", new_dh), ("data_go_kr_key", new_dg)):
                if v.strip():
                    sett[name] = v.strip()
            llm_mod.save_settings(sett)
            st.success("저장했습니다.")

    st.subheader("방문 예약 준비(직원용)")
    st.caption("이용 신청·전화 상담 때 방문자 질문을 넣으면 필요한 센터 표·기간 목록과 안내문이 나옵니다. "
               "해당 CSV를 미리 받아 '센터가 미리 넣어 둔 데이터 폴더'에 두면, 방문자는 데이터 단계를 건너뜁니다.")
    pq = st.text_input("방문자 질문", placeholder="예: 애월읍에 카페 열면 어때?", key="adm_prep_q")
    pp = st.selectbox("활용 목적", PURPOSES, format_func=lambda x: PURPOSE_LABEL[x], key="adm_prep_p")
    if pq:
        from jeju_agent.visit_prep import make_prep, to_html
        prep = make_prep(pq, pp, Profile(), cat)
        last = pd.Period(date.today(), "M") - 1
        for r in prep.plan.requests:
            st.markdown(f"- **{r.table_id}** {esc(r.table_name)} — 기간 {(last - 11).strftime('%Y.%m')}&#126;{last.strftime('%Y.%m')}"
                        f" · {esc('; '.join(r.conditions[:1]))}")
        st.download_button("안내문(인쇄용 HTML)", to_html(prep).encode("utf-8"), "방문안내.html",
                           icon=":material/print:")

    st.subheader("공개 데이터 새로 받기(제주데이터허브 597)")
    dh_key = sett.get("jejudatahub_app_key") or os.environ.get("JEJUDATAHUB_APP_KEY", "")
    if not dh_key:
        st.caption("데이터허브 프로젝트키를 넣으면 최신 자료를 받아 data/public에 저장합니다. 지금은 동봉 파일(2016.09~2018.12)을 씁니다.")
    elif st.button("지금 받기(1~2분)", icon=":material/cloud_download:"):
        from jeju_agent.datahub_api import fetch_all, save_csv
        with st.spinner("받는 중…"):
            try:
                df = fetch_all(get_table(cat, PUBLIC_ID), dh_key)
                ym = sorted(df["dtYearMonth"].astype(str))
                path = save_csv(df, ROOT / "data" / "public" / f"허브597_내국인관광객_카드이용_{ym[0]}-{ym[-1]}.csv")
                public_table.clear()
                st.success(f"저장했습니다: {path.name} ({len(df):,}행)")
            except Exception:  # noqa: BLE001
                st.error("받지 못했습니다. 키와 인터넷 연결을 확인해 주세요.")

    st.subheader("AI 사용량")
    pct = llm_mod.usage_pct()
    st.progress(min(pct, 100) / 100, text=f"이번 달 {llm_mod.pct_label(pct)} 사용 (방문자 화면에는 %만 보입니다)")
    st.caption(f"운영자 참고: 이번 달 \\${llm_mod.month_spent():.4f} / 한도 \\${budget:.0f}. "
               "100%가 되면 방문자 화면에 'AI 꺼짐'이 뜨고 정해진 규칙으로만 답합니다. 다음 달 1일에 다시 0%부터 셉니다.")
    if llm_mod.USAGE.exists():
        import json
        rows = [json.loads(x) for x in llm_mod.USAGE.read_text(encoding="utf-8").splitlines()[-20:]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.page_link(visitor_page, label="방문자 화면으로", icon=":material/arrow_back:")


def code_version() -> str:
    """프로그램 코드·동봉 자료가 바뀌었는지 알아보는 표시(파일 이름·크기·수정 시각)."""
    h = hashlib.sha256()
    for f in sorted((ROOT / "jeju_agent").glob("*.py")) + sorted((ROOT / "data" / "public").glob("*.csv")):
        s_ = f.stat()
        h.update(f"{f.name}:{s_.st_size}:{s_.st_mtime_ns}".encode())
    return h.hexdigest()[:12]


@st.cache_resource(show_spinner=False)
def _cache_version() -> dict:
    return {"v": ""}


def refresh_caches_if_code_changed() -> None:
    """공개 데모는 새 코드를 올려도 프로세스가 그대로라 예전 체험 표가 캐시에 남는다 → 코드가 바뀌면 캐시를 비운다."""
    v, h = code_version(), _cache_version()
    if h["v"] != v:                      # 처음(빈 값)에도 비운다: 이 기능이 없던 예전 프로세스의 캐시까지 정리
        st.cache_resource.clear()
        st.cache_data.clear()
        h = _cache_version()
    h["v"] = v


refresh_caches_if_code_changed()
visitor_page = st.Page(visitor, title="분석", icon=":material/insights:", default=True)
admin_pg = st.Page(admin_page, title="운영자", icon=":material/lock:", url_path="admin", visibility="hidden")
st.navigation([visitor_page, admin_pg], position="hidden").run()
