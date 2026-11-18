"""결론 먼저: 분석 결과(StepOutcome) → 판정 문장 + 핵심 수치(KPI) 3개 + 할 일 3개 + 결론형 근거 카드.

원칙
- 판정은 LLM이 아니라 아래 공개 규칙표로 코드가 한다(VERDICT_RULES). 같은 데이터면 늘 같은 결론(재현성).
- 입력은 분석 도구의 응용집계(비중·배율·순위·지수)뿐 → 반출 기준과 같은 수치로 판정한다.
- 숫자는 '100원 중 56원', '8월이 2월의 1.5배'처럼 바로 와닿는 말로 바꾼다.
- 가상 데이터·공개 데이터 결론은 그 사실을 함께 적는다. 경쟁(가게 수)은 공개 상가정보(실제 값)로 판정하고,
  센터 매출 몫이 있으면 '가게 하나당 매출 지수'(매출 몫 ÷ 가게 몫)까지 본다.
- 목적이 논문·연구/현황자료면 등급 라벨과 '할 일' 대신 중립 서술(문어체)과 인용 표기를 준다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .agent import StepOutcome
from .korean import fmt_month_short, josa
from .planner import Plan, _short_biz, _short_region

# ── 판정 규칙표(화면 [판정 기준 보기]와 기획서에 그대로 싣는다) ───────────────────────────
TOURIST_GRADES = [(65, "뚜렷한 관광객 장사"), (55, "관광객 장사"), (45, "관광객·도민 반반"),
                  (35, "도민 단골 장사"), (-1, "뚜렷한 도민 단골 장사")]
SEASON_BIG, SEASON_SOME = 2.0, 1.5
PEAK_INDEX, LOW_INDEX = 120, 80
WEEKEND_TYPE, WEEKDAY_TYPE = 33.0, 25.0
HOUR_FOCUS = 1.2
MIN_ROWS = 30
PER_STORE_HIGH, PER_STORE_LOW = 1.2, 0.8
VERDICT_RULES = [
    ("손님 구성", "관광객(개별+단체) 매출 비중 T: 65% 이상 '뚜렷한 관광객 장사', 55~65 '관광객 장사', 45~55 '관광객·도민 반반', "
              "35~45 '도민 단골 장사', 35 미만 '뚜렷한 도민 단골 장사'. 제주 전체 같은 업종과의 차이가 3%p 미만이면 "
              "'평균 수준', 3~10 '다소', 10 이상 '뚜렷이'. 관심 대상 자료가 30행 미만이면 판정 보류.",
     "기준점: 공개 데이터 597에서 읍면 식당·카페 64.6~65.0%, 제주시 도심 29.3%"),
    ("계절", "가장 많은 달 ÷ 가장 적은 달 R: 2.0배 이상 '계절 영향 큼', 1.5~2.0 '계절 영향 있음', 1.5 미만 '사계절 고른 편'. "
           "평소 달(기간 평균)=100일 때 120 이상은 성수기, 80 미만은 비수기. 12개월이 안 되면 판정하지 않음.",
     "기준점: 597에서 관광객 매출 2.3배, 도민 매출 1.5배(제주시 읍면 식음료)"),
    ("시장 크기", "제주 전체 같은 업종 매출 중 그 동네의 몫과 순위 r: 3위 안 '손꼽히는 큰 시장', 10위 안 '큰 시장', "
               "절반 안 '중간 시장', 그 밖 '작은 시장'.", "경쟁은 아래 '경쟁(가게 수)'에서 따로 판정"),
    ("경쟁(가게 수)", "같은 업종 가게 수의 동네 순위 k: 3위 안 '가게가 손꼽히게 많은 동네', 10위 안 '가게가 많은 동네', "
                   "절반 안 '가게 수 중간', 그 밖 '가게가 적은 동네'. 센터 매출 몫이 있으면 매출 몫 ÷ 가게 몫 = 가게 하나당 "
                   "매출 지수 E: 1.2 이상 '가게 수에 비해 손님 넉넉', 0.8~1.2 '평균 수준', 0.8 미만 '가게가 많은 편(경쟁 셈)'.",
     "가게 수: 소상공인시장진흥공단 상가(상권)정보(실제 공개 데이터). 가게 크기·실제 영업 여부는 반영하지 않음"),
    ("요일", "토+일 비중 W: 33% 이상 '주말형', 25% 이하 '평일형'(고르게 나뉘면 28.6%). 공휴일은 원래 요일에 포함돼 뺌.",
     "운영진 답변(2026-11-02): 공휴일은 원래 요일에도 집계"),
    ("시간대", "시간대마다 길이가 달라(점심 3시간, 밤 9시간) 1시간당 비중으로 비교. 1위가 2위의 1.2배 이상이면 '집중형'.",
     "명세서 [참고4] 시간대 기준"),
]
SEASON_NAME = {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄", 6: "여름", 7: "여름", 8: "여름",
               9: "가을", 10: "가을", 11: "가을"}
NEUTRAL_PURPOSES = ("논문·연구", "현황자료·보고서")
WEEK = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


@dataclass
class KPI:
    label: str
    value: str
    delta: str = ""
    help: str = ""
    chart: list[float] | None = None


@dataclass
class Card:
    key: str              # customers / season / location / week / time / public
    eyebrow: str          # 머리표(분석 종류 · 센터 전용 여부)
    title: str            # 결론 문장
    explain: str          # 해석 1~2줄
    sowhat: str           # 그래서(할 일)
    grade: str            # 등급 라벨
    step_index: int
    synthetic: bool = False
    public: bool = False
    hold: bool = False    # 판정 보류
    extra: list[str] = field(default_factory=list)   # 접어 둘 보조 문장(연령대 등)
    phrase: str = ""      # 판정 문장 조립용
    vals: dict = field(default_factory=dict)          # 문장 조립용 수치(응용집계)
    report: str = ""      # 보고서·사업계획서에 옮겨 쓸 문장(문어체, %p 허용)


@dataclass
class Answer:
    headline: str
    question_line: str
    kpis: list[KPI] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    core: str = ""
    market: str = ""      # 부제: 시장 크기 문장
    badges: list[tuple[str, str]] = field(default_factory=list)    # (글, 색)
    cards: list[Card] = field(default_factory=list)
    public_card: Card | None = None
    caveats: list[str] = field(default_factory=list)
    basis: list[str] = field(default_factory=list)
    trust: list[str] = field(default_factory=list)
    neutral: bool = False
    report_sentences: list[str] = field(default_factory=list)
    citation: str = ""
    synthetic: bool = False


def _m(ym: str) -> int:
    return int(str(ym)[4:6])


def _mon(ym: str, first_year: str = "") -> str:
    """'202601' → '1월'(첫해와 다른 해의 달이면 '26년 1월')."""
    s = str(ym)
    if len(s) != 6:
        return s
    return (f"{s[2:4]}년 " if first_year and s[:4] != first_year else "") + f"{int(s[4:])}월"


def _purpose(plan: Plan) -> str:
    p = plan.slots.purpose
    return p if p in ("사업계획서·창업", "가게·회사 운영", "현황자료·보고서", "논문·연구") else "사업계획서·창업"


def _grade_tourist(t: float) -> str:
    return next(name for th, name in TOURIST_GRADES if t >= th)


def _cmp_word(d: float) -> str:
    a = abs(d)
    if a < 3:
        return "평균 수준"
    return ("다소 " if a < 10 else "뚜렷이 ") + ("높음" if d > 0 else "낮음")


def _flags(o: StepOutcome, loaded: dict) -> tuple[bool, bool]:
    lt = loaded.get(o.step.table_id)
    return bool(lt is not None and getattr(lt, "synthetic", False)), o.step.table_id.startswith("허브-")


# ── 분석별 카드 ─────────────────────────────────────────────────────
def card_customers(i: int, o: StepOutcome, plan: Plan, purpose: str) -> Card | None:
    a = o.result.facts.get("applied", {})
    T, B, d = a.get("관심 대상 비중(%)"), a.get("비교 기준 비중(%)"), a.get("차이(%p)")
    if T is None or T != T:
        return None
    p = o.step.params
    label = p.get("label", "관광객")
    fl, bl = p.get("focus_label", "관심 대상"), p.get("base_label", "제주 전체")
    n_rows = o.result.facts.get("simple", {}).get("관심 대상 행 수", MIN_ROWS)
    if p.get("seg_col") == "user_type":                       # 외국인·국적: 보통 몇 % 수준 → '평균의 몇 배'
        times = round(T / B, 1) if B else None
        title = f"{fl} 매출 중 {label} 손님 몫은 {T}%입니다"
        explain = f"{bl} 평균은 {B}%입니다." + (f" 평균의 {times}배입니다." if times else "")
        sowhat = ("외국어 메뉴판·해외 결제수단·외국어 지도 등록을 준비할 근거가 됩니다." if times and times >= 1.5 else
                  "외국인 손님은 평균 수준입니다. 내국인 관광객·도민을 먼저 겨냥하는 편이 효율적입니다.")
        grade = f"{label} 손님이 평균의 {times}배" if times else f"{label} 손님 {T}%"
        return Card("customers", "손님 구성", title, explain, sowhat, grade, i,
                    phrase=f"{label} 손님 몫이 {T}%로 제주 평균의 {times}배인 곳" if times else f"{label} 손님 몫이 {T}%인 곳",
                    vals={"T": T, "B": B, "d": d, "near": False},
                    report=f"{fl} 카드 매출 중 {label} 결제 비중은 {T}%로, {bl} 평균({B}%)의 {times}배다." if times else "")
    who = "내국인 관광객" if "내국인" in label else ("도민" if label == "도민" else "관광객")
    rest = "도민" if "내국인" in label else ("관광객·법인 카드" if who == "도민" else "도민·법인 카드")
    grade = _grade_tourist(T if who != "도민" else 100 - T)
    hold = n_rows < MIN_ROWS
    title = f"{fl} 손님 돈의 {T}%는 {who} 지갑에서 나옵니다"
    if d is None or B is None or B != B:
        cmp_ = ""
    elif abs(d) < 3:
        cmp_ = f"{bl}({B}%){josa(bl, '과/와')} 비슷합니다. "
    else:
        cmp_ = f"{bl}({B}%)보다 {abs(d)}%포인트 {'높습니다' if d > 0 else '낮습니다'}. "
    explain = cmp_ + f"100원을 벌면 {round(T)}원은 {who}, {100 - round(T)}원은 {rest}에서 옵니다."
    tour = T if who != "도민" else 100 - T
    if tour >= 55:
        sowhat = "관광객이 줄어드는 비수기에도 버틸 도민 단골 상품(평일 할인, 동네 정기권 등)을 함께 계획해 보세요."
    elif tour >= 45:
        sowhat = "관광객과 도민을 함께 겨냥한 메뉴·가격을 검토해 보세요(평일 도민, 주말·성수기 관광객)."
    else:
        sowhat = "동네 단골이 매출의 중심입니다. 관광객 유입은 추가 기회로 볼 수 있습니다."
    c = Card("customers", "손님 구성", title, explain, sowhat, grade, i, hold=hold, phrase=grade,
             vals={"T": T, "B": B, "d": d, "near": any(abs(T - th) < 1 for th, _ in TOURIST_GRADES if th > 0)})
    if d is not None and B is not None and B == B:
        c.report = (f"{fl} 카드 매출 중 {who} 결제 비중은 {T}%로, {bl} 평균({B}%)"
                    + (f"과 비슷하다." if abs(d) < 3 else f"보다 {abs(d)}%p {'높' if d > 0 else '낮'}다."))
    if hold:
        c.title, c.grade, c.phrase = "자료가 적어 손님 구성을 판정하지 않습니다", "판정 보류(표본 부족)", ""
        c.explain = f"관심 대상 자료가 {n_rows}행뿐입니다. 이웃 동이나 같은 권역으로 넓혀 다시 보세요."
    elif d is not None and d == d:
        c.extra = [f"제주 전체 같은 업종과 비교: {_cmp_word(d)}"]
    return c


def card_season(i: int, o: StepOutcome, purpose: str) -> Card | None:
    a = o.result.facts.get("applied", {})
    hi, lo, R = a.get("가장 높은 기간"), a.get("가장 낮은 기간"), a.get("최고/최저 배율")
    idx = a.get("월 지수", {})
    if not (hi and lo and R):
        return None
    months = [str(k)[4:6] for k in idx]
    dup = {m for m in months if months.count(m) > 1}

    def mon(k):      # 12개월 창에 같은 달이 두 번 나올 때만 연도를 붙인다
        k = str(k)
        return f"{k[:4]}년 {int(k[4:6])}월" if k[4:6] in dup else f"{int(k[4:6])}월"
    hm, lm = mon(hi), mon(lo)
    R1 = a.get("최고/최저 배율(화면)") or round(R, 1)
    n = len(idx)
    if n < 12:
        return Card("season", "월별 흐름", f"기간이 {n}개월이라 성수기를 판정하지 않습니다",
                    f"가장 많은 달은 {hm}, 가장 적은 달은 {lm}입니다.", "12개월 이상 데이터를 받아 다시 보세요.",
                    "판정 보류(기간 짧음)", i, hold=True)
    grade = "계절 영향 큼" if R >= SEASON_BIG else ("계절 영향 있음" if R >= SEASON_SOME else "사계절 고른 편")
    peaks = [k for k, v in idx.items() if v >= PEAK_INDEX]
    lows = [k for k, v in idx.items() if v < LOW_INDEX]
    title = f"가장 잘 되는 {hm}{josa(hm, '이/가')} 가장 한산한 {lm}의 {R1}배입니다"
    explain = f"평소 달(기간 평균)을 100으로 보면 {hm}은 {round(idx.get(hi, 0))}, {lm}은 {round(idx.get(lo, 0))}입니다."
    if peaks:
        explain += f" 성수기(120 이상)는 {'·'.join(mon(k) for k in peaks)}"
        explain += f", 비수기(80 미만)는 {'·'.join(mon(k) for k in lows)}입니다." if lows else "입니다."
    elif lows:
        explain += f" 비수기(80 미만)는 {'·'.join(mon(k) for k in lows)}입니다."
    keys = list(idx)
    if len(keys) >= 3:          # 이어진 석 달 중 가장 약한 구간(비수기 깊이)
        j = min(range(len(keys) - 2), key=lambda q: sum(idx[keys[q + t]] for t in range(3)))
        D = sum(idx[keys[j + t]] for t in range(3)) / 3
        if D < 80:
            explain += (f" 가장 약한 석 달({mon(keys[j])}~{mon(keys[j + 2])})은 평소의 {round(D / 10)}할 수준입니다.")
    if R >= SEASON_BIG:
        low_set = lows or [lo]
        pct = [round(idx[k]) for k in low_set]
        sowhat = (f"비수기 {len(low_set)}개월(평소의 {min(pct)}~{max(pct)}%)을 버틸 임대료·인건비를 "
                  + ("개업 자금에 넣어 두세요." if purpose == "사업계획서·창업" else "미리 준비해 두세요."))
    elif R >= SEASON_SOME:
        sowhat = f"한산한 {_mon(lo)} 전후에는 인력·재료를 줄이고, {_mon(hi)} 전에 미리 늘리는 계획을 세워 두세요."
    else:
        sowhat = "계절 차이가 작아 1년 내내 같은 운영 계획을 써도 됩니다. 요일·시간대 운영이 더 중요합니다."
    yoy = a.get("최근 달 전년 같은 달 대비(%)")
    extra = [f"{fmt_month_short(a.get('최근 달', ''))}은 1년 전 같은 달보다 {yoy:+}%입니다."] if yoy is not None else []
    hs, ls = SEASON_NAME[_m(hi)], SEASON_NAME[_m(lo)]
    phrase = {"계절 영향 큼": f"{hs}에 벌고 {ls}을 버텨야 하는" if hs != ls else "계절을 많이 타는",
              "계절 영향 있음": f"{hs}에 조금 더 버는", "사계절 고른 편": "사계절 고르게 버는"}[grade]
    il = round(idx.get(lo, 0))
    report = (f"월별 카드 매출(평소=100)은 {hm} {round(idx.get(hi, 0))}, {lm} {il}{josa(str(il), '으로/로')} "
              f"최고 달이 최저 달의 {R1}배다.")
    return Card("season", "월별 흐름", title, explain, sowhat, grade, i, extra=extra, phrase=phrase,
                vals={"hi": hm, "lo": lm, "R": R1, "idx_hi": round(idx.get(hi, 0)), "idx_lo": round(idx.get(lo, 0))},
                report=report)


def _who(params: dict) -> str:
    """비교한 손님 구분의 짧은 이름(관광객·도민·중국인·외국인…)."""
    lab = params.get("label", "관광객")
    if params.get("seg_col") == "user_type":
        return lab if lab in ("중국인", "일본인") else "외국인"
    return "내국인 관광객" if "내국인" in lab else "도민" if lab == "도민" else "단체 관광객" if lab == "단체 관광객" else "관광객"


def card_regions(i: int, o: StepOutcome, plan: Plan) -> Card | None:
    """'연동이랑 노형동 비교' — 동네를 합치지 않고 나란히: 손님 구성·매출 순위·계절."""
    a = o.result.facts.get("applied", {})
    rows = [r for r in a.get("동네", []) if r.get("관광객 비중(%)") is not None]
    if len(rows) < 2:
        return None
    biz = _short_biz(plan.slots.business, plan.slots.biz_label) or "같은 업종"
    who = _who(o.step.params)
    hi = max(rows, key=lambda r: r["관광객 비중(%)"])
    lo = min(rows, key=lambda r: r["관광객 비중(%)"])
    gap = round(hi["관광객 비중(%)"] - lo["관광객 비중(%)"], 1)
    n, base = a.get("지역 수"), a.get("제주 평균 관광객 비중(%)")
    if gap >= 2:
        title = (f"{hi['동네']} {biz}{josa(biz, '은/는')} {who} 몫이 {hi['관광객 비중(%)']}%로 "
                 f"{lo['동네']}({lo['관광객 비중(%)']}%)보다 {gap}%p 높습니다")
    else:
        title = (f"{'·'.join(r['동네'] for r in rows)} {biz}의 {who} 몫은 "
                 f"{'·'.join(str(r['관광객 비중(%)']) + '%' for r in rows)}로 비슷합니다")
    ranked = sorted(rows, key=lambda r: r["매출 순위"] or 999)
    explain = ("매출 순위는 " + ", ".join(f"{r['동네']} {r['매출 순위']}위(몫 {r['매출 몫(%)']}%)" for r in ranked)
               + (f" — 제주 {n}곳 중입니다." if n else "입니다."))
    seas = [r for r in rows if r.get("성수기÷비수기(배)")]
    if seas:
        explain += " 성수기÷비수기는 " + ", ".join(f"{r['동네']} {r['성수기÷비수기(배)']}배({r['성수기']}↔{r['비수기']})"
                                              for r in seas) + "입니다."
    if gap >= 5:
        sowhat = f"{who} 손님을 노린다면 {hi['동네']}, 도민 단골을 노린다면 {lo['동네']} 쪽이 맞습니다."
    else:
        sowhat = (f"{hi['동네']}의 {who} 몫이 조금 더 높지만({gap}%p) 큰 차이는 아닙니다. "
                  "시장 크기(매출 순위)와 임대료·가게 수로 고르세요." if gap >= 2 else
                  "손님 구성은 비슷하니 시장 크기(매출 순위)와 임대료·가게 수로 고르세요.")
    if ranked[0]["매출 순위"] and ranked[-1]["매출 순위"] and ranked[0]["매출 순위"] != ranked[-1]["매출 순위"]:
        sowhat += f" 시장은 {ranked[0]['동네']}{josa(ranked[0]['동네'], '이/가')} 더 큽니다."
    report = (f"{biz} 카드 매출 중 {who} 결제 비중은 " + ", ".join(f"{r['동네']} {r['관광객 비중(%)']}%" for r in rows)
              + (f"로 {hi['동네']}{josa(hi['동네'], '이/가')} {gap}%p 높다" if gap >= 2 else "로 비슷하다")
              + (f"(제주 전체 평균 {base}%)." if base is not None else "."))
    return Card("regions", "동네 비교", title, explain, sowhat, f"{who} 몫 차이 {gap}%p", i,
                vals={"rows": rows, "gap": gap, "N": n, "base": base, "who": who}, report=report)


def card_location(i: int, o: StepOutcome, plan: Plan, has_stores: bool = False) -> Card | None:
    t = o.result.table
    a = o.result.facts.get("applied", {})
    if t is None or not len(t) or "bjd" not in t.columns:
        return None
    biz = _short_biz(plan.slots.business, plan.slots.biz_label) or "같은 업종"
    n = a.get("지역 수", len(t))
    top3 = ", ".join(f"{k}({p}%)" for k, p in zip(t["bjd"].head(3), t["비중(%)"].head(3)))
    mine = a.get("관심 지역 순위", {})
    explain = f"같은 업종 매출을 동네별로 나누면 {top3} 순입니다. 막대는 제주 전체 {biz} 매출 중 그 동네의 몫입니다."
    avg = a.get("동네 평균 비중(%)")
    if mine:
        name, (r, S) = min(mine.items(), key=lambda kv: kv[1][0])
        if len(mine) > 1:                     # 용담일·이·삼동처럼 여러 법정동이면 합쳐서
            name = _short_region(plan.slots.regions) or name
            S = a.get("관심 지역 몫 합계(%)", round(sum(v[1] for v in mine.values()), 1))
        grade = ("제주에서 손꼽히는 큰 시장" if r <= 3 else "큰 시장" if r <= 10 else
                 "중간 시장" if r <= n / 2 else "작은 시장")
        title = f"{name}{josa(name, '은/는')} 제주 {biz} 매출 {r}위 동네입니다({n}곳 중)"
        explain = (f"제주 전체 {biz} 매출 100원 중 {round(S)}원({S}%)이 {name}에서 나옵니다. "
                   f"1위는 {t['bjd'].iloc[0]}({t['비중(%)'].iloc[0]}%)입니다.")
        if avg and a.get("동네 평균 대비 배수"):
            explain += f" {name}{josa(name, '은/는')} 동네 평균({avg}%)의 {a['동네 평균 대비 배수']}배입니다."
        explain += (" 경쟁이 센지는 아래 '경쟁(가게 수)' 카드에서 함께 봅니다." if has_stores
                    else " 가게 수 자료가 없어 경쟁이 센지는 이 데이터로 알 수 없습니다.")
        if r <= 10:
            sowhat = ("수요가 큰 만큼 자리 잡은 가게도 많을 수 있습니다. 아래 경쟁 카드의 가게 수와 함께 보세요." if has_stores
                      else f"수요가 큰 만큼 자리 잡은 가게도 많을 수 있습니다. 같은 동의 {biz} 수를 소상공인365(무료)나 "
                      "외식업 POS(1-19)로 확인해 보세요.")
        elif r > n / 2:
            sowhat = "수요가 작은 동네입니다. 상위 동네 손님을 끌어올 이유(메뉴·위치)를 정리해 보세요."
        else:
            sowhat = "중간 규모 시장입니다. 임대료·가게 수와 함께 비교해 보세요."
        phrase = f"제주 {biz} 매출 {r}위 시장" if r > 3 else f"제주에서 손꼽히는 {biz} 시장({r}위)"
        report = f"{name}{josa(name, '은/는')} {biz} 카드 매출이 발생한 제주 {n}개 읍면동 가운데 {r}위(제주 전체의 {S}%)다."
        vals = {"name": name, "r": r, "S": S, "N": n}
        if len(mine) > 1:                     # 순위는 동네마다 따로(합친 몫에 한 동네 순위를 붙이지 않는다)
            rk = "·".join(f"{k} {v[0]}위" for k, v in sorted(mine.items(), key=lambda kv: kv[1][0]))
            title = f"{name} {biz} 매출은 제주 전체의 {S}% — {rk}({n}곳 중)"
            explain = explain.replace(f"{name}에서 나옵니다. ", f"{name}에서 나옵니다(동네별 순위 {rk}). ", 1)
            phrase = f"제주 {biz} 매출의 {S}%가 나오는 시장"
            report = f"{name}의 {biz} 카드 매출은 제주 전체의 {S}%이고, 제주 {n}개 읍면동 가운데 순위는 {rk}다."
            vals["rk"] = rk
    else:
        grade = f"1위 {t['bjd'].iloc[0]}"
        title = f"제주에서 {biz} 매출이 가장 큰 동네는 {t['bjd'].iloc[0]}({t['비중(%)'].iloc[0]}%)입니다"
        sowhat = "후보 동네를 2~3곳 정해 같은 질문으로 비교해 보세요(손님 구성·계절이 다를 수 있습니다)."
        phrase = ""
        report = f"{biz} 카드 매출이 가장 큰 읍면동은 {top3} 순이다."
        vals = {"top1": t["bjd"].iloc[0], "N": n}
    return Card("location", "시장 크기 · 다른 동네와 비교", title, explain, sowhat, grade, i, phrase=phrase,
                report=report, vals=vals)


FOOD_WORDS = ("음식", "식당", "음료", "카페", "커피", "주점", "제과", "빵", "한식", "일식", "중식", "양식", "분식", "치킨",
              "피자", "브런치", "술집", "고깃집", "횟집", "외식", "식음료")
UNFOOD = [("외국어 메뉴판", "외국어 안내문"), ("메뉴·가격", "상품·가격"), ("메뉴·좌석·영업시간", "상품·서비스·영업시간"),
          ("메뉴·위치", "상품·위치"), ("메뉴로", "상품으로"), ("인력과 메뉴", "인력과 상품"), ("대표 메뉴", "대표 상품"),
          ("메뉴", "상품")]


def is_food(plan: Plan) -> bool:
    s = plan.slots
    text = " ".join(s.business or []) + " " + (s.biz_label or "")
    return not text.strip() or any(w in text for w in FOOD_WORDS)


def unfood(text: str) -> str:
    for a, b in UNFOOD:
        text = text.replace(a, b)
    return text


NO_REST_BIZ = ("숙박", "호텔", "여관", "펜션", "민박", "콘도", "모텔", "편의점", "렌터카", "자동차 임대", "주유")


def card_week(i: int, o: StepOutcome, biz: str = "") -> Card | None:
    a = o.result.facts.get("applied", {})
    share = {w: a.get(f"{w} 비중(%)") for w in WEEK if a.get(f"{w} 비중(%)") is not None}
    if len(share) < 7:
        return None
    W = round(share["토요일"] + share["일요일"], 1)
    grade = "주말형" if W >= WEEKEND_TYPE else ("평일형" if W <= WEEKDAY_TYPE else "요일 고른 편")
    hi, lo = a.get("가장 많은 시점", ""), a.get("가장 적은 시점", "")
    p, q = a.get("최고 시점 비중(%)"), a.get("최저 시점 비중(%)")
    best = max(range(5), key=lambda k: sum(share[w] for w in WEEK[k:k + 3]))      # 이어진 사흘 중 매출이 가장 큰 묶음
    three = WEEK[best:best + 3]
    s3 = round(sum(share[w] for w in three), 1)
    hi_s = hi.replace("·", "·")
    if p - q < 3:
        title = "요일 차이가 거의 없습니다"
    elif s3 >= 45:
        title = f"{'·'.join(w[0] for w in three)} 사흘에 매출의 {s3}%가 몰립니다 — {hi_s}{josa(hi_s, '이/가')} 가장 많음({p}%)"
    else:
        title = f"{hi_s}에 가장 많이 팔립니다({p}%)"
    explain = (f"고르게 팔리면 하루 14.3%입니다. 토·일 이틀은 {W}%입니다. {lo}{josa(lo, '은/는')} {q}%로 가장 적습니다. "
               "공휴일 매출은 원래 요일에 이미 들어 있어 두 번 세지 않았습니다.")
    low2 = sorted(share, key=share.get)[:2]
    if share[low2[1]] - share[low2[0]] < 0.3:   # 거의 같은 두 요일은 함께
        rest_txt = f"{low2[0]}·{low2[1]}({share[low2[0]]}%·{share[low2[1]]}%)"
    else:
        rest_txt = f"{lo}({q}%)"
    if any(w in biz for w in NO_REST_BIZ):     # 쉬는 날이 없는 업종(숙박·편의점·렌터카): 한산한 요일을 채우는 쪽으로
        sowhat = (f"가장 한산한 {rest_txt}에는 평일 할인·연박 같은 혜택으로 손님을 채우고, "
                  f"일손은 {'·'.join(w[0] for w in three)}에 모으세요.")
    else:
        sowhat = (f"쉬는 날을 정한다면 매출이 가장 적은 {rest_txt}의 손실이 가장 작습니다. "
                  f"일손은 {'·'.join(w[0] for w in three)}에 모으세요.")
    report = (f"요일별 카드 매출은 {'·'.join(w[0] for w in three)} 3일에 {s3}%가 집중되며(토·일 {W}%, 고르게 나뉘면 "
              f"28.6%), 가장 적은 요일은 {lo}({q}%){josa(lo, '이다/다')}.")
    return Card("week", "요일", title, explain, sowhat, grade, i, phrase=grade, report=report,
                vals={"W": W, "three": "·".join(w[0] for w in three), "s3": s3, "hi": hi, "lo": lo})


def card_time(i: int, o: StepOutcome, hours_label: dict[str, str]) -> Card | None:
    t = o.result.table
    if t is None or not len(t) or "time" not in t.columns:
        return None
    a = o.result.facts.get("applied", {})
    peak = a.get("가장 많은 시점", "")
    ph, x = a.get("1시간당 가장 바쁜 시점"), a.get("1시간당 1위/2위 배율")

    def lab(k):
        return f"{k}({hours_label[k]})" if hours_label.get(k) else k

    if ph and "1시간당 비중(%)" in t:
        order = t.sort_values("1시간당 비중(%)", ascending=False)
        grade = f"{ph} 집중형" if x and x >= HOUR_FOCUS else "·".join(order["time"].head(2)) + " 고른형"
        if "·" in peak:
            title = f"{peak.replace('·', '과 ', 1)}이 {a.get('최고 시점 비중(%)')}% 안팎으로 비슷하지만, 1시간당으로는 {lab(ph)}이 가장 바쁩니다"
        elif ph != peak:
            title = f"매출은 {peak}에 가장 많지만({a.get('최고 시점 비중(%)')}%), 1시간당으로는 {lab(ph)}이 가장 바쁩니다"
        else:
            title = f"{lab(peak)}에 매출이 가장 몰립니다({a.get('최고 시점 비중(%)')}%)"
        top2 = t.sort_values("비중(%)", ascending=False).head(2)
        explain = ", ".join(f"{r['time']}은 {int(r['시간'])}시간에 {r['비중(%)']}%(1시간당 {r['1시간당 비중(%)']:.1f}%)"
                            for _, r in top2.iterrows()) + "입니다."
        low = order.iloc[-1]
        explain += f" {low['time']}은 {int(low['시간'])}시간 동안 {low['비중(%)']}%뿐입니다."
        sowhat = (f"1시간당 가장 바쁜 {ph}에 일손을 가장 많이 두고, 1시간당 비중이 가장 낮은 {low['time']} "
                  "영업은 줄이는 것을 검토해 보세요.")
    else:
        grade = f"{peak} 많음"
        title = f"{peak}에 매출이 가장 몰립니다({a.get('최고 시점 비중(%)')}%)"
        explain, sowhat = "", f"{peak} 시간대에 일손을 모으세요."
    rep_ = (f"시간대별 카드 매출은 시간대 길이를 감안하면 {lab(ph)}이 1시간당 {round(a.get('1시간당 비중(%)') or 0, 1)}%로 가장 높다."
            if ph else f"시간대별 카드 매출은 {peak}에 가장 많다.")
    return Card("time", "시간대", title, explain, sowhat, grade, i, phrase=grade, report=rep_,
                vals={"busy": lab(ph or peak) if ph or peak else "", "peak": peak, "ph": ph or peak,
                      "focus": bool(x and x >= HOUR_FOCUS)})


def card_stores(i: int, o: StepOutcome, plan: Plan, loc: Card | None, ym: str, pop=None) -> Card | None:
    """경쟁(가게 수) — 공개 상가정보(실제). 센터 매출 몫(loc)이 있으면 가게 하나당 매출 지수까지."""
    t = o.result.table
    a = o.result.facts.get("applied", {})
    if t is None or not len(t):
        return None
    biz = _short_biz(plan.slots.business, plan.slots.biz_label) or "같은 업종"
    n, total, avg = a.get("지역 수", len(t)), a.get("제주 전체 가게 수", 0), a.get("동네 평균 가게 수")
    cnts = a.get("관심 지역 가게 수", {})
    ranks = a.get("관심 지역 순위", {})
    top3 = ", ".join(f"{k}({v}곳)" for k, v in zip(t["bjd"].head(3), t["가게 수"].head(3)))
    src = f"소상공인 상가정보 {ym}" if ym else "소상공인 상가정보"
    eyebrow = f"경쟁 · 같은 업종 가게 수 · 실제 공개 데이터({src})"
    if not plan.slots.regions:
        where = "·".join(plan.slots.city) or "제주"
        title = f"{where}에서 {biz} 가게가 가장 많은 동네는 {t['bjd'].iloc[0]}({t['가게 수'].iloc[0]}곳)입니다"
        explain = f"{where} 전체 {biz}는 {total:,}곳이고, 많은 곳은 {top3} 순입니다."
        return Card("stores", eyebrow, title, explain, "후보 동네를 정해 같은 질문으로 가게 수와 매출을 함께 비교해 보세요.",
                    f"1위 {t['bjd'].iloc[0]}", i, public=True, report=f"{biz} 가게가 많은 읍면동은 {top3} 순이다({src}).",
                    vals={"N": n, "total": total})
    name = _short_region(plan.slots.regions) if len(plan.slots.regions) > 1 else plan.slots.regions[0]
    cnt = int(sum(cnts.values()))
    if not ranks:                       # 그 동네에 등록된 가게가 없다
        title = f"{name}에는 등록된 {biz} 가게가 없습니다({src})"
        return Card("stores", eyebrow, title, f"제주 전체 {biz}는 {total:,}곳이고, 많은 곳은 {top3} 순입니다.",
                    "경쟁 가게는 없지만 수요(손님)가 있는지 센터 매출 데이터로 꼭 함께 확인하세요.", "가게가 적은 동네", i,
                    public=True, vals={"name": name, "cnt": 0, "N": n, "total": total})
    r = min(v[0] for v in ranks.values())
    share = round(sum(v[1] for v in ranks.values()), 1)
    grade = ("가게가 손꼽히게 많은 동네" if r <= 3 else "가게가 많은 동네" if r <= 10 else
             "가게 수 중간" if r <= n / 2 else "가게가 적은 동네")
    title = (f"{name}에는 {biz}{josa(biz, '이/가')} {cnt}곳 — 제주 {n}개 동네 중 "
             + ("가장 많습니다" if r == 1 else f"{r}번째로 많습니다" if r <= n / 2 else f"{r}번째로, 적은 편입니다"))
    explain = f"제주 전체 {biz} {total:,}곳의 {share}%가 {name}에 있습니다(동네 평균 {avg}곳). 많은 곳은 {top3} 순입니다."
    per, per_all = None, None
    if pop is not None and len(pop.df):                 # 행정안전부 주민등록 인구(실제): 도민 1,000명당 가게 수
        p_ = pop.df[pop.df["bjd"].isin(plan.slots.regions)]["pop"].sum()
        if p_:
            per = round(cnt / p_ * 1000, 1)
            per_all = round(total / pop.df["pop"].sum() * 1000, 1)
            explain += (f" 주민등록 인구로 나누면 도민 1,000명당 {per}곳으로 제주 평균({per_all}곳)의 "
                        f"{round(per / per_all, 1)}배입니다.")
    E = None
    if loc is not None and loc.vals.get("S"):
        E = round(loc.vals["S"] / share, 2) if share else None
    if E is not None:
        eg = ("가게 수에 비해 손님 넉넉" if E >= PER_STORE_HIGH else "평균 수준" if E >= PER_STORE_LOW
              else "가게가 많은 편(경쟁 셈)")
        explain += (f" 매출 몫({loc.vals['S']}%)을 가게 몫({share}%)으로 나누면 {E} — 가게 하나당 매출이 제주 평균의 "
                    f"약 {E}배입니다" + (" (매출 몫은 가상 데이터)" if loc.synthetic else "") + ".")
        grade = f"{grade} · {eg}"
        if E < PER_STORE_LOW:
            sowhat = (f"가게 수에 비해 매출이 작은 동네입니다. 손님을 나눠 갖는 {biz}{josa(biz, '이/가')} 많으니, 가까운 "
                      "가게와 다르게 보일 점(메뉴·좌석·영업시간)을 먼저 정하세요.")
        elif E >= PER_STORE_HIGH:
            sowhat = "가게 수에 비해 매출이 큰 동네입니다. 자리를 잡으면 손님을 모으기 좋은 편이니 임대료와 함께 비교해 보세요."
        else:
            sowhat = "가게 수와 매출이 평균 비율입니다. 입지(거리·주차)와 메뉴로 다르게 보일 점을 정해 두세요."
    elif r <= 10:
        sowhat = (f"같은 동네에 {biz}{josa(biz, '이/가')} {cnt}곳 있어 경쟁이 셀 수 있습니다. 가까운 가게와 다르게 보일 "
                  "점(메뉴·좌석·영업시간)을 사업계획서에 적어 두세요.")
    else:
        sowhat = "같은 업종 가게가 적은 동네입니다. 손님이 충분한지 센터 매출 데이터로 함께 확인하세요."
    report = (f"소상공인시장진흥공단 상가(상권)정보({ym or '최근'} 기준)에 따르면 {name}의 {biz}{josa(biz, '은/는')} {cnt}곳으로 "
              f"제주 {n}개 법정동 가운데 {r}위(제주 전체의 {share}%)다.")
    rk = ""
    if len(ranks) > 1:                  # 합계 가게 수에 한 동네 순위를 붙이지 않는다 → 동네마다 따로
        rk = "·".join(f"{k} {cnts.get(k, 0)}곳({v[0]}위)" for k, v in sorted(ranks.items(), key=lambda kv: kv[1][0]))
        title = f"{name}의 {biz}{josa(biz, '은/는')} 모두 {cnt}곳 — {rk}"
        report = (f"소상공인시장진흥공단 상가(상권)정보({ym or '최근'} 기준)에 따르면 {name}의 {biz}{josa(biz, '은/는')} 모두 "
                  f"{cnt}곳(제주 전체의 {share}%)이고, 제주 {n}개 법정동 가운데 {rk}다.")
    return Card("stores", eyebrow, title, explain, sowhat, grade, i, public=True, phrase=grade, report=report,
                extra=["가게 수는 사업자 등록 기준이라 아주 작은 가게나 최근 문을 닫은 가게가 섞여 있을 수 있습니다."],
                vals={"name": name, "cnt": cnt, "r": r, "N": n, "share": share, "total": total, "E": E,
                      "per1000": per, "per1000_all": per_all, "rk": rk})


def card_visitors(trend_o: tuple[int, StepOutcome] | None, week_o: tuple[int, StepOutcome] | None,
                  plan: Plan, period: str) -> Card | None:
    """최근 방문객 흐름 — 한국관광공사 지역별 방문자 수(이동통신 기반, 실제 공개 데이터)."""
    if not trend_o:
        return None
    i, o = trend_o
    a = o.result.facts.get("applied", {})
    hi, lo, R = a.get("가장 높은 기간"), a.get("가장 낮은 기간"), a.get("최고/최저 배율")
    idx = a.get("월 지수", {})
    if not hi or not lo or not R or len(idx) < 12:
        return None
    cities = (o.step.params.get("filters") or {}).get("sigungu") or ["제주"]
    city = "·".join(cities)
    H, L = (f"{x[2:4]}년 {int(x[4:6])}월" for x in (hi, lo))      # 1년이 두 해에 걸쳐 있어 연도를 붙인다
    grade = "계절 영향 큼" if R >= SEASON_BIG else "계절 영향 있음" if R >= SEASON_SOME else "사계절 고른 편"
    title = f"최근 1년 {city} 외지인 방문자는 {H}이 가장 많고 {L}이 가장 적습니다({round(R, 2)}배)"
    explain = f"평소 달을 100으로 보면 {H} {round(idx[hi])}, {L} {round(idx[lo])}입니다."
    W = None
    if week_o:
        t = week_o[1].result.table
        col = [c for c in t.columns if "비중" in c]
        if col:
            sh = dict(zip(t.iloc[:, 0], t[col[0]]))
            W = round(float(sh.get("토요일", 0) + sh.get("일요일", 0)), 1)
            explain += f" 요일로는 토·일 이틀에 {W}%가 몰립니다(고르게 나뉘면 28.6%)."
    explain += " 이동통신 자료로 추정한 방문자 수라 매출과는 다릅니다."
    if R < SEASON_SOME:
        sowhat = "최근 방문객 수는 계절 차이가 크지 않습니다. 매출의 계절 차이는 센터 카드 데이터로 확인하세요."
    else:
        sowhat = f"방문객이 적은 {L} 전후를 비수기로 잡고, 인력·재고 계획을 세워 두세요."
    week_g = ("주말형" if W is not None and W >= WEEKEND_TYPE else "평일형" if W is not None and W <= WEEKDAY_TYPE
              else "요일 고른 편")
    report = (f"한국관광공사 지역별 방문자 수({period})에 따르면 {city} 외지인 방문자는 {H}이 가장 많고 {L}이 가장 적어 "
              f"최고 달이 최저 달의 {round(R, 2)}배다" + (f"(토·일 비중 {W}%)." if W is not None else "."))
    return Card("visitors", f"최근 방문객 흐름 · 실제 공개 데이터(한국관광공사 {period})", title, explain, sowhat,
                f"{grade} · {week_g}", i, public=True, report=report,
                vals={"R": R, "hi": H, "lo": L, "W": W, "city": city})


SLOT_ORDER_PUB = ["오전", "점심", "오후", "저녁", "밤"]


def card_district(i: int, o: StepOutcome, plan: Plan) -> Card | None:
    """지구 유형별 요일·시간대·손님 구성 — 제주데이터허브 '관광지 및 상업지구' 카드 데이터(실제, 2016.09~2017.11)."""
    a = o.result.facts.get("applied", {})
    per = a.get("기간", "")
    period = f"{per[:4]}.{per[4:6]}~{per[7:11]}.{per[11:13]}" if len(per) == 13 else per
    rows = {k: v for k, v in a.items() if isinstance(v, dict)}
    if not rows:
        return None

    def lead(v):
        s = {k: v.get(f"{k} 비중(%)") or 0 for k in SLOT_ORDER_PUB}
        k = max(s, key=s.get)
        return k, s[k]
    eyebrow = f"지구 유형 비교 · 실제 공개 데이터(제주데이터허브 {period})"
    eve = max(rows, key=lambda d: rows[d].get("저녁 비중(%)") or 0)
    focus = a.get("관심 지구")
    if not focus or focus not in rows:
        day = [d for d in rows if lead(rows[d])[0] in ("점심", "오후")]
        title = ("지구 유형마다 장사 시간이 다릅니다 — " + ("·".join(day) + "는 낮, " if day else "")
                 + f"{eve}{josa(eve, '은/는')} 저녁({rows[eve].get('저녁 비중(%)')}%)")
        return Card("district", eyebrow, title, "내국인 관광객 카드 매출을 지구 유형 5종으로 나눠 본 실제 값입니다.",
                    "후보 동네를 정하면 가장 가까운 지구 유형과 비교해 보여 드립니다.", "지구 유형 비교", i, public=True,
                    vals={"focus": None})
    v = rows[focus]
    k, p = lead(v)
    W = v.get("토·일 비중(%)")
    week_g = "주말형" if W is not None and W >= WEEKEND_TYPE else "평일형" if W is not None and W <= WEEKDAY_TYPE \
        else "요일 고른 편"
    place = _short_region(plan.slots.regions) or "·".join(plan.slots.city) or "이 동네"
    slots = " > ".join(f"{s}({v.get(f'{s} 비중(%)')}%)" for s in sorted(SLOT_ORDER_PUB,
                                                                      key=lambda s: -(v.get(f"{s} 비중(%)") or 0)))
    title = f"'{focus}' 지구는 {k}에 가장 많이 쓰고({p}%), 토·일 몫은 {W}%입니다"
    explain = (f"{place}{josa(place, '은/는')} 원자료에 지구 구분이 없어 가장 가까운 유형('{focus}')으로 봤습니다(추정). "
               f"이 유형의 내국인 관광객 카드 매출은 {slots} 순이고, 토·일 몫은 {W}%(고르게 나뉘면 28.6%)입니다. "
               f"손님 돈은 내국인 관광객 {v.get('내국인관광객 비중(%)')}%, 도민 {v.get('제주도민 비중(%)')}%, "
               f"법인 {v.get('법인 비중(%)')}%, 중국인 관광객 {v.get('중국인관광객 비중(%)')}%입니다.")
    if eve != focus:
        explain += f" 같은 자료에서 {eve}{josa(eve, '은/는')} 저녁 몫이 {rows[eve].get('저녁 비중(%)')}%로 '저녁 장사'입니다."
    if k in ("점심", "오후", "오전"):
        sowhat = ("낮 장사 유형입니다. 저녁 영업을 길게 잡기보다 점심·오후에 일손을 모으는 계획이 맞는지, 센터 시간대 데이터"
                  "(동 × 업종)로 내 동네도 같은지 확인하세요.")
    else:
        sowhat = "저녁 장사 유형입니다. 저녁 시간대 인력과 메뉴를 먼저 정하고, 센터 시간대 데이터로 내 동네·업종도 같은지 확인하세요."
    report = (f"제주데이터허브 '관광지 및 상업지구' 카드 데이터({period})에 따르면 {focus}의 내국인 관광객 카드 매출은 "
              f"{k}({p}%) 비중이 가장 크고 토·일 비중은 {W}%다.")
    return Card("district", eyebrow + " · 가장 가까운 유형(추정)", title, explain, sowhat, f"{week_g} · {k} 중심", i,
                public=True, report=report, extra=["요일·시간대는 내국인 관광객 카드 매출 기준입니다(도민 자료 없음)."],
                vals={"focus": focus, "W": W, "lead": k, "lead_p": p})


def card_public(outs: list[tuple[int, StepOutcome]], center_d: float | None, demo: bool) -> Card | None:
    by = {o.step.tool: (i, o) for i, o in outs}
    if "compare_share" not in by:
        return None
    i, o = by["compare_share"]
    a = o.result.facts.get("applied", {})
    P, B, d = a.get("관심 대상 비중(%)"), a.get("비교 기준 비중(%)"), a.get("차이(%p)")
    if P is None or P != P:
        return None
    fl = o.step.params.get("focus_label", "")
    period = "2016~2018"
    if demo or center_d is None or d is None:
        title = f"공개 데이터(실제 값): {fl} 매출의 {P}%가 내국인 관광객입니다({period})"
        grade = "실제 공개 데이터"
    elif (center_d >= 3 and d >= 3) or (center_d <= -3 and d <= -3):
        title = f"공개 데이터로도 같은 방향입니다 — {fl} 매출의 {P}%가 내국인 관광객({period})"
        grade = "공개 데이터와 같은 방향"
    elif center_d * d < 0 and abs(center_d) >= 3 and abs(d) >= 3:
        title = "공개 데이터는 다른 방향입니다 — 기간(2016~2018 vs 최근)과 단위(시 vs 동) 차이를 확인하세요"
        grade = "공개 데이터와 다른 방향"
    else:
        title = f"공개 데이터로는 뚜렷하지 않습니다 — {fl} 매출의 {P}%가 내국인 관광객({period})"
        grade = "공개 데이터로는 뚜렷하지 않음"
    fl = fl or "제주 전체"
    explain = (f"제주 전체({B}%)보다 {abs(d)}%포인트 {'높' if d > 0 else '낮'}습니다." if d is not None and abs(d) >= 0.05
               else "")
    grp = by.get("group_share")
    if grp:
        g = {k.replace(" 비중(%)", ""): v for k, v in grp[1].result.facts["applied"].items() if k != "전체 비중(%)"}
        if g:
            low_name = min(g, key=g.get)
            if d is not None and d > 0 and not fl.startswith(low_name):
                explain += f" 다만 도민 위주인 {low_name}({g[low_name]}%)이 평균을 낮춘 영향이 큽니다."
            similar = [(k, v) for k, v in g.items() if not fl.startswith(k) and abs(v - P) < 3]
            if similar:
                explain += (f" {similar[0][0]}({similar[0][1]}%)과 비슷해서, 이 지역만의 특징이라기보다 "
                            "같은 유형 지역의 공통점으로 보입니다.")
    extra = []
    sb = by.get("season_by")
    if sb:
        sf = sb[1].result.facts["applied"]
        t_, l_ = sf.get("내국인관광객 최고/최저 배율"), sf.get("제주도민 최고/최저 배율")
        if t_ and l_:
            extra.append(f"같은 자료에서 관광객 매출은 가장 많은 달이 가장 적은 달의 {t_}배, 도민 매출은 {l_}배로, "
                         "관광객 비중이 높을수록 계절을 더 탑니다.")
    age = by.get("share_by")
    if age:
        top = [(k.replace(" 비중(%)", ""), v) for k, v in list(age[1].result.facts["applied"].items())[:2]]
        if top:
            extra.append("내국인 관광객 손님은 " + "·".join(f"{k}({v}%)" for k, v in top) + "가 많습니다.")
    explain += (" 공개 데이터는 시·도심/읍면·업종 8종까지만 나뉘어 동네·세부 업종은 따로 볼 수 없습니다. "
                "그래서 센터 데이터가 필요합니다.")
    extra.append("숫자가 다른 이유: 범위(시 읍면 식음료 vs 동네 업종), 기간(2016~2018 vs 최근 12개월), 관광객 정의"
                 "(내국인만 vs 개별+단체)가 달라 센터 숫자와 서로 빼거나 직접 비교하면 안 됩니다.")
    sowhat = ("사업계획서에 누구나 확인할 수 있는 공개 데이터(제주데이터허브 597)와 동네 단위 센터 데이터를 함께 "
              "인용하면 근거가 단단해집니다.")
    return Card("public", f"공개 데이터로 확인 · 제주데이터허브 597 · {period}", title, explain, sowhat, grade,
                grp[0] if grp else i, public=True, extra=extra)


# ── 종합 ─────────────────────────────────────────────────────────────
def _hours_label() -> dict[str, str]:
    try:
        from .synth import get_table, load_catalog, ref_rows
        return {r[0]: r[1] for r in ref_rows(get_table(load_catalog(), "1-14"), "시간대") if len(r) > 1}
    except Exception:  # noqa: BLE001
        return {}


def build_answer(plan: Plan, outs: list[StepOutcome], loaded: dict) -> Answer:
    purpose = _purpose(plan)
    neutral = purpose in NEUTRAL_PURPOSES
    done = [(i, o) for i, o in enumerate(outs) if o.result is not None]
    center = [(i, o) for i, o in done if not o.step.table_id.startswith(("허브-", "공개-"))]
    public = [(i, o) for i, o in done if o.step.table_id.startswith("허브-")]
    shops = [(i, o) for i, o in done if o.step.tool == "store_rank"]
    visits = [(i, o) for i, o in done if o.step.table_id == "공개-방문자"]
    dists = [(i, o) for i, o in done if o.step.tool == "district_profile"]
    use = center or public
    synthetic = any(_flags(o, loaded)[0] for _, o in use)
    hl = _hours_label()

    cards: list[Card] = []
    for i, o in use:
        tool, cat_col = o.step.tool, o.step.params.get("cat_col")
        c = None
        if tool == "compare_share":
            c = card_customers(i, o, plan, purpose)
        elif tool == "trend":
            c = card_season(i, o, purpose)
        elif tool == "top_n":
            c = card_location(i, o, plan, has_stores=bool(shops))
        elif tool == "pattern" and cat_col == "week":
            c = card_week(i, o, " ".join(plan.slots.business or []) + " " + (plan.slots.biz_label or ""))
        elif tool == "pattern" and cat_col == "time":
            c = card_time(i, o, hl)
        elif tool == "region_compare":
            c = card_regions(i, o, plan)
        if c and not any(x.key == c.key for x in cards):
            c.synthetic, c.public = _flags(o, loaded)
            if not c.public and o.badge and o.badge.center_only:
                c.eyebrow += " · 센터에서만 나오는 수치"
            cards.append(c)

    want = [{"rank": "location", "weekday": "week", "timeslot": "time", "trend": "season", "share": "customers",
             "compare": "regions"}[v]
            for v in plan.slots.views if v in ("rank", "weekday", "timeslot", "trend", "share", "compare")]
    if any(c.key == "regions" for c in cards) and "regions" in want:   # 비교 질문이면 비교 카드가 맨 앞
        want.remove("regions")
        want.insert(0, "regions")
    if shops:
        from .report import period_of
        i_s, o_s = shops[0]
        lt_s = loaded.get(o_s.step.table_id)
        cs = card_stores(i_s, o_s, plan, next((c for c in cards if c.key == "location"), None),
                         period_of(lt_s).replace(" 기준", "") if lt_s is not None else "", loaded.get("공개-인구"))
        if cs:
            cards.append(cs)
    if visits:
        from .report import period_of
        lt_v = loaded.get("공개-방문자")
        cv = card_visitors(next(((i, o) for i, o in visits if o.step.tool == "trend"), None),
                           next(((i, o) for i, o in visits if o.step.tool == "pattern"), None), plan,
                           period_of(lt_v) if lt_v is not None else "")
        if cv:
            cards.append(cv)
    if dists:
        cdist = card_district(dists[0][0], dists[0][1], plan)
        if cdist:
            cards.append(cdist)
    default = ["regions", "customers", "season", "week", "time", "location", "stores", "visitors", "district"]
    cards.sort(key=lambda c: (want.index(c.key) if c.key in want else len(want),
                              default.index(c.key) if c.key in default else 9))
    by = {c.key: c for c in cards}

    center_d = next((o.result.facts.get("applied", {}).get("차이(%p)") for _, o in center
                     if o.step.tool == "compare_share"), None)
    pub_card = card_public(public, center_d, synthetic or not center) if public else None

    focus = plan.focus_label or "관심 대상"
    place = bool(plan.slots.regions or plan.slots.city)
    if not place and focus != "관심 대상" and not focus.startswith("제주"):
        focus = "제주 " + focus
    if not center and public and pub_card:      # 공개 데이터만 있을 때: 공개 카드 기준 이름
        focus = next((o.step.params.get("focus_label") for _, o in public if o.step.params.get("focus_label")), focus)
    headline = _headline(plan, by, want, focus, neutral, cards)
    # 물은 동네·업종 조합의 카드 결제가 데이터에 아예 없으면(드문 업종·작은 동네) 다른 결론으로 넘어가지 말고 그렇다고 말한다
    cs = next((o for _, o in center if o.step.tool == "compare_share"), None)
    no_focus = bool(plan.slots.regions and plan.slots.business and cs is not None
                    and cs.result.facts.get("simple", {}).get("관심 대상 행 수") == 0)
    if no_focus:
        headline = (f"{focus}{josa(focus, '은/는')} 이 데이터에 카드 결제 기록이 없어 손님 구성·계절·요일·시간대를 "
                    "판정하지 못했습니다.")
    if synthetic and cards:
        headline = "[체험] " + headline

    if not is_food(plan):                        # 숙박·소매·렌터카 등: 음식점 말투(메뉴) 대신 상품
        for c in cards:
            c.sowhat, c.explain = unfood(c.sowhat), unfood(c.explain)
    kpis = _kpis(plan, by, use)
    order = ["regions", "season", "week", "customers", "time", "location"]
    actions = []
    if not neutral:
        for k in order:
            c = by.get(k)
            if not c or c.hold or c.grade == "사계절 고른 편":
                continue
            if "일손" in c.sowhat and any("일손" in a for a in actions):     # 같은 동작은 한 번만
                continue
            actions.append(c.sowhat)
        actions = actions[:3]
    core = "" if neutral else _core(by, want)
    if core:
        actions = [x for x in actions if x != core][:3]          # 핵심 줄과 같은 말은 할 일에서 뺀다
    market = _market(by, plan)
    badges = [(by[k].grade, "blue") for k in ("week", "time") if k in by and (want[:1] != [k])]
    if "stores" in by and plan.slots.regions and by["stores"].vals.get("cnt") is not None:
        badges.append((f"경쟁: {by['stores'].grade}", "gray"))
    elif "location" in by and plan.slots.regions:
        badges.append(("경쟁 강도: 판정 안 함(가게 수 데이터 없음)", "gray"))

    checks = sum(1 for _, o in done for c in o.result.checks if c.startswith(("검산", "기간 확인", "중복 방지")))
    n_center = len({o.step.table_id for _, o in center})
    trust = []
    if n_center:
        trust.append(f"센터 카드 데이터 {n_center}종" + ("(가상)" if synthetic else ""))
    if public:
        trust.append("공개 데이터 597로 교차 확인")
    if "stores" in by:
        trust.append("가게 수는 상가정보 실제 값")
    if "visitors" in by:
        trust.append("최근 방문객은 관광공사 실제 값")
    if "district" in by:
        trust.append("지구 유형 요일·시간대는 데이터허브 실제 값")
    trust += [f"자동 검산 {checks}건 통과", "반출 기준(비중·지수·순위) 충족", "판정은 공개 규칙, AI는 문장만"]

    caveats = ["비씨카드 결제만 집계했습니다(현금·다른 카드사 제외). 비율·순위로 보는 것이 안전합니다."]
    if "location" in by and plan.slots.regions and "stores" not in by:
        caveats.append("가게 수가 없어 경쟁 강도는 판정하지 않았습니다. 외식업 POS(1-19)나 소상공인365 업소 수로 "
                       "확인할 수 있습니다.")
    if synthetic:
        caveats.insert(0, "체험 모드: 센터 카드 데이터 자리에 가상 데이터를 넣었습니다. 센터 수치는 예시이고, "
                          "「경쟁(가게 수)」「최근 방문객 흐름」「지구 유형 비교」「공개 데이터로 확인」만 실제 값입니다.")
    if no_focus:
        caveats.insert(1 if synthetic else 0,
                       f"질문한 동네·업종({focus})의 카드 결제가 이 데이터에 없습니다. 가게가 아주 적거나 다른 업종으로 "
                       "등록됐을 수 있습니다. 이웃 동네나 더 넓은 업종으로 다시 물어보세요.")
    if not center and public:
        caveats.insert(0, "공개 데이터(2016~2018년, 제주시·서귀포시 단위)로 본 결론이라 동네별 차이와 최근 변화는 "
                          "반영되지 않았습니다.")

    from .report import period_of, source_line
    basis = [source_line(loaded[t]) for t in dict.fromkeys(o.step.table_id for _, o in done) if t in loaded]
    period = next((period_of(loaded[o.step.table_id]) for _, o in use if o.step.table_id in loaded), "")
    qline = f"질문: {plan.slots.question} · {purpose}" + (f" · {period}" if period else "")
    ans = Answer(headline, qline, kpis, actions, core, market, badges, cards, pub_card, caveats[:4], basis, trust,
                 neutral, synthetic=synthetic)
    if neutral:
        ans.report_sentences = _report_sentences(by, period)
        ans.citation = "; ".join(b.replace("자료: ", "") for b in basis)
    return ans


# 결론 문장 조립표: 축 등급 → (-고, -며, 관형)
AXIS_FORMS = {
    "뚜렷한 관광객 장사": ("관광객이 대부분이고", "관광객이 대부분이며", "관광객이 대부분인"),
    "관광객 장사": ("관광객이 더 많고", "관광객이 더 많으며", "관광객이 더 많은"),
    "관광객·도민 반반": ("관광객과 도민이 반반이고", "관광객과 도민이 반반이며", "관광객과 도민이 반반인"),
    "도민 단골 장사": ("도민이 더 많고", "도민이 더 많으며", "도민이 더 많은"),
    "뚜렷한 도민 단골 장사": ("도민이 대부분이고", "도민이 대부분이며", "도민이 대부분인"),
    "계절 영향 큼": ("계절을 많이 타고", "계절을 많이 타며", "계절을 많이 타는"),
    "계절 영향 있음": ("계절을 조금 타고", "계절을 조금 타며", "계절을 조금 타는"),
    "사계절 고른 편": ("사계절 고르고", "사계절 고르며", "사계절 고른"),
}


def _axis_forms(key: str, by: dict) -> tuple[str, str, str] | None:
    if key == "customers":
        c = by.get("customers")
        if not c or c.hold:
            return None
        if c.grade in AXIS_FORMS:
            f = AXIS_FORMS[c.grade]
            if c.vals.get("near") and "더 많" in f[0]:           # 경계 근처는 단정하지 않는다
                f = tuple(x.replace("더 많고", "더 많은 편이고").replace("더 많으며", "더 많은 편이며")
                          .replace("더 많은", "더 많은 편인") if i == 2 else
                          x.replace("더 많고", "더 많은 편이고").replace("더 많으며", "더 많은 편이며")
                          for i, x in enumerate(f))
            return f
        lab = c.grade                                            # 외국인 등: '외국인 평균의 1.5배'
        return (f"{lab}이고", f"{lab}이며", f"{lab}인")
    if key == "season":
        c = by.get("season")
        return AXIS_FORMS.get(c.grade) if c and not c.hold else None
    if key == "weektime":
        w, t = by.get("week"), by.get("time")
        xs = []
        if w and w.grade in ("주말형", "평일형"):
            xs.append("주말" if w.grade == "주말형" else "평일")
        if t and t.vals.get("focus") and t.vals.get("ph"):
            xs.append(t.vals["ph"])
        if not xs:
            return None
        x = "·".join(xs)
        return (f"{x}에 몰리고", f"{x}에 몰리며", f"{x}에 몰리는")
    return None


def _headline(plan, by, want, focus, neutral, cards) -> str:
    if not cards:
        return "분석할 수 있는 결과가 부족합니다. 데이터를 더 준비해 주세요."
    if want[:1] == ["regions"] and "regions" in by:
        return (by["regions"].report if neutral and by["regions"].report else by["regions"].title + ".")
    tj = josa(focus, "은/는")
    c = by.get("customers")
    c = c if c and not c.hold else None
    if neutral:
        if (want[:1] == ["location"] or not c) and "location" in by:
            return by["location"].title + "."
        if c and c.report:
            return c.report
        return cards[0].title + "."
    if want[:1] == ["location"] and "location" in by and not plan.slots.regions:
        return by["location"].title + "."
    axis_of = {"customers": "customers", "season": "season", "week": "weektime", "time": "weektime"}
    order = []
    for k in [axis_of.get(w) for w in want] + ["customers", "season", "weektime"]:
        if k and k not in order:
            order.append(k)
    axes = [f for f in (_axis_forms(k, by) for k in order) if f][:3]
    if not axes:
        return cards[0].title + "."
    if len(axes) == 3:
        body = f"{axes[0][0]}, {axes[1][1]}, {axes[2][2]}"
    elif len(axes) == 2:
        body = f"{axes[0][0]} {axes[1][2]}"
    else:
        body = axes[0][2]
    return f"{focus}{tj} {body} 장사입니다."


def _market(by: dict, plan: Plan) -> str:
    loc = by.get("location")
    s = by.get("stores")
    if (not loc or "r" not in loc.vals) and s and s.vals.get("cnt"):
        biz = _short_biz(plan.slots.business, plan.slots.biz_label) or "같은 업종"
        many = (f"동네별로는 {s.vals['rk']}입니다" if s.vals.get("rk") else
                "제주에서 가장 많습니다" if s.vals["r"] == 1 else f"제주 {s.vals['r']}위입니다")
        return (f"{s.vals['name']}에는 {biz}{josa(biz, '이/가')} {s.vals['cnt']}곳으로 {many}"
                "(상가정보 실제 값). 동네 매출은 센터 데이터에서 볼 수 있습니다.")
    if not loc or "r" not in loc.vals:
        return ""
    biz = _short_biz(plan.slots.business, plan.slots.biz_label) or "같은 업종"
    r, n = loc.vals["r"], loc.vals["N"]
    s = by.get("stores")
    if loc.vals.get("rk"):                     # 여러 동네: 동네마다 따로 매긴 순위
        tail = f" {biz} 가게는 모두 {s.vals['cnt']}곳입니다." if s and s.vals.get("cnt") else ""
        return f"제주 {biz} 매출 순위는 {loc.vals['rk']}({n}곳 중)입니다." + tail
    if s and s.vals.get("cnt"):
        rs = s.vals["r"]
        many = "제주에서 가장 많습니다" if rs == 1 else f"제주 {rs}위입니다"
        return f"제주 {biz} 매출 {r}위({n}곳 중) 동네이고, {biz} 가게도 {s.vals['cnt']}곳으로 {many}."
    if r <= 10:
        return f"제주 {biz} 매출 {r}위({n}곳 중) 동네라 손님은 많은 편이지만, 가게 수(경쟁)는 이 데이터로 알 수 없습니다."
    return f"제주 {biz} 매출 {r}위({n}곳 중) 동네입니다."


def _core(by: dict, want: list[str] | None = None) -> str:
    s, c, loc, w, t = (by.get(k) for k in ("season", "customers", "location", "week", "time"))
    rg = by.get("regions")
    if want and want[0] == "regions" and rg and not rg.hold and rg.sowhat:     # '어디가 나아?'에 바로 답
        return rg.sowhat
    if want and want[0] == "season" and s and not s.hold and s.vals.get("idx_hi"):     # '비수기엔 얼마나 빠져?'에 바로 답
        v = s.vals
        return (f"성수기는 {v['hi']}, 비수기는 {v['lo']} — 비수기 매출은 성수기의 "
                f"{round(v['idx_lo'] / v['idx_hi'] * 100)}% 수준입니다.")
    if want and want[0] in ("week", "time") and (w or t):
        parts = [x for x in ((w.vals.get("three") if w else ""), (t.vals.get("ph") if t else "")) if x]
        return f"핵심은 {' '.join(parts)} 일손 배치입니다."
    if s and s.grade == "계절 영향 큼":
        return "핵심은 비수기 버티기입니다."
    if c and "관광객 장사" in c.grade:
        return "핵심은 도민 단골로 비수기를 보완하는 것입니다."
    if c and "도민 단골" in c.grade:
        return "핵심은 단골 유지입니다(관광객은 추가 기회)."
    st_ = by.get("stores")
    if st_ and st_.vals.get("E") is not None and st_.vals["E"] < PER_STORE_LOW:
        return "핵심은 많은 경쟁 가게 사이에서 다르게 보이는 것입니다."
    if loc and "큰 시장" in loc.grade and not st_:
        return "핵심은 경쟁 가게 수 확인입니다."
    return ""


def _kpis(plan: Plan, by: dict, use) -> list[KPI]:
    out: list[KPI] = []
    biz = _short_biz(plan.slots.business, plan.slots.biz_label) or "같은 업종"
    rg = by.get("regions")
    if rg:                                           # 비교 질문: 동네마다 손님 몫과 매출 순위
        for r in rg.vals["rows"][:3]:
            out.append(KPI(f"{r['동네']} {rg.vals['who']} 몫", (f"{r['관광객 비중(%)']:.1f}%" if r['관광객 비중(%)'] < 10 else f"{round(r['관광객 비중(%)'])}%"),
                           f"{biz} 매출 {r['매출 순위']}위" + (f" · {rg.vals['N']}곳 중" if rg.vals.get("N") else ""),
                           "그 동네 같은 업종 카드 매출 중 해당 손님이 낸 몫과, 제주 동네 중 매출 순위입니다."))
        return out
    place = bool(plan.slots.regions or plan.slots.city)
    c, s, loc = by.get("customers"), by.get("season"), by.get("location")
    if c and not c.hold and "T" in c.vals:
        o = next(o for _, o in use if o.step.tool == "compare_share")
        lab = o.step.params.get("label", "관광객")
        who = _who(o.step.params)
        B = c.vals.get("B")
        base_lab = (o.step.params.get("base_label") or "제주 전체") if o.step.table_id.startswith("허브-") \
            else f"제주 {biz}"
        T = c.vals["T"]
        pct = (lambda v: f"{v:.1f}%" if v < 10 else f"{round(v)}%")     # 작은 몫은 소수 한 자리(3.3% vs 2.7%)
        out.append(KPI(f"{who} 손님 몫", pct(T),
                       f"{base_lab} 평균 {pct(B)}" if place and B is not None and B == B else "",
                       "관광객 = 개별+단체 관광객(외국인 포함). 나머지는 도민·법인 카드. 비씨카드 결제금액 기준."))
    elif c and not c.hold:
        out.append(KPI("손님", c.grade, "", c.title))
    if s and not s.hold:
        v = s.vals
        out.append(KPI("성수기 ÷ 비수기", f"{v['R']}배", f"{v['hi']} {v['idx_hi']} ↔ {v['lo']} {v['idx_lo']} (평소=100)",
                       "가장 잘 되는 달 매출을 가장 한산한 달 매출로 나눈 값입니다. 금액은 보여 주지 않습니다."))
    if loc and loc.vals.get("rk"):
        v = loc.vals
        rk = v["rk"] if v["rk"].count("·") < 2 else "·".join(v["rk"].split("·")[:2]) + " 등"
        out.append(KPI(f"{biz} 매출 몫", f"{v['S']}%", f"{rk} · {v['N']}곳 중",
                       "제주 전체 같은 업종 카드 매출 중 이 동네들에서 결제된 몫의 합과, 동네마다 따로 매긴 순위입니다."))
    elif loc and "r" in loc.vals:
        v = loc.vals
        out.append(KPI(f"{biz} 매출 순위", f"{v['r']}위", f"{v['N']}곳 중 · 몫 {v['S']}%",
                       "제주 전체 같은 업종 카드 매출 중 그 동네에서 결제된 몫의 순위입니다."))
    elif loc:
        out.append(KPI(f"{biz} 매출 1위 동네", loc.vals.get("top1", ""), f"{loc.vals.get('N', '')}개 동네 중",
                       "제주 전체 같은 업종 카드 매출 중 그 동네에서 결제된 몫이 가장 큰 곳입니다."))
    sc = by.get("stores")
    if not loc and sc and sc.vals.get("cnt") is not None and place:
        out.append(KPI(f"{biz} 가게 수", f"{sc.vals['cnt']}곳", (f"모두 · {sc.vals['N']}개 동네 중" if sc.vals.get("rk") else
                                                          f"제주 {sc.vals.get('r', '-')}위 · {sc.vals['N']}개 동네 중"),
                       "소상공인시장진흥공단 상가(상권)정보의 같은 업종 가게 수(실제 공개 데이터)."))
    w, t = by.get("week"), by.get("time")
    if len(out) < 3 and w:
        out.append(KPI("주말(토·일) 몫", f"{w.vals['W']}%", "고르게 팔리면 28.6%", w.title))
    if len(out) < 3 and t and t.vals.get("busy"):
        out.append(KPI("1시간당 가장 바쁜 때", t.vals["ph"], t.vals["busy"], t.title))
    return out[:3]


def _report_sentences(by: dict, period: str) -> list[str]:
    out = []
    for k in ("regions", "customers", "season", "location", "stores", "visitors", "district", "week", "time"):
        c = by.get(k)
        if c and not c.hold and c.report:
            out.append(c.report.replace("카드 매출 중", f"카드 매출({period}) 중", 1) if k == "customers" else c.report)
    return out
