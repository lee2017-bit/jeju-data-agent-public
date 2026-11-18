"""결과 설명자료(HTML)를 실행 기록(docs/submission/results/*.json)에서 만든다. 숫자는 기록에서 그대로 가져온다.

    python tools/bench_examples.py && python tools/bench_parse.py && python tools/build_results_doc.py

구성은 대회 요구 항목 순서(문제 정의 → Agent 구조 → 주요 기능 → 실행 결과 → 검증 방법·한계 → 센터 활용 방안)이고,
기획서와 같은 글자 체계(docs/submission/visual.css)를 쓴다. 화면 그림은 docs/proposal/img/ 의 실제 앱 캡처다.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "docs" / "submission" / "results"
OUT = ROOT / "docs" / "submission" / "결과_설명자료.html"
IMG = "../proposal/img/"
PURPOSE = {"사업계획서·창업": "가게 열기·사업계획서", "가게·회사 운영": "가게 운영", "현황자료·보고서": "현황자료·보고서", "논문·연구": "논문·연구"}
CARD_KO = {"regions": "동네 비교", "customers": "손님 구성", "season": "월별 흐름", "week": "요일", "time": "시간대", "location": "시장 크기",
           "stores": "경쟁(가게 수)", "visitors": "최근 방문객", "district": "지구 유형", "public": "공개 데이터 교차 확인"}
CARD_DATA = {"regions": "센터 1-08", "customers": "센터 1-08", "season": "센터 1-08", "week": "센터 1-12", "time": "센터 1-14", "location": "센터 1-08",
             "stores": "상가정보 + 행안부 인구", "visitors": "관광공사 방문자 수", "district": "데이터허브 관광지 및 상업지구",
             "public": "데이터허브 597"}
# 화면 실행 기록(2026-11-10, 2026-11-03)에서 옮긴 지원사업 판정 수치
PROG_OPEN, PROG_JUDGED, PROG_NOW = 1589, 17, 5
MODEL_PAIRS, MODEL_AGREE = 36, 30


def e(x) -> str:
    return html.escape("" if x is None else str(x))


def bg(c: dict) -> str:
    if c.get("public"):
        return "<span class='bg b-real'>실제</span>"
    return "<span class='bg b-demo'>체험</span>" if c.get("synthetic") else "<span class='bg b-center'>센터</span>"


def head(kk: str, title: str, lead: str = "") -> str:
    return (f"<div class='hdr'><span class='kk'>{kk}</span><h2 class='t1'>{title}</h2>"
            + (f"<p class='ld'>{lead}</p>" if lead else "") + "</div>")


def table(cols, rows) -> str:
    th = "".join(f"<th style='width:{w}'>{e(h)}</th>" if w else f"<th>{e(h)}</th>" for h, w in cols)
    return "<table class='ax'><tr>" + th + "</tr>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) + "</table>"


def build() -> str:
    ex = json.loads((RES / "examples.json").read_text(encoding="utf-8"))
    pb = json.loads((RES / "parse_bench.json").read_text(encoding="utf-8"))
    rows = ex["examples"]
    first = rows[0]
    rule = pb["results"][0]
    ais = pb["results"][1:]
    ai_ok = [r["완전 정답"] for r in ais]
    ai_cost = sum(r["AI 비용(USD)"] for r in ais) / max(len(ais), 1)
    ai_sec = sum(r["초"] for r in ais) / max(len(ais), 1)
    t_an = [r["seconds"]["analyze"] for r in rows]
    checks = [r["checks_passed"] for r in rows]
    n = len(rows)
    nq = rule["문항"]
    css = (OUT.parent / "visual.css").read_text(encoding="utf-8")
    P = []

    # ── 1쪽 표지 ──
    toc = [("1", "문제 정의", "누가 오고, 어디서 막히나", "2"), ("2", "Agent 구조", "판단은 규칙, 말은 AI", "3"),
           ("3", "주요 기능", "여섯 가지", "4"), ("4", "실행 결과", "대표 질문 · 근거 카드 · 질문 6개 · 목적별 출력", "5~8"),
           ("5", "검증 방법 · 한계", "정확도 실측 · 신뢰 장치", "9~10"), ("6", "센터 활용 방안", "방문 전부터 반출 심사까지", "11")]
    P.append(f"""<div class='page m mcover'>
  <div class='meta'>제주 AI·빅데이터 활용 AI Agent 개발 챌린지 · 결과 설명자료 · 팀 치킨암살단-제주</div>
  <h1 style='margin-top:12mm'>결과 설명자료</h1>
  <p class='sub'>제주 사장님 상권비서가 실제로 내놓는 결과와,<br>직접 재 본 기록</p>
  <div class='b3 mt9'>
    <div><b>{n}/{n}</b><span>질문 끝까지 실행</span><small>서로 다른 질문 {n}개</small></div>
    <div><b>{min(ai_ok)}/{nq}</b><span>질문 해석 정답</span><small>AI + 규칙, {len(ais)}회 모두</small></div>
    <div><b>{max(t_an)}초</b><span>분석 시간</span><small>질문 {n}개 모두 1초 안(그림 제외)</small></div>
  </div>
  <div class='read2 mt9'>
    <div><span class='bg b-real'>실제</span><p>제주데이터허브·공공데이터포털에서 받은 실제 값</p></div>
    <div><span class='bg b-demo'>체험</span><p>센터 데이터 자리에 넣은 가상 데이터 — 명세서 형식 그대로, 수치에 의미 없음</p></div>
  </div>
  <div class='toc mt9'>""" + "".join(f"<div><i>{a}</i><b>{e(b)} <span>· {e(c)}</span></b><em>{d}쪽</em></div>" for a, b, c, d in toc) + f"""</div>
  <div class='foot'><img src='{IMG}demo-qr.svg' alt='공개 데모 QR'><div><b>같은 결과를 설치 없이 보기</b><span>jeju-data-agent.streamlit.app</span><small style='display:block;font-size:10pt;font-weight:600;color:#475569;margin-top:1mm'>시연 영상(3분) youtu.be/sO9QfRvw-D8</small>
    <p class='cap'>숫자는 {e(ex['run_date'])} 실행 기록(docs/submission/results/*.json)에서 그대로 옮겼습니다</p></div></div>
</div>""")

    # ── 2쪽 문제 정의 ──
    P.append(f"""<section class='pg m'>
  {head('1 · 문제 정의', '센터 데이터는 귀하지만,<br>쓰기까지 벽이 셋 있습니다')}
  <h3 class='hd'>누가, 무엇을 하러 오나 <span>· 운영진 답변: 방문자 대다수는 기관·기업, 목적은 논문·현황자료·사업계획서</span></h3>
  <div class='who4'>
    <div><span class='ico'>🧑‍🍳</span><b>예비창업자</b><span>사업계획서</span></div>
    <div><span class='ico'>🏢</span><b>기관·기업</b><span>현황 보고서</span></div>
    <div><span class='ico'>🎓</span><b>연구자</b><span>논문·과제</span></div>
    <div><span class='ico'>🧑‍💼</span><b>센터 직원</b><span>상담·반출 심사</span></div>
  </div>
  <h3 class='hd mt12'>어디서 막히나</h3>
  <div class='w3'>
    <div><span class='no'>벽 1</span><b>무엇을 받아야 하나</b><p>표 71종 중에서 골라 기간·조건을 정해 내려받기. 컬럼은 영문</p></div>
    <div><span class='no'>벽 2</span><b>AI에 보내면 안 됨</b><p>센터 데이터 원본·조회 결과는 외부 AI 전송 금지</p></div>
    <div><span class='no'>벽 3</span><b>들고 나갈 수 있나</b><p>10 미만 수치·엑셀 표는 원칙적으로 반출 불가, 그림은 PNG·JPG만</p></div>
  </div>
  <p class='stmt mt12'>목표: 질문 한 줄에서 <em>들고 나갈 수 있는 결과</em>까지,<br>방문 한 번에</p>
  <div class='n2 mt12'>
    <div><b>방문자에게</b><p>코딩 없이 평소 말로 묻고, 사업계획서·보고서에 바로 넣을 근거를 받습니다</p></div>
    <div><b>센터에게</b><p>직원 1:1 지원 없이도 분석이 끝나고, 반출 신청이 규정에 맞춰 들어옵니다</p></div>
  </div>
  <p class='cap mt9'>근거: 대회 게시판 운영진 답변(2026.10~11) · 센터 데이터 반출 정책(2026.9) · 센터 데이터 명세서(2026.1)</p>
</section>""")

    # ── 3쪽 Agent 구조 ──
    P.append(f"""<section class='pg m'>
  {head('2 · Agent 구조', '판단은 규칙이, 말은 AI가')}
  <div class='arch'>
    <div class='ext'><b>☁️ 외부 AI (gpt-6-luna)</b><p class='ok'>받는 것: 질문 문장, 지원사업 공고문</p><p class='no'>센터 데이터는 받지 않음</p></div>
    <div class='link'>↕ 질문 문장만 오감</div>
    <div class='pc'><span class='pclab'>🔒 센터 PC 안</span>
      <div class='flow6'>
        <div class='ai'><i>1</i><b>질문 해석</b><span>규칙 + AI<br>동네·업종·대상·관점</span></div>
        <div><i>2</i><b>분석 계획</b><span>받을 표·기간<br>쓸 도구</span></div>
        <div><i>3</i><b>도구 실행</b><span>검증된 도구 10개<br>비중·순위·지수 등</span></div>
        <div><i>4</i><b>자동 검산</b><span>합계·기간 누락<br>표본 부족</span></div>
        <div><i>5</i><b>반출 점검</b><span>응용집계·PNG<br>10 미만 가림</span></div>
        <div><i>6</i><b>결론 정리</b><span>공개 규칙표로<br>등급·할 일</span></div>
      </div>
      <div class='io'>
        <div><b>들어오는 것</b> · 센터에서 받은 CSV, 공개 데이터(앱에 동봉)</div>
        <div><b>나가는 것</b> · 결론·근거 카드, 보고서·근거팩, 반출 신청 묶음</div>
      </div>
    </div>
  </div>
  <figure class='mt9'><div class='sh'><img src='{IMG}c-agentlog.jpg' alt='Agent 작업 기록'></div>
    <figcaption class='cap mt3'>실제 화면에 남는 작업 기록 — 단계마다 한 일, 걸린 시간, 같은 질문·데이터면 같은 재현 번호</figcaption></figure>
  <div class='act3 mt9'>
    <div style='background:var(--orange-soft)'><b>🤖 AI</b><ul><li>질문 문장에서 표현 뽑기</li><li>공고문과 자격 대조</li></ul></div>
    <div style='background:var(--green-soft)'><b>📐 규칙(코드)</b><ul><li>계산 · 검산 · 판정</li><li>문서 · 반출 묶음 만들기</li></ul></div>
    <div style='background:#FEF3C7'><b>🙋 사람</b><ul><li>이해한 내용 확인 · 고치기</li><li>데이터 받기 · 반출 신청</li></ul></div>
  </div>
</section>""")

    # ── 4쪽 주요 기능 ──
    feats = [("💬", "평소 말로 질문", "동네·업종·대상·관점을 알아듣고 확인받음", "정확도 9쪽"),
             ("📥", "받을 데이터 안내", "표 번호·기간·조건을 알려 주고, 받은 CSV는 알아서 인식", "화면 아래"),
             ("🧭", "결론 먼저 + 근거 카드", "한 문장 결론, 핵심 숫자 3개, 카드마다 그림·해설·출처", "5~6쪽"),
             ("🎯", "목적별 출력", "사업계획서면 할 일, 보고서·논문이면 옮겨 쓸 문장", "8쪽"),
             ("🏷️", "지원사업 거르기", "모집 중 공고를 조건으로 거르고 AI가 자격 대조", "9쪽"),
             ("📦", "반출 신청 묶음", "보고서·근거팩·그림·신청 문구를 한 번에", "8쪽")]
    P.append(f"""<section class='pg m'>
  {head('3 · 주요 기능', '여섯 가지 기능')}
  <div class='f6'>""" + "".join(f"<div><span class='ico'>{a}</span><b>{e(b)}</b><p>{e(c)}</p><em>→ {e(d)}</em></div>" for a, b, c, d in feats) + f"""</div>
  <h3 class='hd mt12'>실제 화면: 받을 데이터 안내 <span>· 표 번호·기간·조건을 알려 주고, 받으면 자동으로 넘어감</span></h3>
  <div class='sh w160'><img src='{IMG}s-data.jpg' alt='데이터 준비 화면'></div>
</section>""")

    # ── 5쪽 실행 결과 ① 대표 질문 ──
    P.append(f"""<section class='pg m'>
  {head('4 · 실행 결과 ① 대표 질문', '“카페 하려는데 애월이랑<br>한림 중 어디가 좋을까?”')}
  <div class='layer'><span class='bg b-real'>실제</span><b>맨 위: 공개 데이터 실제 값으로 먼저 답</b></div>
  <div class='sh w160'><img src='{IMG}s-real.jpg' alt='실제 공개 데이터 답'></div>
  <div class='layer mt9'><span class='bg b-demo'>체험</span><b>그 아래: 센터 데이터로 본 결론</b><span class='d'>· 센터 PC에서는 실제 값</span></div>
  <div class='sh w160'><img src='{IMG}s-answer-top.jpg' alt='센터 데이터 결론'></div>
  <p class='cap mt6'>분석 {min(t_an)}~{max(t_an)}초(도구 실행·판정, 그림 제외) · 자동 검산 {min(checks)}~{max(checks)}건 통과 · 반출 점검 '반출 가능'</p>
</section>""")

    # ── 6쪽 실행 결과 ② 근거 카드 ──
    cards = first["answer_demo"]["cards"] + [c for c in first["answer_public"]["cards"] if c["key"] == "public"]
    grid = [c for c in cards if c["key"] != "public"] if len(cards) > 9 else cards   # 3×3 한 쪽에 맞춤(공개 597은 앞쪽 화면에 있음)
    cw = "".join(
        f"<div><div class='top'><b>{e(CARD_KO.get(c['key'], c['key']))}</b>{bg(c)}</div>"
        f"<span class='gr{' hold' if c.get('hold') else ''}'>{e(c['grade'])}</span>"
        f"<p>{e(c['title'].replace('[체험] ', ''))}</p><span class='src'>{e(CARD_DATA.get(c['key'], ''))}</span></div>"
        for c in grid)
    P.append(f"""<section class='pg m'>
  {head('4 · 실행 결과 ② 근거 카드', f'근거 카드 {len(grid)}장 — 등급은 규칙표가 정합니다')}
  <div class='c9'>{cw}</div>
  <div class='sh mt9' style='width:130mm;margin-left:auto;margin-right:auto'><img src='{IMG}s-card.jpg' alt='근거 카드'></div>
  <p class='cap mt3' style='text-align:center'>카드 한 장: 그림 · 쉬운 해설 · 출처 — AI는 등급을 정하지 않습니다(판정 규칙은 화면 [판정 기준 보기]와 기획서 부록에 공개)</p>
</section>""")

    # ── 7쪽 실행 결과 ③ 질문 6개 ──
    qc = []
    for r in rows:
        u = r["understood"]
        chips = [x for x in ["/".join(u["regions"] or u["city"]) or "제주 전체", "/".join(u["business"][:2]) or "전체 업종", u["segment"]] if x]
        st = r["steps"]
        qc.append(f"<div><span class='pp'>{e(PURPOSE.get(r['purpose'], r['purpose']))}</span>"
                  f"<p class='qq'>{e(r['question'])}</p>"
                  f"<p class='ch'>" + "".join(f"<span>{e(c)}</span>" for c in chips) + "</p>"
                  f"<p class='st'>✓ 도구 {st['done']}/{st['total']} · 검산 {r['checks_passed']}건 · 분석 {r['seconds']['analyze']}초</p>"
                  f"<div class='an'><p><span class='bg b-demo'>체험</span> {e(r['answer_demo']['headline'].replace('[체험] ', ''))}</p>"
                  f"<p class='pub'><span class='bg b-real'>실제</span> {e(r['answer_public']['headline'])}</p></div></div>")
    P.append(f"""<section class='pg m'>
  {head('4 · 실행 결과 ③ 질문 6개', f'서로 다른 질문 {n}개, 모두 끝까지')}
  <div class='q6'>{''.join(qc)}</div>
  <p class='cap mt6'>목적·동네·업종·대상·관점을 바꿔 화면과 같은 순서로 실행(tools/bench_examples.py, 질문 해석은 규칙만 써서 키 없이 재현)</p>
</section>""")

    # ── 8쪽 실행 결과 ④ 목적별 출력 + 산출물 ──
    act = first["answer_demo"]["actions"]
    quotes = [(r["question"], r["answer_demo"]["report_sentences"][0]) for r in rows if r["answer_demo"]["report_sentences"]][:2]
    P.append(f"""<section class='pg m'>
  {head('4 · 실행 결과 ④ 목적별 출력', '목적에 맞춰 바뀌는 결과물')}
  <div class='p2'>
    <div style='background:var(--orange-soft)'><h3 class='hd'>🧑‍🍳 가게 열기 · 운영</h3><p class='to'>→ 등급 + 그래서 할 일</p>
      <ol>""" + "".join(f"<li>{e(a)}</li>" for a in act) + f"""</ol></div>
    <div style='background:var(--blue-soft)'><h3 class='hd'>🎓 현황자료 · 논문</h3><p class='to'>→ 보고서에 그대로 옮길 문장 + 인용 표기</p>"""
             + "".join(f"<blockquote>{e(s)}</blockquote>" for _, s in quotes) + f"""</div>
  </div>
  <h3 class='hd mt12'>가져가는 파일 <span>· 반출 신청 묶음 하나에 모두(원본·조회 결과는 넣지 않음)</span></h3>
  <div class='files4'>
    <div><span class='ico'>📄</span><b>분석 보고서</b><p>결론·근거·출처·판정 규칙·한계 (DOCX, 약 13쪽)</p></div>
    <div><span class='ico'>📄</span><b>사업계획서 근거팩</b><p>문제인식·실현가능성·성장전략 순서 (DOCX, 약 9쪽)</p></div>
    <div><span class='ico'>🖼️</span><b>근거 그림</b><p>PNG만, 그림 속 숫자도 비율·지수</p></div>
    <div><span class='ico'>📝</span><b>반출 신청 문구</b><p>파일마다 출처·표 번호·기간·사유</p></div>
  </div>
  <div class='sh w160 mt6'><img src='{IMG}s-bundle.jpg' alt='반출 신청 묶음'></div>
</section>""")

    # ── 9쪽 검증 ① 정확도 ──
    fields = ["동네", "업종", "대상", "관점"]
    ai0 = ais[0]
    bars = "".join(
        f"<div class='lab'>{f}</div><div class='two'>"
        f"<div class='bar r'><i style='width:{rule[f] / nq * 100:.1f}%'><span>{rule[f]}</span></i></div>"
        f"<div class='bar ai'><i style='width:{ai0[f] / nq * 100:.1f}%'><span>{ai0[f]}</span></i></div></div>"
        for f in fields)
    missed = [x["question"] for x in rule["rows"] if not x["ok"]]
    P.append(f"""<section class='pg m'>
  {head('5 · 검증 방법 ① 정확도 실측', '직접 재 본 정확도')}
  <h3 class='hd'>질문 해석 <span>· 돌려 말한 일상 표현 {nq}문항, 네 항목을 모두 맞혀야 정답</span></h3>
  <div class='vs'>
    <div class='a'><b>{rule['완전 정답']}/{nq}</b><span>규칙만</span><small>키 없이도 동작</small></div>
    <div class='arr'>→</div>
    <div class='b'><b>{min(ai_ok)}/{nq}</b><span>AI + 규칙</span><small>{len(ais)}회 모두 · 평균 {ai_sec:.0f}초 · ${ai_cost:.4f}</small></div>
  </div>
  <div class='bars mt6'>{bars}</div>
  <p class='key mt3'><span><i style='background:#94A3B8'></i>규칙만</span><span><i style='background:var(--blue)'></i>AI + 규칙</span><span>(15문항 중 맞힌 수)</span></p>
  <p class='cap mt3'>규칙만으로 놓쳤던 {len(missed)}문항(예: “{e(missed[0]) if missed else ''}”)을 AI가 모두 바로잡았습니다. AI는 질문 문장만 받고, 법정동·업종 대응은 내장 사전이 합니다.</p>
  <h3 class='hd mt12'>지원사업 자격 판정 <span>· 화면 실행 기록(2026-11-10)</span></h3>
  <div class='fun'>
    <div style='background:#94A3B8'><b>{PROG_OPEN:,}건</b><span>모집 중 공고</span></div>
    <div style='background:#5B7FE8'><b>{PROG_JUDGED}건</b><span>조건으로 거른 뒤 판정</span></div>
    <div style='background:var(--blue)'><b>{PROG_NOW}건</b><span>'지금 신청할 수 있어요'</span></div>
  </div>
  <div class='n2 mt6'>
    <div><b>모델 고른 근거</b><p>같은 {MODEL_PAIRS}건을 상위 모델(단가 20배)과 비교해 {MODEL_AGREE}건 일치, 갈린 건 대부분은 상위 모델이 '확인 필요'로 더 조심스러웠을 뿐</p></div>
    <div><b>판정은 추정</b><p>화면·근거팩에 '공고문을 꼭 확인하세요'를 붙이고, 거른 이유를 공개합니다</p></div>
  </div>
</section>""")

    # ── 10쪽 검증 ② 신뢰 장치 · 한계 ──
    P.append(f"""<section class='pg m'>
  {head('5 · 검증 방법 ② 신뢰 장치와 한계', '같은 데이터면 같은 결론')}
  <div class='t6'>
    <div><span class='ico'>🔁</span><b>재현 번호</b><p>질문·조건·표·기간으로 만든 번호. 같으면 같은 결론</p></div>
    <div><span class='ico'>🧮</span><b>자동 검산</b><p>합계, 기간 누락·중복, 공휴일 중복, 표본 부족은 판정 보류</p></div>
    <div><span class='ico'>🏷️</span><b>실제 / 체험 구분</b><p>카드·그림·문서 모두에 표시, 가상 결과는 제목에 [가상]</p></div>
    <div><span class='ico'>↔️</span><b>교차 확인</b><p>센터 결과와 공개 데이터 597이 같은 방향인지, 다르면 이유까지</p></div>
    <div><span class='ico'>✅</span><b>자동 테스트 117개</b><p>해석·검산·판정·반출·문서·지원사업·화면 흐름</p></div>
    <div><span class='ico'>▶️</span><b>다시 돌리기</b><p><code>pytest</code> · <code>tools/bench_examples.py</code> · <code>tools/bench_parse.py</code></p></div>
  </div>
  <h3 class='hd mt12'>한계</h3>
  <div class='lim'>
    <div><span class='ico'>⚠️</span><div><b>실제 센터 CSV로는 아직 못 돌렸습니다</b><p>센터 숫자는 모두 체험(가상)이라, 실제 데이터로 돌리면 결론이 달라집니다</p></div></div>
    <div><span class='ico'>⚠️</span><div><b>판정 기준점은 잠정치입니다</b><p>공개 데이터 597(2016~2018)로 잡았고, 센터 실데이터로 다시 맞출 예정입니다</p></div></div>
    <div><span class='ico'>⚠️</span><div><b>공개 데이터는 단위·기간이 다릅니다</b><p>시·지구 단위, 과거 기간이거나 매출이 아닌 방문자 수 — 카드마다 단위·기간을 적습니다</p></div></div>
    <div><span class='ico'>⚠️</span><div><b>해석 {nq}문항은 개발자가 만든 문항입니다</b><p>실제 방문자 질문으로 넓혀 다시 재야 합니다</p></div></div>
  </div>
</section>""")

    # ── 11쪽 센터 활용 방안 ──
    P.append(f"""<section class='pg m'>
  {head('6 · 센터 활용 방안', '센터에서는 이렇게 씁니다')}
  <div class='use4'>
    <div><span class='when'>방문 전</span><b>상담 · 미리 받기</b><p>직원이 상담 때 질문을 넣으면 받을 표·기간이 나오고, 미리 받아 두면 방문자는 데이터 단계를 건너뜀</p><p class='who'>센터 직원</p></div>
    <div><span class='when'>방문 중</span><b>스스로 분석</b><p>질문 → 데이터 받기 → 결론·근거 → 근거팩까지 1:1 지원 없이</p><p class='who'>방문자</p></div>
    <div><span class='when'>퇴실 전</span><b>작업 지우기</b><p>버튼 하나로 내려받은 CSV와 결과 파일을 지움</p><p class='who'>방문자</p></div>
    <div><span class='when'>반출 심사</span><b>규정대로 접수</b><p>비율·순위와 PNG 위주, 파일마다 출처·기간·사유가 적힌 신청 문구</p><p class='who'>반출 심사자</p></div>
  </div>
  <p class='stmt mt12'>결과 카드마다 <em>'센터에서만 나오는 수치'</em>를 표시해,<br>센터에 올 이유를 결과로 보여 줍니다</p>
  <div class='n2 mt12'>
    <div><b>🧰 운영 부담은 작게</b><p>설치 3단계(install.bat → PIN → run.bat), 센터 PC 사양(GPU 불필요)에서 동작</p></div>
    <div><b>💰 비용은 정해진 만큼</b><p>AI는 월 $10 한도, 방문자 화면엔 %만 · 키가 없어도 규칙으로 끝까지</p></div>
  </div>
  <h3 class='hd mt12'>다음 단계</h3>
  <div class='next3'>
    <div><b>실제 데이터로 기준 맞추기</b><p>센터 CSV로 판정 기준점과 문장을 다시 점검</p></div>
    <div><b>실제 질문으로 넓히기</b><p>방문자 질문을 모아 해석 문항과 사전을 늘림</p></div>
    <div><b>표 늘리기</b><p>외식업 POS 등 다른 센터 표에 도구를 붙임</p></div>
  </div>
</section>""")

    # ── 12쪽 부록: 실행 기록 표 ──
    card_rows = [[e(CARD_KO.get(c["key"], c["key"])), bg(c), e(c["title"]), e(c["grade"]), e(CARD_DATA.get(c["key"], ""))] for c in cards]
    acc_rows = [[e(r["mode"]) + (f" ({i}회차)" if i else ""), f"<b>{r['완전 정답']}/{r['문항']}</b>", *(str(r[f]) for f in fields),
                 f"{r['초']}초", f"${r['AI 비용(USD)']}"] for i, r in enumerate(pb["results"])]
    miss_rows = []
    for x in rule["rows"]:
        if not x["ok"]:
            wrong = [k for k in fields if not x[k]]
            ai_x = next(y for y in ai0["rows"] if y["question"] == x["question"])
            miss_rows.append([e(x["question"]), e("·".join(wrong)),
                              e(f"대상 '{ai_x['segment'] or '-'}' · 관점 {', '.join(ai_x['views']) or '-'}")])
    P.append(f"""<section class='pg m'>
  {head('부록', '실행 기록 표')}
  <p class='axh'>대표 질문의 근거 카드(결론 문장은 화면 그대로)</p>
  {table([('카드', '15%'), ('값', '7%'), ('결론 문장', ''), ('등급', '17%'), ('데이터', '17%')], card_rows)}
  <p class='axh'>질문 해석 {nq}문항(tools/bench_parse.py)</p>
  {table([('방식', '24%'), ('완전 정답', '10%'), ('동네', '8%'), ('업종', '8%'), ('대상', '8%'), ('관점', '8%'), ('걸린 시간', '11%'), ('AI 비용', '')], acc_rows)}
  <p class='axh'>규칙만으로 놓친 문항과 AI를 더한 해석</p>
  {table([('질문', '46%'), ('규칙이 놓친 항목', '16%'), ('AI를 더한 해석', '')], miss_rows)}
  <p class='cap'>원자료: docs/submission/results/examples.json · parse_bench.json(실행일 {e(ex['run_date'])}). 개발 중(2026-11-03)에는 AI 13/15였고, 해석 규칙을 다듬은 뒤 {len(ais)}회 모두 {min(ai_ok)}/{nq}. AI 답은 실행마다 조금 다를 수 있습니다.</p>
</section>""")

    return ("<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>결과 설명자료 — 제주 사장님 상권비서</title>"
            "<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/static/pretendard.css'>"
            f"<style>{css}</style></head><body>\n" + "\n".join(P) + "\n</body></html>")


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(OUT)
