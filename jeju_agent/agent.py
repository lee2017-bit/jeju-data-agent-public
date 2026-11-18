"""계획 실행과 해설: Plan의 각 단계를 검증된 도구로 실행하고, 결과를 쉬운 문장으로 풀어 쓴다.

키 없는 모드의 해설은 문장 틀(템플릿)로 만든다. LLM 모드에서는 같은 facts['applied']만
LLM에 넘겨 문장을 다듬게 한다(원본·단순집계 수치는 보내지 않음).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .alternatives import Badge, badge_for
from .export_policy import Kind, judge
from .korean import column_labels, fmt_month, josa
from .loader import LoadedTable
from .planner import Plan, Step
from .tools import (AnalysisResult, compare_share, district_profile, group_share, pattern, region_compare, season_by,
                    share_by, store_rank, top_n, trend)

TOOLS = {"compare_share": compare_share, "trend": trend, "top_n": top_n, "pattern": pattern, "share_by": share_by,
         "group_share": group_share, "season_by": season_by, "store_rank": store_rank,
         "district_profile": district_profile, "region_compare": region_compare}
MEASURE_KO = {"use_amt": "매출", "use_cnt": "결제 건수", "user_cnt": "이용자 수",
              "useCost": "매출", "useCount": "결제 건수", "userCount": "이용자 수",   # 597 공개 데이터 컬럼
              "tou_num": "방문자 수", "store_cnt": "가게 수"}                            # 공공데이터포털(방문자·상가)


@dataclass
class StepOutcome:
    step: Step
    result: AnalysisResult | None
    narrative: list[str] = field(default_factory=list)
    missing_data: bool = False
    export_verdict: str = ""
    error: str = ""
    badge: Badge | None = None


_fmt_month = fmt_month


def narrate(step: Step, r: AnalysisResult) -> list[str]:
    a = r.facts.get("applied", {})
    m = MEASURE_KO.get(step.params.get("measure", ""), "매출")
    out: list[str] = []
    if step.tool == "compare_share":
        label = step.params.get("label", "")
        f, b, gap = a.get("관심 대상 비중(%)"), a.get("비교 기준 비중(%)"), a.get("차이(%p)")
        if f is not None and b is not None:
            more = "높습니다" if gap > 0 else ("낮습니다" if gap < 0 else "같습니다")
            fl = step.params.get("focus_label", "관심 대상")
            bl = step.params.get("base_label", "비교 기준")
            out.append(f"{fl}의 {m} 가운데 {label} 비중은 {f}%로, {bl}({b}%)보다 {abs(gap)}%p {more}.")
            if f >= 50:
                out.append(f"매출의 절반 이상이 {label}에서 나오므로 관광 성수기·비수기 영향을 크게 받을 수 있습니다.")
    elif step.tool == "trend":
        hi, lo, ratio = a.get("가장 높은 기간"), a.get("가장 낮은 기간"), a.get("최고/최저 배율")
        if hi and lo:
            out.append(f"{m}{josa(m, '이/가')} 가장 많은 달은 {_fmt_month(hi)}, 가장 적은 달은 {_fmt_month(lo)}입니다"
                       + (f"(최고 달이 최저 달의 {ratio}배)." if ratio else "."))
        yoy = a.get("최근 달 전년 같은 달 대비(%)")
        if yoy is not None:
            out.append(f"{_fmt_month(a.get('최근 달', ''))} 매출은 1년 전 같은 달보다 {yoy:+}% 변했습니다.")
    elif step.tool == "top_n":
        ranks = [v for k, v in a.items() if k.endswith("위")][:5]
        if ranks:
            out.append("같은 업종 매출이 큰 지역은 " + ", ".join(ranks) + " 순입니다.")
    elif step.tool == "district_profile":
        f = a.get("관심 지구")
        per = a.get("기간", "")
        a = {**a, "기간": f"{per[:4]}.{per[4:6]}~{per[7:11]}.{per[11:13]}" if len(per) == 13 else per}
        if f and isinstance(a.get(f), dict):
            v = a[f]
            out.append(f"{f}: 토·일 {v.get('토·일 비중(%)')}%, 오후 {v.get('오후 비중(%)')}%·저녁 {v.get('저녁 비중(%)')}%"
                       f"(내국인 관광객 카드 매출, {a.get('기간', '')}).")
        else:
            out.append(f"지구 유형 5종의 요일·시간대·손님 구성을 비교했습니다({a.get('기간', '')}).")
    elif step.tool == "store_rank":
        t = r.table
        if len(t):
            out.append("같은 업종 가게가 많은 동네는 " + ", ".join(f"{k}({v}곳)" for k, v in zip(t.iloc[:5, 1], t["가게 수"][:5]))
                       + f" 순입니다(제주 전체 {a.get('제주 전체 가게 수', 0):,}곳).")
    elif step.tool == "pattern":
        peak, share, even = a.get("가장 많은 시점"), a.get("최고 시점 비중(%)"), a.get("고르게 나뉠 때 비중(%)")
        if peak:
            out.append(f"{m}{josa(m, '은/는')} {peak}에 가장 많습니다(전체의 {share}%, 고르게 나뉘면 {even}%).")
        ph = a.get("1시간당 가장 바쁜 시점")
        if ph and ph not in peak.split("·"):
            out.append(f"시간대 길이를 감안한 1시간당 매출은 {ph}이 가장 많습니다.")
    elif step.tool == "group_share":
        g = {k.replace(" 비중(%)", ""): v for k, v in a.items() if k != "전체 비중(%)"}
        if g:
            out.append("그룹별 비중: " + ", ".join(f"{k} {v}%" for k, v in g.items())
                       + (f" (전체 {a['전체 비중(%)']}%)." if a.get("전체 비중(%)") is not None else "."))
    elif step.tool == "season_by":
        if a:
            out.append("가장 많은 달 ÷ 가장 적은 달: " + ", ".join(f"{k.replace(' 최고/최저 배율', '')} {v}배"
                                                         for k, v in a.items()) + ".")
    elif step.tool == "share_by":
        top = list(a.items())[:3]
        if top:
            out.append("비중이 큰 순서: " + ", ".join(f"{k.replace(' 비중(%)', '')} {v}%" for k, v in top) + ".")
    return out


def run_plan(plan: Plan, loaded: dict[str, LoadedTable]) -> list[StepOutcome]:
    outs: list[StepOutcome] = []
    for st in plan.steps:
        lt = loaded.get(st.table_id)
        if lt is None or lt.table is None:
            outs.append(StepOutcome(st, None, missing_data=True, badge=badge_for(st.tool, st.table_id, st.params)))
            continue
        params = {k: v for k, v in st.params.items() if k != "label"}
        if st.tool == "compare_share":
            params["col_labels"] = column_labels(lt.table)
        try:
            r = TOOLS[st.tool](lt.df, **params)
        except KeyError as e:
            outs.append(StepOutcome(st, None, error=f"필요한 컬럼이 없습니다: {e}"))
            continue
        # 추세는 반출본을 '평소=100 지수'(응용집계)로 바꿔 내보내므로 그 형태로 판정한다
        v = judge(Kind.APPLIED_AGG if st.tool == "trend" else r.kind, [lt.table], ".png")
        outs.append(StepOutcome(st, r, narrate(st, r), export_verdict=v.verdict.value,
                                badge=badge_for(st.tool, st.table_id, st.params)))
    return outs
