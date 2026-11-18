"""데이터 활용 명세서(HTML)를 카탈로그·동봉 파일에서 만든다. 손으로 옮겨 적지 않으므로 코드와 문서가 어긋나지 않는다.

    python tools/build_data_spec.py            → docs/submission/데이터_활용_명세서.html
PDF는 같은 폴더의 HTML을 브라우저 인쇄(A4)로 만든다(README '제출물 만들기' 참고).
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "submission" / "데이터_활용_명세서.html"
CENTER = json.loads((ROOT / "catalog" / "center_catalog.json").read_text(encoding="utf-8"))
PUBLIC = json.loads((ROOT / "catalog" / "public_datasets.json").read_text(encoding="utf-8"))

# 센터 표 컬럼을 이 서비스에서 어떻게 쓰는지(planner·tools·insight 기준)
CENTER_USE = {
    "base_year_month": "사용 — 월별 흐름(성수기·비수기), 기간 검산",
    "pt_year": "미사용(base_year_month로 대신)", "pt_month": "미사용(base_year_month로 대신)",
    "dstrct_se": "미사용(7개 권역, 질문 단위가 동네라서)",
    "city": "필터 — '제주시 전체'처럼 시 단위로 물을 때",
    "area_type": "미사용", "bjd": "사용 — 동네(법정동 73곳). 질문 지명을 이 값으로 맞춤",
    "biz_cd": "미사용(업종명으로 맞춤)", "biz_nm": "사용 — 업종(42종). '카페' → '비알콜 음료점업' 사전 대응",
    "user_type": "사용 — 내국인·도민·외국인(국가) 구분, 손님층 비중",
    "tour_type": "사용 — 도민/개별/단체 관광객. 관광객 몫의 기준",
    "week": "사용 — 요일 분포(1-12). '공휴일' 행은 원래 요일과 중복이라 비중에서 뺌",
    "time": "사용 — 시간대 5구간(1-14). 길이가 달라 1시간당 비중으로도 비교",
    "age": "미사용(다음 단계: 연령대 손님층)", "sex": "미사용",
    "user_cnt": "선택 — '손님 수'로 물을 때", "use_cnt": "선택 — '결제 건수'로 물을 때",
    "use_amt": "기본 측정값 — 매출(이용금액)",
}
CENTER_TABLES = [("1-08", "필수"), ("1-12", "필수"), ("1-14", "필수"), ("1-07", "호환(옛 형식, 같은 기간 값은 1-08과 같음)")]

PUBLIC_USE = {
    "허브-597": "공개 데이터로 먼저 보기, 센터 결과 방향 교차 확인(관광객 몫·계절·도심/읍면)",
    "허브-지구": "지구 유형 비교 카드(요일·시간대·손님 구성)",
    "공개-상가": "경쟁(가게 수) 카드, 가게 하나당 매출 지수",
    "공개-방문자": "최근 방문객 흐름 카드(월별·요일)",
    "공개-인구": "도민 1,000명당 같은 업종 가게 수",
}
FILES = {
    "허브-597": ["허브597_내국인관광객_카드이용_201609-201812.csv"],
    "허브-지구": ["허브_요일별_카드_201609-201711.csv", "허브_시간대별_카드_201609-201711.csv",
                "허브_이용자유형별_카드_201609-201711.csv"],
    "공개-상가": ["상가정보_제주_202609_동네업종별_가게수.csv"],
    "공개-방문자": ["방문자_제주_202510-202609_일별.csv"],
    "공개-인구": ["인구_제주_202610_법정동.csv"],
}
EXTRA_FILES = ["허브_업종별_카드_201609-201711.csv", "허브_연령성별_카드_201609-201711.csv", "허브_테마별_카드_201609-201812.csv"]
UPDATE_CMD = {
    "허브-597": "tools/windows/get_597.bat(PC) 또는 운영자 페이지 [지금 받기](데이터허브 프로젝트키)",
    "허브-지구": "tools/windows/get_hub.bat(PC, 6종을 한 번에)",
    "공개-상가": "python -m jeju_agent.stores update(키 불필요, 분기마다)",
    "공개-방문자": "python -m jeju_agent.datagokr update(공공데이터포털 인증키)",
    "공개-인구": "python -m jeju_agent.datagokr update(공공데이터포털 인증키)",
}

PREP = [
    ("인코딩·형식", "센터 CSV 전부", "UTF-8(BOM)·CP949·EUC-KR 순서로 읽기, 모든 값을 문자로 읽은 뒤 숫자 열만 변환, 앞뒤 공백 제거",
     "센터 CSV의 실제 인코딩이 공개되지 않음", "loader.read_csv_any"),
    ("'NA' 보존", "센터 CSV 전부", "문자열 'NA'를 결측으로 바꾸지 않음(빈칸만 결측)", "명세서상 'NA'는 실제 코드값일 수 있음", "loader.read_csv_any"),
    ("표 자동 판별", "내려받은 CSV", "컬럼명(영문)과 한글 라벨 일치도로 어느 표인지 판별(0.6 미만이면 묻기)", "방문자가 파일 이름을 바꿔도 인식", "loader.identify_table"),
    ("합계 행 제외", "카탈로그에 합계값이 정의된 표(597 '전체' 업종 등)", "다른 행과 더하면 두 번 세어지므로 뺌, 뺀 행 수를 화면에 알림", "이중 집계 방지", "loader.normalize_values"),
    ("공휴일 중복 제외", "1-12 요일별", "'공휴일' 행은 원래 요일에도 집계되어 있어 요일 비중 계산에서 뺌", "운영진 답변(2026-11-02)", "tools.pattern(exclude)"),
    ("시간대 길이 보정", "1-14 시간대", "시간대 길이(점심 3시간, 밤 9시간 등, 명세서 [참고4])로 나눈 1시간당 비중을 함께 계산", "길이가 다른 구간끼리 그대로 비교하면 왜곡", "tools.pattern(hours)"),
    ("값 표기 통일", "597", "연령대 표기('20 미만'·'20대미만' → '20대 미만') 통일, 값 앞뒤 공백 제거", "기간에 따라 원자료 표기가 다름", "public loader"),
    ("리 → 법정동 합산", "행안부 인구", "리 단위 인구를 법정동 이름으로 더함(애월읍 = 하귀1리 + 애월리 + …)", "센터 1-08의 법정동 단위에 맞춤", "datagokr.fetch_population"),
    ("가게 → 법정동×업종 집계", "상가정보", "제주 59,101곳을 법정동×업종(대·중·소분류) 가게 수로 줄이고 상호·주소·좌표는 버림, 카드 업종 대응(card_biz) 추가", "개인 사업장 정보 최소화, 센터 업종과 비교", "stores.aggregate"),
    ("제주만 남기기", "관광공사 방문자 수", "시군구 코드 50110(제주시)·50130(서귀포시)만, 구분 코드를 현지인·외지인·외국인으로", "전국 응답에서 제주만", "datagokr.fetch_visitors"),
    ("세 표 합치기", "관광지 및 상업지구 요일·시간대·이용자 유형", "districtType·dim·cat·userType·dtYearMonth·useCost 한 표로 합침", "지구 유형 비교를 한 번에", "hub_district.combined"),
    ("작은 값 처리", "반출 결과", "단순집계는 10 미만 값을 가리거나 범주로 바꿈, 결과는 비중·순위·지수(응용집계) 위주", "센터 반출 정책", "export_policy.suppress_small_values"),
]
POLICY = [
    ("원본·발췌 반출 불가(카드 등 반출 불가 데이터)", "반출 묶음에 원본·조회 결과·미리보기 표를 넣지 않음. 보고서·그림은 집계 결과만"),
    ("단순집계는 10 미만 수치가 없을 때만", "결과 표시는 비중·순위·지수(응용집계) 위주. 단순집계가 필요한 경우 10 미만을 가리고 '조건부'로 표시(엄격 해석)"),
    ("응용집계(비율·순위·지수 등)는 수치 포함 반출 가능", "판정·카드·근거팩의 숫자를 응용집계로 설계(관광객 몫 %, 성수기 지수, 동네 순위, 가게 하나당 매출 지수)"),
    ("시각화는 PNG/JPG만", "그림은 PNG로만 저장, 그림 안 숫자도 응용집계"),
    ("소스코드에 데이터 샘플 출력이 있으면 불가", "반출 대상 코드 점검기(code_has_data_print)로 head() 등 출력 검사"),
    ("자료마다 출처(원본데이터 명칭)·활용 사유 기재", "반출 신청 문구를 자동 작성(표 이름·기간·조건·활용 사유)"),
    ("반출 불가 데이터 원본·조회 결과는 외부 LLM 전송 불가", "AI에는 질문 문장과 지원사업 공고문만 보냄. 센터 데이터·분석 결과는 보내지 않음"),
    ("퇴실 후 삭제", "[퇴실 전 내 작업 지우기]가 질문·결과·반출 묶음과 이 화면이 읽은 내려받기 CSV를 지움"),
]


def e(x) -> str:
    return html.escape("" if x is None else str(x))


def rows_of(name: str) -> int:
    p = ROOT / "data" / "public" / name
    return len(pd.read_csv(p, dtype=str, encoding="utf-8-sig")) if p.exists() else 0


def table(head: list[tuple[str, str]], rows: list[list[str]], cls: str = "dense") -> str:
    th = "".join(f'<th style="width:{w}">{e(h)}</th>' if w else f"<th>{e(h)}</th>" for h, w in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><tr>{th}</tr>{body}</table>'


def center_section() -> str:
    tabs = {t["id"]: t for t in CENTER["tables"]}
    out = []
    for tid, role in CENTER_TABLES:
        t = tabs[tid]
        rows = [[f"<code>{e(c['name'])}</code>", e(c.get("label")), e(c.get("dtype")), e(c.get("example")),
                 e(CENTER_USE.get(c["name"].strip(), "미사용"))] for c in t["columns"]]
        out.append(f"<h3>{e(tid)} {e(t['name'])} <span class='tag'>{e(role)} · {e(t.get('period'))}</span></h3>")
        out.append(f"<p class='small muted'>{e(t.get('description', ''))[:260]}</p>")
        if tid == "1-07":
            out.append("<p class='small'>1-07은 2025년 6월까지의 옛 형식입니다. 앱은 같은 방식으로 읽지만 v02(1-08) 사용을 권장합니다(운영진 답변: 겹치는 기간 값은 같음). 컬럼은 1-08에서 dstrct_se만 없습니다.</p>")
            continue
        out.append(table([("컬럼", "17%"), ("한글명", "12%"), ("형식", "9%"), ("예시", "15%"), ("이 서비스에서", "")], rows))
    return "\n".join(out)


def public_section() -> str:
    out = []
    for t in PUBLIC["tables"]:
        tid = t["id"]
        files = FILES.get(tid, [])
        nrows = sum(rows_of(f) for f in files)
        meta = [["제공", e(t.get("provider"))], ["기간", e(t.get("period"))],
                ["출처", f"<a href='{e(t.get('source_url'))}'>{e(t.get('source_url'))}</a>"],
                ["이용조건", e(t.get("license"))], ["앱에서", e(PUBLIC_USE.get(tid, ""))],
                ["동봉 파일", "<br>".join(f"data/public/{e(f)}" for f in files) + f" ({nrows:,}행)"],
                ["새로 받기", e(UPDATE_CMD.get(tid, ""))]]
        cols = [[f"<code>{e(c['name'])}</code>", e(c.get("label")), e(c.get("example")), e(c.get("note"))] for c in t["columns"]]
        out.append(f"<h3>{e(t.get('source_name') or t['name'])} <span class='tag'>{e(tid)}</span></h3>")
        out.append(table([("항목", "13%"), ("내용", "")], meta))
        out.append(table([("컬럼", "17%"), ("한글명", "15%"), ("예시", "17%"), ("비고", "")], cols))
    return "\n".join(out)


def overview() -> str:
    rows = [
        ["<span class='badge b-center'>필수·센터</span>", "카드 이용 현황(읍면동)_v02 1-08", "제주빅데이터센터", "2025.05~현재(월)", "법정동×업종×이용자 구분", "손님 구성·계절·동네 순위", "센터 PC 안에서만, 반출은 응용집계·PNG"],
        ["<span class='badge b-center'>필수·센터</span>", "카드 이용 현황(요일별)_v02 1-12", "제주빅데이터센터", "같음", "법정동×업종×요일", "요일 분포(주말형·평일형)", "같음"],
        ["<span class='badge b-center'>필수·센터</span>", "카드 이용 현황(시간대)_v02 1-14", "제주빅데이터센터", "같음", "법정동×업종×시간대 5구간", "시간대 집중", "같음"],
        ["<span class='badge b-center'>참고·센터</span>", "데이터 명세서 v12(표 71종)", "제주빅데이터센터", "2026-01-28판", "표·컬럼·코드표", "표 추천·컬럼 판별·지명/업종 사전", "센터 제공 문서"],
        ["<span class='badge b-real'>필수·데이터허브</span>", "597 내국인 관광객 지역·업종·성별·연령대별 카드 이용", "제주데이터허브(제주특별자치도)", "2016.09~2018.12", "시군구·도심/읍면×업종 9종×관광객/도민×연령·성별", "공개 데이터로 먼저 보기·교차 확인", "제한 없음·무료"],
        ["<span class='badge b-real'>필수·데이터허브</span>", "관광지 및 상업지구 요일별·시간대별·이용자 유형별 카드", "제주데이터허브(제주특별자치도)", "2016.09~2017.11", "지구 5종×요일·시간대·이용자 유형", "지구 유형 비교", "제한 없음·무료"],
        ["<span class='badge b-real'>보조·포털</span>", "소상공인 상가(상권)정보", "소상공인시장진흥공단", "2026.09", "법정동×업종 가게 수", "경쟁(가게 수)", "제한 없음"],
        ["<span class='badge b-real'>보조·포털</span>", "한국관광공사 지역별 방문자 수", "한국관광공사", "2025.10~2026.09(일)", "제주시·서귀포시×현지인/외지인/외국인", "최근 방문객 흐름", "제한 없음"],
        ["<span class='badge b-real'>보조·포털</span>", "행정안전부 법정동 주민등록 인구", "행정안전부", "2026.10", "법정동", "도민 1,000명당 가게 수", "제한 없음"],
        ["<span class='badge b-real'>보조·포털</span>", "K-Startup 사업공고 · 기업마당 지원사업", "창업진흥원 · 중소벤처기업부", "실시간(30분 캐시)", "공고", "신청할 지원사업", "K-Startup 제한 없음, 기업마당 공공누리 제3유형"],
    ]
    return table([("구분", "11%"), ("데이터", "21%"), ("제공", "13%"), ("기간", "11%"), ("단위", "15%"), ("앱에서", "14%"), ("이용조건", "")], rows)


def build() -> str:
    css = (OUT.parent / "style.css").read_text(encoding="utf-8")
    extra = "".join(f"<li>data/public/{e(f)} ({rows_of(f):,}행)</li>" for f in EXTRA_FILES)
    parts = [
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>데이터 활용 명세서 — 제주 사장님 상권비서</title>",
        "<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/web/static/pretendard.css'>",
        f"<style>{css}\ncode{{font-size:7.4pt}} a{{color:var(--blue);word-break:break-all}}</style></head><body>",
        "<div class='cover' style='gap:6pt'><div class='kicker'>제주 AI·빅데이터 활용 AI Agent 개발 챌린지 · 제출물</div>",
        "<h1>데이터 활용 명세서</h1><div class='sub'>제주 사장님 상권비서가 쓰는 데이터의 출처·기간·컬럼·전처리·이용조건·반출 기준</div>",
        "<div class='box blue'><p><b>요약</b> — 센터 필수 데이터(카드 이용 현황 1-08·1-12·1-14)가 결론의 중심이고, 제주데이터허브 공개 데이터 2계열(597, 관광지 및 상업지구)로 "
        "먼저 답하고 방향을 교차 확인합니다. 센터 카드 데이터에 없는 경쟁(가게 수)·최근 방문객·인구는 공공데이터포털 실제 값으로 채웁니다. "
        "센터 데이터는 센터 PC 안에서만 분석하고, 외부 AI로 보내지 않으며, 반출은 응용집계·PNG로만 만듭니다.</p>"
        "<p style='margin:0' class='small muted'>이 문서는 tools/build_data_spec.py가 카탈로그(catalog/*.json)와 동봉 파일(data/public)에서 자동으로 만듭니다. "
        "이용조건은 각 데이터의 공공데이터포털 페이지 '이용허락범위' 표기(2026-11-10 확인)입니다.</p></div></div>",
        "<h2><span class='num'>1</span>데이터 목록</h2>", overview(),
        "<h2 style='margin-top:14pt'><span class='num'>2</span>센터 필수 데이터(컬럼별 사용 방식)</h2>",
        "<p class='small'>센터 조회 화면에서 표·기간(월)·조건을 골라 CSV(UTF-8, 영문 컬럼)로 내려받으면 앱이 내려받기 폴더를 3초마다 보고 자동으로 인식합니다. "
        "필요한 표·기간·조건은 질문에서 정해 화면에 안내합니다. 아래 '이 서비스에서'가 '미사용'인 컬럼은 읽기만 하고 결론에 쓰지 않습니다.</p>",
        center_section(),
        "<h2 style='margin-top:14pt'><span class='num'>3</span>공개 데이터(동봉, 실제 값)</h2>", public_section(),
        "<h3>함께 받아 동봉했지만 아직 화면에 쓰지 않는 파일</h3>",
        f"<ul class='small'>{extra}</ul><p class='small'>같은 '관광지 및 상업지구' 계열(업종별·연령성별)과 내국인 관광객 테마별 카드입니다. "
        "이용조건은 같고(공공데이터포털 15094890·15094891·15094859, 제한 없음), 화면 연결은 다음 단계입니다.</p>",
        "<h2 style='margin-top:14pt'><span class='num'>4</span>전처리 규칙</h2>",
        table([("규칙", "13%"), ("대상", "16%"), ("처리", "33%"), ("이유", "22%"), ("코드", "")],
              [[e(a), e(b), e(c), e(d), f"<code>{e(f)}</code>"] for a, b, c, d, f in PREP]),
        "<h2><span class='num'>5</span>센터 반출 정책 대응</h2>",
        "<p class='small'>근거: 제주빅데이터센터 데이터 반출 정책(2026-09-01 개정). 해석이 갈리는 부분은 엄격하게 해석했습니다.</p>",
        table([("정책", "38%"), ("이 서비스의 처리", "")], [[e(a), e(b)] for a, b in POLICY]),
        "<h2><span class='num'>6</span>데이터 맞추기(결합)와 한계</h2><ul>",
        "<li><b>법정동</b>: 센터 1-08·상가정보·행안부 인구 모두 법정동 73곳 이름으로 맞춥니다. 센터 법정동 목록은 이름만 있어, 제주시·서귀포시에 하나씩 있는 '월평동'은 인구·가게 수 모두 두 곳을 합친 값으로 계산합니다(알려진 한계).</li>",
        "<li><b>업종</b>: 상가정보 업종(소분류)을 센터 카드 업종 42종에 대응시킨 card_biz(예: 카페 → 비알콜 음료점업, 펜션 → 여관업). 대응이 없는 업종은 경쟁 카드를 만들지 않습니다.</li>",
        "<li><b>지구 유형</b>: 관광지 및 상업지구 데이터에는 어느 동네가 어느 지구인지 없습니다. 질문 동네와 가장 가까운 유형(읍면 → 내국인 주요 관광지, 제주시 원도심 동 → 제주시 구도심 등)을 정하고 화면에 '추정'이라고 적습니다.</li>",
        "<li><b>결합하지 않은 것</b>: 유동인구(행정동 43곳)와 카드(법정동 73곳)는 단위가 달라 아직 결합하지 않습니다.</li>",
        "<li><b>해석 주의</b>: 카드 데이터는 비씨카드 결제 기준이라 매출 전체가 아닙니다 → 비율·순위로 해석합니다. 관광공사 '방문자'는 이동통신 추정 방문자로 매출이 아닙니다. "
        "공개 데이터는 시·지구 단위이고 기간이 과거(597 2016~2018)이거나 최근(방문자 2025~2026)이라 카드마다 단위·기간을 적습니다.</li>",
        "<li><b>표본·기간</b>: 관심 대상 자료가 30행 미만이면 판정 보류, 12개월이 안 되면 계절 판정을 하지 않습니다.</li></ul>",
        "</body></html>",
    ]
    return "\n".join(parts)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(OUT)
