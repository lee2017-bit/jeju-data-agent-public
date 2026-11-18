"""방문 전 준비표: 집(또는 센터 상담 전화)에서 질문을 정리하고, 센터에 와서 한 번에 끝내도록.

- 인쇄용 준비표(HTML): 질문 해석, 센터에서 받을 데이터(표·조건·기간·센터 전용 이유),
  온라인으로 먼저 볼 수 있는 것, 지금 신청할 수 있는 지원사업(마감·방문 접수), 준비물
- 준비 파일(CSV): 센터 PC 반입은 CSV만 허용되므로 질문·목적·조건을 CSV로 저장해 두고,
  센터에서 넣으면 같은 질문과 분석 계획이 그대로 복원된다.
"""

from __future__ import annotations

import csv
import html
import io
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .alternatives import badge_for
from .planner import Plan, make_plan, parse
from .programs import Profile, Program

PREP_KEYS = ["question", "purpose", "stage", "age", "keywords"]
CENTER_INFO = ("제주빅데이터센터: 제주시 첨단로, 제주테크노파크 건물 3층. "
               "이용 신청은 제주데이터허브(jejudatahub.net)에서 먼저 해 주세요(정확한 주소·운영시간도 같은 곳에서 확인).")


@dataclass
class PrepSheet:
    question: str
    purpose: str
    profile: Profile
    plan: Plan
    programs: list[Program] = field(default_factory=list)


def make_prep(question: str, purpose: str, profile: Profile, cat: dict, programs: list[Program] | None = None) -> PrepSheet:
    plan = make_plan(parse(question, cat, purpose), cat)
    return PrepSheet(question, purpose, profile, plan, programs or [])


def to_csv_bytes(p: PrepSheet) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["항목", "값"])
    w.writerow(["question", p.question])
    w.writerow(["purpose", p.purpose])
    w.writerow(["stage", p.profile.stage])
    w.writerow(["age", "" if p.profile.age is None else p.profile.age])
    w.writerow(["keywords", "|".join(p.profile.keywords)])
    w.writerow(["tables", "|".join(r.table_id for r in p.plan.requests)])
    w.writerow(["made", date.today().isoformat()])
    return buf.getvalue().encode("utf-8-sig")


def from_csv(data: bytes | str | Path) -> dict:
    if isinstance(data, Path):
        data = data.read_bytes()
    if isinstance(data, bytes):
        for enc in ("utf-8-sig", "cp949"):
            try:
                data = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    rows = list(csv.reader(io.StringIO(data)))
    if not rows or rows[0][:2] != ["항목", "값"]:
        raise ValueError("방문 준비 파일 형식이 아닙니다.")
    kv = {r[0]: (r[1] if len(r) > 1 else "") for r in rows[1:] if r}
    age = kv.get("age", "")
    return {"question": kv.get("question", ""), "purpose": kv.get("purpose", ""),
            "profile": Profile(stage=kv.get("stage") or "예비창업자", age=int(age) if age.isdigit() else None,
                               keywords=[k for k in kv.get("keywords", "").split("|") if k])}


def is_prep_csv(head: bytes) -> bool:
    try:
        first = head.decode("utf-8-sig", errors="ignore").splitlines()[0]
    except IndexError:
        return False
    return first.replace('"', "").startswith("항목,값")


def to_html(p: PrepSheet) -> str:
    e = html.escape
    s = p.plan.slots
    rows = []
    for r in p.plan.requests:
        steps = [st for st in p.plan.steps if st.table_id == r.table_id]
        why = badge_for(steps[0].tool, steps[0].table_id, steps[0].params).reason if steps else ""
        rows.append(f"<tr><td>{e(r.table_id)}</td><td>{e(r.table_name)}</td><td>{e('; '.join(r.conditions))}</td>"
                    f"<td>{e(why.replace('센터에서만 나오는 수치: ', ''))}</td></tr>")
    progs = "".join(
        f"<tr><td>{e(pg.title)}</td><td>{e(pg.org)}</td><td>{e(pg.end)}</td>"
        f"<td>{e(', '.join(pg.apply_methods))}{' <b>(방문 접수)</b>' if pg.visit_required else ''}</td></tr>"
        for pg in p.programs[:8]) or "<tr><td colspan=4>조건에 맞는 모집 중 공고를 찾지 못했습니다.</td></tr>"
    scope = "".join(f"<p class='muted'>⚠ {e(a)}</p>" for a in p.plan.scope_notes)
    found = []
    if s.regions:
        found.append("지역: " + ", ".join(s.regions))
    if s.business:
        found.append("업종: " + ", ".join(s.business))
    if s.segment:
        found.append("대상: " + s.segment[2])
    return f"""<!doctype html><html lang='ko'><meta charset='utf-8'><title>방문 준비표</title>
<style>body{{font-family:'Malgun Gothic','NanumGothic',sans-serif;max-width:820px;margin:24px auto;padding:0 16px;line-height:1.6}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #d1d5db;padding:6px;vertical-align:top}}
th{{background:#f3f4f6}}h1{{margin-bottom:4px}}.muted{{color:#6b7280;font-size:13px}}
.box{{border:1px solid #d1d5db;border-radius:8px;padding:10px 14px;margin:12px 0}}@media print{{.noprint{{display:none}}}}</style>
<h1>제주빅데이터센터 방문 준비표</h1><p class='muted'>작성일 {date.today().isoformat()}</p>
<div class='box'><b>내 질문</b>: {e(p.question)}<br><b>활용 목적</b>: {e(p.purpose or '-')}<br>
<b>Agent가 이해한 내용</b>: {e(' / '.join(found) or '지역·업종을 더 구체적으로 적으면 좋습니다')}</div>
<h2>1. 센터에서 볼 데이터</h2><table><tr><th>표</th><th>데이터</th><th>조건</th><th>센터에서만 나오는 이유</th></tr>{''.join(rows)}</table>{scope}
<h2>2. 지금 신청할 수 있는 지원사업</h2><table><tr><th>공고</th><th>기관</th><th>마감</th><th>신청 방법</th></tr>{progs}</table>
<p class='muted'>출처: 창업진흥원 K-Startup, 중소벤처기업부 기업마당(공공누리 제3유형: 출처표시·변경금지). 자격 조건과 신청 방법은 공고문을 꼭 확인하세요.</p>
<h2>3. 준비물</h2><ul>
<li>제주데이터허브에서 빅데이터센터 <b>이용 신청</b>(방문 날짜 예약)</li>
<li>이 준비표와 <b>방문 준비 파일(CSV)</b> — 센터 PC에 넣으면 같은 질문이 바로 이어집니다(센터 반입은 CSV만 가능)</li>
<li>(선택) 내 가게 월별 매출 합계 CSV — 센터 데이터와 함께 비교할 수 있습니다. 반출 승인된 자료 외에는 퇴실 후 삭제됩니다.</li>
<li>지원사업 신청서 양식(있으면) — 근거팩을 항목에 맞춰 붙여 넣습니다.</li></ul>
<div class='box'>{e(CENTER_INFO)}</div>
<p class='muted'>예상 소요: 데이터 받기 10분 + 분석·보고서 20분 + 반출 신청 10분 ≈ 1시간 이내(데이터 크기에 따라 다름)</p>
</html>"""
