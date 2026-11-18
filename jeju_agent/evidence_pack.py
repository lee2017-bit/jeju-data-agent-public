"""지원사업 근거팩: 분석 결과를 사업계획서 양식 항목에 맞춰 붙여 넣을 수 있게 정리한다.

양식 기준: 예비창업패키지 등 창업 지원사업에서 널리 쓰는 PSST 구조
  1. 문제인식(Problem) — 시장 현황·문제점
  2. 실현가능성(Solution) — 운영 계획의 근거
  3. 성장전략(Scale-up) — 목표 고객·확장 방향
  4. 팀 구성(Team) — 데이터로 채울 수 없으므로 작성 안내만
+ 부록: 지금 신청할 수 있는 지원사업(신청 방법·마감), 출처 표기, 한계

문장은 데이터가 보여 주는 범위 안에서만 '~할 수 있습니다' 수준으로 쓴다(과장 금지).
"""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

from .korean import josa
from .programs import Program
from .report import LIMITS_COMMON, ReportBundle, section_title, synthetic_note

PSST = [  # 사업계획서 항목 ← 결론 카드
    ("1. 문제인식 (시장 현황 및 문제점)", ("regions", "customers", "location", "stores", "public")),
    ("2. 실현가능성 (운영 계획의 근거)", ("season", "week", "time", "visitors", "district")),
]
GROWTH = "3. 성장전략 (목표 고객과 확장 방향)"
PLAN_ACTION = {   # 사업계획서 문장 예시의 뒷문장(문어체, 데이터 범위 안에서 과장 없이)
    "regions": "후보 동네의 손님 구성과 시장 크기를 나란히 비교해 입지와 주 고객층을 정했다.",
    "location": "수요 규모를 근거로 입지를 정했으며, 경쟁 가게 수는 별도 자료로 확인한다.",
    "season": "월별 매출 차이를 반영해 인력·재고·자금 계획을 세운다.",
    "week": "요일별 매출 비중에 맞춰 영업일과 인력을 배치한다.",
    "time": "시간대별 매출에 맞춰 영업시간과 근무 시간을 정한다.",
    "public": "공개 데이터와 센터 데이터를 함께 인용해 근거를 보강한다.",
    "stores": "가까운 경쟁 가게와 다르게 보일 점(메뉴·좌석·영업시간)을 정해 차별화한다.",
    "visitors": "최근 방문객 흐름을 함께 보아 계절별 운영 계획을 세운다.",
    "district": "같은 유형 지구의 요일·시간대 흐름을 참고해 영업시간과 인력 배치를 정한다.",
}


def _customer_action(T: float | None) -> str:
    if T is None:
        return "주 고객층과 비수기 보완 고객층을 나눠 공략한다."
    if T >= 55:
        return "이에 따라 관광객을 주 고객으로 하되, 비수기를 받쳐 줄 도민 단골 고객층을 함께 공략한다."
    if T < 45:
        return "이에 따라 도민 단골을 주 고객으로 하고, 성수기에는 관광객 대상 메뉴·홍보를 더한다."
    return "관광객과 도민 매출이 비슷하므로 두 고객층을 함께 겨냥하고, 계절에 따라 홍보 대상을 바꾼다."


def plan_sentence(sec: dict) -> str:
    """사업계획서에 옮겨 쓸 문장: 카드의 문어체 문장(report) + 계획 문장. report가 없으면 제목을 문어체로 바꿔 쓴다."""
    key = sec.get("key")
    base = sec.get("report") or ""
    if not base:
        t = sec.get("title", "").replace("공개 데이터(실제 값): ", "")
        base = t.replace("입니다", "이다") if t.count("니다") == t.count("입니다") else ""
    if key == "customers":
        return f"{base} {_customer_action((sec.get('vals') or {}).get('T'))}".strip()
    if key == "public" and not base:
        return "누구나 확인할 수 있는 공개 데이터(제주데이터허브 597)에서도 같은 경향이 확인된다. " + PLAN_ACTION["public"]
    return f"{base} {PLAN_ACTION.get(key, '')}".strip() if base else ""


def growth_lines(secs: list[dict]) -> list[str]:
    """성장전략: 결론 카드의 수치로 목표 고객·운영 집중·확장 방향을 문어체로(데이터가 있는 것만, '검토한다' 수준)."""
    by = {s.get("key"): s for s in secs if not s.get("hold")}
    v = {k: (s.get("vals") or {}) for k, s in by.items()}
    out = []
    T = v.get("customers", {}).get("T")
    if T is not None:
        if T >= 55:
            out.append(f"1차 목표 고객은 관광객이다(같은 업종 매출의 {T}%). 관광객이 줄어드는 비수기에는 도민 단골 상품"
                       "(평일 할인, 동네 정기권 등)으로 매출을 보완한다.")
        elif T < 45:
            out.append(f"1차 목표 고객은 도민 단골이다(관광객 매출 {T}%). 재방문 혜택으로 단골을 늘리고, 성수기에는 "
                       "관광객 대상 메뉴·홍보를 더한다.")
        else:
            out.append(f"관광객과 도민 매출이 비슷하다(관광객 {T}%). 두 고객층을 함께 겨냥하고 계절에 따라 홍보 대상을 바꾼다.")
    se = v.get("season", {})
    if se.get("R") is not None and se["R"] < 1.5:
        out.append(f"가장 잘 되는 달이 가장 한산한 달의 {se['R']}배로 계절 차이가 작아, 연중 고른 인력·재고 계획을 세운다.")
    elif se.get("hi") and se.get("lo"):
        out.append(f"성수기({se['hi']}, 평소=100일 때 {se.get('idx_hi')})에 앞서 인력·재고를 늘리고, 비수기"
                   f"({se['lo']}, {se.get('idx_lo')})에는 운영비를 줄여 연간 현금 흐름을 맞춘다.")
    wk, tm = v.get("week", {}), v.get("time", {})
    has_w, has_t = bool(wk.get("three") and wk.get("s3") is not None), bool(tm.get("busy"))
    when = ""
    if has_w and has_t:
        when = f"매출이 요일로는 {wk['three']}({wk['s3']}%)에, 하루 중에는 1시간당 기준으로 {tm['busy']}에 가장 몰리므로"
    elif has_w:
        when = f"매출의 {wk['s3']}%가 {wk['three']}에 몰리므로"
    elif has_t:
        when = f"하루 중 {tm['busy']}에 1시간당 매출이 가장 많으므로"
    if when:
        tail = f" 가장 한산한 {wk['lo']}{josa(wk['lo'], '은/는')} 휴무·정비일 후보로 둔다." if wk.get("lo") else ""
        out.append(when + ", 이때 인력과 대표 메뉴를 집중한다." + tail)
    sv = v.get("stores", {})
    if sv.get("cnt") and sv.get("E") is not None:
        how = ("가게 하나당 매출이 제주 평균보다 작아" if sv["E"] < 0.8 else "가게 하나당 매출이 제주 평균보다 커"
               if sv["E"] >= 1.2 else "가게 하나당 매출이 제주 평균 수준이라")
        out.append(f"같은 동네 같은 업종 가게가 {sv['cnt']}곳이고 {how}, 가까운 가게와 다르게 보일 점(메뉴·좌석·영업시간)을 "
                   "개업 전에 정한다.")
    elif sv.get("cnt"):
        out.append(f"같은 동네 같은 업종 가게가 {sv['cnt']}곳" + (f"({sv['rk']})" if sv.get("rk") else f"(제주 {sv.get('r')}위)")
                   + "이므로, 가까운 가게와 다르게 보일 점을 "
                   "개업 전에 정한다.")
    lo = v.get("location", {})
    if lo.get("name") and lo.get("r"):
        out.append(f"{lo['name']}{josa(lo['name'], '은/는')} 같은 업종 매출이 제주 {lo.get('N')}개 동네 가운데 {lo['r']}위인 "
                   "시장이다. 자리를 잡은 뒤에는 매출 상위 동네를 2호점·팝업 판매 후보로 검토하되, 동네별 가게 수(경쟁)를 "
                   "먼저 확인한다.")
    return out


def implications(sec: dict) -> list[str]:
    """섹션의 '그래서' 문장(보수적 표현)."""
    return [sec["sowhat"]] if sec.get("sowhat") else []


def build_evidence_pack(bundle: ReportBundle, question: str, programs: list[Program] | None = None,
                        purpose: str = "", synthetic: bool = False) -> Path:
    from docx import Document
    from docx.shared import Inches, Pt

    secs = [s for s in bundle.sections if not s["missing"]]
    from .insight import FOOD_WORDS, unfood
    seen = question + " " + " ".join(str(x.get("title", "")) for x in secs)
    tx = (lambda x: x) if any(w in seen for w in FOOD_WORDS) else unfood     # 숙박·소매 등은 '메뉴' 대신 '상품'
    doc = Document()
    doc.styles["Normal"].font.name = "맑은 고딕"
    doc.styles["Normal"].font.size = Pt(10.5)
    doc.add_heading("지원사업 근거팩", level=1)
    doc.add_paragraph(f"사업 아이디어·질문: {question}")
    if purpose:
        doc.add_paragraph(f"활용 목적: {purpose}")
    if synthetic:                    # 센터 표 자리만 가상. 공개 데이터(597·상가정보)는 실제 값 그대로
        for sec in secs:
            if not sec.get("public"):
                sec["synthetic"] = True
    org = [n for n, hit in (("제주빅데이터센터", any(not x.get("public") and not x.get("synthetic") for x in secs)),
                            ("제주데이터허브", any(x.get("table_id", "").startswith("허브-") for x in secs)),
                            ("소상공인 상가정보", any(x.get("table_id", "") == "공개-상가" for x in secs)),
                            ("한국관광공사", any(x.get("table_id", "") == "공개-방문자" for x in secs)),
                            ("가상 데이터(시연용)", any(x.get("synthetic") for x in secs))) if hit]
    doc.add_paragraph(f"작성일: {date.today().isoformat()} · 자료: {', '.join(org) or '-'}(이용자 가공)")
    if any(x.get("synthetic") for x in secs):
        doc.add_paragraph(synthetic_note(secs) + " 실제 신청서에는 센터 데이터로 다시 만든 결과를 쓰세요.")
    ans = bundle.answer
    if ans is not None:
        doc.add_heading("한 줄 요약", level=2)
        doc.add_paragraph(ans.headline).runs[0].bold = True
        if ans.core:
            doc.add_paragraph(ans.core)
    doc.add_paragraph("아래 문단과 그림은 사업계획서 해당 항목에 그대로 붙여 넣을 수 있게 정리했습니다. "
                      "그림 아래 출처 표기를 함께 옮겨 주세요.")

    synth = any(x.get("synthetic") for x in secs)
    for heading, keys in PSST:
        doc.add_heading(heading, level=2)
        picked = [s for s in secs if s.get("key") in keys]
        if not picked:
            doc.add_paragraph("이 항목에 쓸 분석 결과가 없습니다. 질문에 요일·시간대·고객층을 넣어 다시 분석해 보세요.")
            continue
        for s in picked:
            doc.add_paragraph(section_title(s)).runs[0].bold = True
            for line in s.get("narrative", []):
                doc.add_paragraph(line)
            doc.add_paragraph("→ " + tx(s["sowhat"]))
            sent = tx(plan_sentence(s))
            if sent:
                p = doc.add_paragraph()
                p.add_run("사업계획서 문장 예시" + ("(가상 수치)" if s.get("synthetic") else "") + ": ").bold = True
                p.add_run(sent)
            doc.add_picture(str(s["chart"]), width=Inches(5.8))
            doc.add_paragraph(s["source"]).runs[0].font.size = Pt(8)
    doc.add_heading(GROWTH, level=2)
    lines = [tx(x) for x in growth_lines(secs)]
    if lines:
        doc.add_paragraph(tx("위 분석에서 바로 나오는 방향입니다. 사업계획서 문장으로 옮겨 쓰고, 메뉴·가격 같은 내 계획을 덧붙이세요.")
                          + (" (가상 수치)" if synth else ""))
        for line in lines:
            doc.add_paragraph(line, style="List Bullet")
    else:
        doc.add_paragraph("이 항목에 쓸 분석 결과가 없습니다. 질문에 고객층·계절을 넣어 다시 분석해 보세요.")
    doc.add_heading("4. 팀 구성", level=2)
    doc.add_paragraph("데이터로 채울 수 없는 항목입니다. 대표자·팀원의 관련 경험과 역할을 직접 적어 주세요.")

    doc.add_heading("부록 1. 지금 신청할 수 있는 지원사업", level=2)
    if programs:
        tbl = doc.add_table(rows=1, cols=5)
        tbl.style = "Light Grid Accent 1"
        for j, h in enumerate(["공고명", "기관", "마감", "신청 방법", "바로가기"]):
            tbl.rows[0].cells[j].text = h
        for pg in programs[:10]:
            c = tbl.add_row().cells
            c[0].text = pg.title
            c[1].text = pg.org
            c[2].text = pg.end
            c[3].text = ", ".join(pg.apply_methods) + (" (방문 접수)" if pg.visit_required else "")
            c[4].text = pg.url
        doc.add_paragraph("출처: 창업진흥원 K-Startup, 중소벤처기업부 기업마당(공공누리 제3유형: 출처표시·변경금지). 신청 방법은 공고 문장에서 자동 분류한 것이므로 세부 자격과 함께 공고문을 꼭 확인하세요.")
    else:
        doc.add_paragraph("조건에 맞는 모집 중 공고를 찾지 못했거나 공고 목록을 불러오지 못했습니다.")

    doc.add_heading("부록 2. 출처 표기와 한계", level=2)
    for s in secs:
        doc.add_paragraph(s["source"], style="List Bullet")
    for line in LIMITS_COMMON:
        doc.add_paragraph(line, style="List Bullet")
    path = bundle.folder / "지원사업_근거팩.docx"
    doc.save(path)
    # 반출 패키지와 신청서 초안에도 근거팩을 더한다(응용집계·그림만 포함된 보고서)
    with zipfile.ZipFile(bundle.zip, "a", zipfile.ZIP_DEFLATED) as z:
        if path.name not in z.namelist():
            z.write(path, path.name)
    req = bundle.request_txt.read_text(encoding="utf-8")
    if path.name not in req:
        tables = ", ".join(dict.fromkeys(f"{s['table_name']}({s['table_id']})" for s in secs if not s.get("public")))
        req += (f"\n추가. 파일: {path.name}\n   출처(원본데이터 명칭): 제주빅데이터센터, {tables}\n"
                f"   활용 사유: {purpose or '지원사업 신청서 작성'}\n")
        bundle.request_txt.write_text(req, encoding="utf-8")
    return path
