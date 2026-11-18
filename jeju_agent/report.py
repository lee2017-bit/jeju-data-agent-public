"""결과물 만들기: 반출 가능한 표 → 한글 차트(PNG) → 보고서(DOCX·HTML) → 반출 신청서 초안 → 묶음(zip).

반출 정책에 맞추는 방법
- 반출용 표에는 응용집계(비중·순위·지수·증감률)만 남긴다. 합계 같은 단순집계 열은 뺀다.
  (응용집계는 수치 포함 반출 가능, 단순집계는 10 미만 처리 필요·텍스트 반출 원칙 불가)
- 차트는 PNG로만 만든다(정책: 시각화는 png·jpg).
- 보고서에는 데이터 원본 행·미리보기를 넣지 않는다(정책: 데이터 샘플 출력 포함 시 반출 불가).
"""

from __future__ import annotations

import html
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager  # noqa: E402

from .agent import StepOutcome  # noqa: E402
from .export_policy import export_request_lines  # noqa: E402
from .korean import fmt_month_short, korean_table  # noqa: E402
from .loader import LoadedTable  # noqa: E402
from .planner import Plan  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FONT_DIR = ROOT / "assets" / "fonts"
APPLIED_COLS = ("비중(%)", "순위", "지수", "대비(%)", "구분", "조건", "가게 수")   # 가게 수: 공개 상가정보(센터 데이터 아님)


def setup_korean_font() -> str:
    """Windows(맑은 고딕) 우선, 없으면 함께 배포한 나눔고딕."""
    names = {f.name for f in font_manager.fontManager.ttflist}
    for n in ("Malgun Gothic", "AppleGothic", "NanumGothic"):
        if n in names:
            plt.rcParams["font.family"] = n
            break
    else:
        for f in FONT_DIR.glob("NanumGothic*.ttf"):
            font_manager.fontManager.addfont(str(f))
        plt.rcParams["font.family"] = "NanumGothic"
    plt.rcParams["axes.unicode_minus"] = False
    return plt.rcParams["font.family"][0] if isinstance(plt.rcParams["font.family"], list) else plt.rcParams["font.family"]


TIME_COLS = ("base_year_month", "dtYearMonth", "base_date", "base_ymd")


def period_of(lt: LoadedTable) -> str:
    for c in TIME_COLS:
        if c in lt.df.columns and len(lt.df):
            a, b = str(lt.df[c].min()), str(lt.df[c].max())
            if len(a) == 6 and a == b:
                return f"{a[:4]}.{a[4:]} 기준"
            if len(a) == 6:
                return f"{fmt_month_short(a)}~{fmt_month_short(b)}"
            if len(a) == 8:
                return f"{a[:4]}.{a[4:6]}.{a[6:]}~{b[:4]}.{b[4:6]}.{b[6:]}"
            return f"{a}~{b}"
    return "기간 미상"


def is_public(table: dict | None) -> bool:
    return bool(table) and (table.get("id", "").startswith("허브-") or str(table.get("category", "")).startswith("공개"))


def source_line(lt: LoadedTable) -> str:
    t = lt.table or {}
    tid = t.get("id", "")
    if lt.synthetic:
        return (f"자료: 가상 데이터(제주빅데이터센터 명세서 {tid} 형식, 시연용 · 실제 수치 아님), "
                f"{period_of(lt)}")
    if tid.startswith("공개-"):
        return f"자료: {t.get('source_name') or t.get('provider', '')}({period_of(lt)}), 이용자 가공"
    if is_public(t) and t.get("source_name"):
        return f"자료: 제주데이터허브, {t['source_name']}({period_of(lt)}), 이용자 가공"
    if is_public(t):
        num = tid.replace("허브-", "")
        return f"자료: 제주데이터허브, {t.get('name', '')}({num}번, {period_of(lt)}), 이용자 가공"
    return f"자료: 제주빅데이터센터, {t.get('name', '')}({tid}, {period_of(lt)}), 이용자 가공"


def exportable(o: StepOutcome) -> pd.DataFrame:
    """반출용 표: 응용집계 열만 남긴다. 추세는 평균=100 지수로 바꾼다."""
    t = o.result.table.copy()
    if o.step.tool == "trend":
        m = o.step.params["measure"]
        avg = t[m].mean()
        t["지수(평균=100)"] = (t[m] / avg * 100).round(1) if avg else None
        t = t.drop(columns=[m])
        return t
    keep = [c for c in t.columns if any(k in c for k in APPLIED_COLS)]
    first = t.columns[0] if t.columns[0] not in keep else None
    if o.step.tool == "top_n":
        first = t.columns[1]
    cols = ([first] if first else []) + keep
    return t[list(dict.fromkeys(cols))]


@dataclass
class ReportBundle:
    folder: Path
    docx: Path
    html: Path
    charts: list[Path]
    request_txt: Path
    zip: Path
    sections: list[dict] = field(default_factory=list)
    answer: object = None


LIMITS_COMMON = [
    "카드 데이터는 비씨카드 한 회사 결제 기준입니다. 현금·다른 카드사 결제는 포함되지 않아 실제 매출 전체가 아닙니다.",
    "비중·순위·지수는 데이터 기간 안의 상대 비교입니다. 개별 가게의 매출을 뜻하지 않습니다.",
    "반출 정책에 따라 합계 대신 비중·지수로 표시했고, 10 미만 값은 표시하지 않습니다.",
]


def synthetic_note(secs: list[dict]) -> str:
    """가상 데이터가 섞였을 때 보고서 첫머리에 넣을 문장. 실제 데이터 결과까지 '가상'으로 보이지 않게 구분한다."""
    done = [s for s in secs if not s["missing"]]
    syn = [s for s in done if s.get("synthetic")]
    if not syn:
        return ""
    if len(syn) == len(done):
        return "※ 이 보고서는 가상 데이터로 만든 예시입니다. 수치에 의미가 없습니다."
    names = {"허브-597": "제주데이터허브 597", "공개-상가": "상가정보 가게 수", "공개-방문자": "관광공사 방문자 수",
             "허브-지구": "제주데이터허브 지구 카드"}
    real = sorted({names.get(s["table_id"], s["table_id"]) for s in done if not s.get("synthetic")})
    return ("※ 제목에 [가상]이 붙은 결과는 시연용 가상 데이터라 수치에 의미가 없습니다. "
            f"나머지({', '.join(real)})는 실제 데이터 결과입니다.")


def section_title(s: dict) -> str:
    return ("[가상] " if s.get("synthetic") else "") + s["title"]


def _focus_label_for(outs: list[StepOutcome], card) -> str:
    if card.key != "public":
        return outs[card.step_index].step.params.get("focus_label", "")
    for o in outs:
        if o.step.table_id.startswith("허브-") and o.step.tool == "compare_share":
            return o.step.params.get("focus_label", "")
    return ""


def build_sections(plan: Plan, outs: list[StepOutcome], loaded: dict[str, LoadedTable], folder: Path,
                   answer=None, export_charts: bool = True) -> list[dict]:
    """결론 카드(insight.Card) 순서대로 섹션을 만든다. 각 섹션: 결론 제목·해석·그래서·반출용 표·차트(PNG)."""
    from .charts import LEGEND, render
    from .insight import _hours_label, build_answer
    answer = answer or build_answer(plan, outs, loaded)
    hl = _hours_label()
    secs = []
    cards = list(answer.cards) + ([answer.public_card] if answer.public_card else [])
    for n, c in enumerate(cards, 1):
        o = outs[c.step_index]
        lt = loaded[o.step.table_id]
        src = source_line(lt)
        sub = " · ".join(x for x in [plan.focus_label, period_of(lt),
                                     f"{lt.table.get('provider') or '공개'} 공개 데이터(실제 값)" if c.public
                                     else "비씨카드 결제금액 기준"] if x)
        if LEGEND.get(c.key):
            sub += "\n" + LEGEND[c.key]
        png = render(c, o, folder / "charts" / f"{n:02d}_{c.key}.png", focus=plan.slots.regions,
                     focus_label=_focus_label_for(outs, c), hours_label=hl,
                     title=c.title if export_charts else None, subtitle=sub if export_charts else "",
                     source=src if export_charts else "", dpi=200 if export_charts else 150)
        secs.append({"key": c.key, "title": c.title, "eyebrow": c.eyebrow, "missing": False,
                     "narrative": [c.explain], "sowhat": c.sowhat, "grade": c.grade, "extra": c.extra,
                     "table": korean_table(exportable(o), lt.table), "chart": png, "synthetic": c.synthetic,
                     "public": c.public, "tool": o.step.tool, "params": o.step.params, "facts": o.result.facts,
                     "checks": o.result.checks, "source": src, "badge": c.eyebrow,
                     "center_only": "센터에서만" in c.eyebrow, "verdict": o.export_verdict,
                     "table_id": o.step.table_id, "period": period_of(lt), "table_name": lt.table["name"],
                     "report": c.report, "vals": dict(c.vals), "hold": c.hold})
    for o in outs:
        if o.result is None:
            secs.append({"title": o.step.why, "missing": True, "table_id": o.step.table_id, "tool": o.step.tool,
                         "params": o.step.params, "badge": o.badge.reason if o.badge else "", "key": "missing"})
    return secs


def _docx(path: Path, title: str, plan: Plan, secs: list[dict], answer, use_purpose: str) -> Path:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor

    from .insight import VERDICT_RULES

    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "맑은 고딕"
    st.font.size = Pt(10.5)
    gray = RGBColor(0x47, 0x55, 0x69)

    def small(text, size=8.5):
        r = doc.add_paragraph().add_run(text)
        r.font.size, r.font.color.rgb = Pt(size), gray

    doc.add_heading(title, level=1)
    small(answer.question_line, 9.5)
    if use_purpose:
        small(f"활용 사유: {use_purpose}", 9.5)
    note = synthetic_note(secs)
    if note:
        doc.add_paragraph(note)

    doc.add_heading("한눈에 보기", level=2)
    r = doc.add_paragraph().add_run(answer.headline)
    r.bold, r.font.size = True, Pt(13.5)
    if answer.core:
        doc.add_paragraph(answer.core)
    if answer.kpis:
        tbl = doc.add_table(rows=1, cols=3)
        tbl.style = "Light Grid Accent 1"
        for j, h in enumerate(["핵심 수치", "값", "비교"]):
            tbl.rows[0].cells[j].text = h
        for k in answer.kpis:
            c = tbl.add_row().cells
            c[0].text, c[1].text, c[2].text = k.label, k.value, k.delta
    if answer.actions:
        doc.add_paragraph().add_run("그래서 할 일").bold = True
        for a in answer.actions:
            doc.add_paragraph(a, style="List Number")
    if answer.report_sentences:
        doc.add_paragraph().add_run("보고서에 쓸 문장").bold = True
        for a in answer.report_sentences:
            doc.add_paragraph(a, style="List Bullet")
        small("인용 표기: " + answer.citation, 9)
    small("믿을 수 있는 이유: " + " · ".join(answer.trust), 9)

    doc.add_heading("근거", level=2)
    for s in [x for x in secs if not x["missing"]]:
        doc.add_heading(section_title(s), level=3)
        small(s["eyebrow"], 9)
        for line in s["narrative"]:
            doc.add_paragraph(line)
        doc.add_picture(str(s["chart"]), width=Inches(6.2))
        p = doc.add_paragraph()
        p.add_run("그래서 ").bold = True
        p.add_run(s["sowhat"])
        for e in s.get("extra", []):
            doc.add_paragraph(e, style="List Bullet")
        small(s["source"])
    missing = [x for x in secs if x["missing"]]
    if missing:
        doc.add_heading("데이터가 없어 빠진 분석", level=2)
        for m in missing:
            doc.add_paragraph(f"{m['title']} — 필요한 표: {m['table_id']}", style="List Bullet")
    doc.add_heading("주의할 점", level=2)
    for line in list(dict.fromkeys(answer.caveats + LIMITS_COMMON)):
        doc.add_paragraph(line, style="List Bullet")
    doc.add_heading("다음 방문 때 이어서 하려면", level=2)
    s_ = plan.slots
    doc.add_paragraph(f"질문: {s_.question} / 동네: {', '.join(s_.regions or s_.city) or '전체'} / 업종: "
                      f"{', '.join(s_.business) or '전체'} / 사용한 센터 표: "
                      f"{', '.join(dict.fromkeys(x['table_id'] for x in secs if not x.get('public')))}. "
                      "같은 질문을 입력하고 같은 표를 받으면 같은 결과가 나옵니다(판정 규칙 고정).")
    doc.add_heading("부록 1. 판정 기준(공개 규칙)", level=2)
    tbl = doc.add_table(rows=1, cols=3)
    tbl.style = "Light Grid Accent 1"
    for j, h in enumerate(["항목", "기준", "근거"]):
        tbl.rows[0].cells[j].text = h
    for name, rule, why in VERDICT_RULES:
        c = tbl.add_row().cells
        c[0].text, c[1].text, c[2].text = name, rule, why
    doc.add_heading("부록 2. 자동 확인과 숫자 표", level=2)
    for s in [x for x in secs if not x["missing"]]:
        for c in s.get("checks", []):
            doc.add_paragraph(c, style="List Bullet")
    for s in [x for x in secs if not x["missing"]]:
        doc.add_paragraph().add_run(section_title(s)).bold = True
        t = s["table"]
        tbl = doc.add_table(rows=1, cols=len(t.columns))
        tbl.style = "Light Grid Accent 1"
        for j, c in enumerate(t.columns):
            tbl.rows[0].cells[j].text = str(c)
        for _, row in t.head(15).iterrows():
            cells = tbl.add_row().cells
            for j, v in enumerate(row):
                cells[j].text = "" if pd.isna(v) else str(v)
    doc.save(path)
    return path


def _html(path: Path, title: str, plan: Plan, secs: list[dict], answer) -> Path:
    e = html.escape
    css = ("body{font-family:'Malgun Gothic','NanumGothic',sans-serif;max-width:880px;margin:24px auto;padding:0 16px;"
           "line-height:1.65;color:#0F172A;font-size:16px}.ans{background:#EFF6FF;border:1px solid #BFDBFE;"
           "border-radius:14px;padding:18px 22px}.v{font-size:22px;font-weight:800}.muted{color:#475569;font-size:14px}"
           ".kpi{display:inline-block;border:1px solid #E2E8F0;border-radius:10px;padding:8px 12px;margin:4px;"
           "background:#fff}.kpi b{font-size:22px}.card{border:1px solid #E2E8F0;border-radius:14px;padding:16px 20px;"
           "margin:16px 0}.so{background:#F8FAFC;border-left:4px solid #EA580C;padding:8px 12px;border-radius:6px}"
           ".warn{background:#FEF3C7;padding:8px 12px;border-radius:8px}table{border-collapse:collapse;font-size:13px}"
           "td,th{border:1px solid #E2E8F0;padding:4px 8px}")
    parts = [f"<!doctype html><html lang='ko'><meta charset='utf-8'><title>{e(title)}</title><style>{css}</style>",
             f"<h1>{e(title)}</h1><p class='muted'>{e(answer.question_line)}</p>"]
    note = synthetic_note(secs)
    if note:
        parts.append(f"<p class='warn'>{e(note)}</p>")
    parts.append(f"<div class='ans'><div class='v'>{e(answer.headline)}</div><p>{e(answer.core)}</p>")
    parts += [f"<span class='kpi'>{e(k.label)}<br><b>{e(k.value)}</b> <span class='muted'>{e(k.delta)}</span></span>"
              for k in answer.kpis]
    if answer.actions:
        parts.append("<ol>" + "".join(f"<li>{e(a)}</li>" for a in answer.actions) + "</ol>")
    if answer.report_sentences:
        parts.append("<ul>" + "".join(f"<li>{e(a)}</li>" for a in answer.report_sentences) + "</ul>")
    parts.append(f"<p class='muted'>{e(' · '.join(answer.trust))}</p></div>")
    for s in [x for x in secs if not x["missing"]]:
        parts.append(f"<div class='card'><div class='muted'>{e(s['eyebrow'])}</div><h3>{e(section_title(s))}</h3>")
        parts += [f"<p>{e(x)}</p>" for x in s["narrative"]]
        parts.append(f"<img src='charts/{s['chart'].name}' style='max-width:100%'>")
        parts.append(f"<p class='so'><b>그래서</b> {e(s['sowhat'])}</p>")
        parts += [f"<p class='muted'>{e(x)}</p>" for x in s.get("extra", [])]
        parts.append(f"<p class='muted'>{e(s['source'])}</p></div>")
    parts.append("<h2>주의할 점</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in dict.fromkeys(answer.caveats + LIMITS_COMMON))
                 + "</ul>")
    path.write_text("".join(parts), encoding="utf-8")
    return path


def build_report(plan: Plan, outs: list[StepOutcome], loaded: dict[str, LoadedTable], out_dir: Path,
                 purpose: str = "", synthetic: bool = False, title: str | None = None,
                 extra_docx=None, answer=None, use_purpose: str = "") -> ReportBundle:
    """분석 보고서(DOCX·HTML) + 반출용 그림(PNG) + 반출 신청서 초안 + 묶음(zip)."""
    import dataclasses

    from .insight import build_answer
    folder = Path(out_dir)
    folder.mkdir(parents=True, exist_ok=True)
    if synthetic:   # 예전 호출 방식: 센터 표 전체가 가상 데이터
        loaded = {k: (v if is_public(v.table) or v.synthetic else dataclasses.replace(v, synthetic=True))
                  for k, v in loaded.items()}
    answer = answer or build_answer(plan, outs, loaded)
    title = title or "데이터 분석 결과"
    secs = build_sections(plan, outs, loaded, folder, answer)
    docx_path = _docx(folder / "분석보고서.docx", title, plan, secs, answer, use_purpose or purpose)
    if extra_docx:
        extra_docx(docx_path, secs)
    html_path = _html(folder / "분석보고서.html", title, plan, secs, answer)
    reason = use_purpose or purpose or "사업계획 수립을 위한 시장 분석"
    items = []
    for s in secs:
        if s["missing"] or s.get("public"):   # 공개 데이터는 반출 신청 대상이 아니다
            continue
        items.append({"file": s["chart"].name, "tables": [{"id": s["table_id"], "name": s["table_name"]}],
                      "period": s["period"], "purpose": reason})
    if items:
        all_tables = []
        for s in secs:
            if not s["missing"] and not s.get("public") and s["table_id"] not in {t["id"] for t in all_tables}:
                all_tables.append({"id": s["table_id"], "name": s["table_name"]})
        items.insert(0, {"file": docx_path.name, "tables": all_tables, "period": items[0]["period"], "purpose": reason})
    req = folder / "반출신청서_초안.txt"
    req.write_text("[제주빅데이터센터 반출 신청 초안]\n작성일: " + date.today().isoformat() + "\n\n"
                   + "\n".join(export_request_lines(items)) + "\n\n"
                   + "※ 반출 대상은 그림(PNG)과 보고서(DOCX)이며 원본 데이터·발췌는 포함하지 않습니다.\n"
                   + "※ 표의 수치는 비중·순위·지수(응용집계)이며 10 미만 값은 표시하지 않았습니다.\n"
                   + ("※ 보고서에는 공개 데이터(제주데이터허브) 분석도 함께 들어 있습니다(반출 심사 대상 아님).\n"
                      if any(s.get("public") and not s["missing"] for s in secs) else ""),
                   encoding="utf-8")
    charts = [s["chart"] for s in secs if not s["missing"]]
    zpath = folder / "반출패키지.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(docx_path, docx_path.name)
        z.write(req, req.name)
        for c in charts:
            z.write(c, f"charts/{c.name}")
    return ReportBundle(folder, docx_path, html_path, charts, req, zpath, secs, answer)
