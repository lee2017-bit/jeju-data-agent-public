"""검증된 분석 도구. LLM이 코드를 새로 짜지 않고 이 함수들만 조합해 쓴다.

모든 도구는 AnalysisResult를 돌려준다.
- table: 화면·보고서용 표
- kind: 반출 판정용 산출물 종류(단순집계/응용집계)
- facts: 해설 문장에 쓸 핵심 수치. 'applied'(비율·순위·증감) 와 'simple'(합계 등)을 구분한다.
  외부 LLM에는 applied만 보낸다.
- checks: 자동 검산 결과와 주의 문구
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .export_policy import Kind
from .korean import fmt_month_short, josa


@dataclass
class AnalysisResult:
    title: str
    table: pd.DataFrame
    kind: Kind
    facts: dict = field(default_factory=lambda: {"applied": {}, "simple": {}})
    checks: list[str] = field(default_factory=list)
    chart: dict = field(default_factory=dict)  # {"type": "bar"|"line", "x": col, "y": col}


def apply_filters(df: pd.DataFrame, filters: dict[str, list[str]] | None) -> pd.DataFrame:
    if not filters:
        return df
    m = pd.Series(True, index=df.index)
    for col, vals in filters.items():
        if vals:
            m &= df[col].isin(vals)
    return df[m]


def describe_filters(filters: dict[str, list[str]] | None, labels: dict[str, str] | None = None) -> str:
    if not filters:
        return "전체"
    labels = labels or {}
    return ", ".join(f"{labels.get(k, k)}={'/'.join(v)}" for k, v in filters.items() if v)


def _pct(x: float) -> float:
    return round(float(x) * 100, 1)


def share_by(df: pd.DataFrame, by: str, measure: str, filters=None, groups: dict[str, list[str]] | None = None,
             title: str | None = None) -> AnalysisResult:
    """by 값별 measure 합계와 비중(%). groups로 값을 묶을 수 있다(예: 관광객=[개별, 단체])."""
    d = apply_filters(df, filters)
    key = d[by]
    if groups:
        inv = {v: g for g, vs in groups.items() for v in vs}
        key = key.map(lambda v: inv.get(v, v))
    s = d.groupby(key, dropna=False)[measure].sum().sort_values(ascending=False)
    total = float(d[measure].sum())
    t = pd.DataFrame({by: s.index, measure: s.values})
    t["비중(%)"] = (t[measure] / total * 100).round(1) if total else np.nan
    checks = []
    if total and abs(float(s.sum()) - total) > 1e-6 * max(1.0, total):
        checks.append("검산 실패: 항목별 합계와 전체 합계가 다릅니다.")
    else:
        checks.append("검산: 항목별 합계 = 전체 합계")
    if len(d) == 0:
        checks.append("조건에 맞는 데이터가 없습니다.")
    facts = {"applied": {f"{k} 비중(%)": v for k, v in zip(t[by], t["비중(%)"])},
             "simple": {"전체 합계": total, "행 수": int(len(d))}}
    return AnalysisResult(title or f"{by}별 {measure} 비중", t, Kind.APPLIED_AGG, facts, checks,
                          {"type": "bar", "x": by, "y": "비중(%)"})


def top_n(df: pd.DataFrame, by: str, measure: str, n: int = 10, filters=None, title: str | None = None,
          highlight: list[str] | None = None) -> AnalysisResult:
    """by 값별 비중 상위 n. highlight(관심 지역)는 n위 밖이어도 순위·비중을 facts에 남긴다."""
    r = share_by(df, by, measure, filters)
    full = r.table.copy()
    full.insert(0, "순위", range(1, len(full) + 1))
    t = full.head(n).copy()
    extra = full[full[by].isin(highlight or []) & (full["순위"] > n)]
    if len(extra):                                   # 관심 지역이 n위 밖이면 표 아래에 덧붙인다
        t = pd.concat([t, extra], ignore_index=True)
    r.table, r.title = t, title or f"{by} 상위 {n}"
    r.facts["applied"] = {f"{i}위": f"{k}({p}%)" for i, k, p in zip(t["순위"], t[by], t["비중(%)"])}
    r.facts["applied"]["관심 지역 순위"] = {k: [int(i), float(p)] for i, k, p in zip(full["순위"], full[by], full["비중(%)"])
                                         if k in (highlight or [])}
    r.facts["applied"]["지역 수"] = int(len(full))
    avg = round(100 / len(full), 1) if len(full) else None
    r.facts["applied"]["동네 평균 비중(%)"] = avg
    sel = full[full[by].isin(highlight or [])]
    if avg and len(sel):
        r.facts["applied"]["관심 지역 몫 합계(%)"] = round(float(sel["비중(%)"].sum()), 1)
        r.facts["applied"]["동네 평균 대비 배수"] = round(float(sel["비중(%)"].sum()) / avg, 1)
    return r


def store_rank(df: pd.DataFrame, by: str = "bjd", count: str = "store_cnt", n: int = 10, filters=None,
               highlight: list[str] | None = None, title: str | None = None) -> AnalysisResult:
    """공개 상가정보: 같은 업종 가게 수의 동네 순위와 몫. 공개 데이터라 가게 수(개수)도 그대로 보여 준다."""
    r = top_n(df, by, count, n, filters, title=title or "같은 업종 가게 수 순위", highlight=highlight)
    cnt = apply_filters(df, filters).groupby(by)[count].sum()
    r.table["가게 수"] = r.table[by].map(cnt).fillna(0).astype(int)
    a = r.facts["applied"]
    a["제주 전체 가게 수"] = int(cnt.sum())
    a["동네 평균 가게 수"] = round(float(cnt.sum()) / len(cnt), 1) if len(cnt) else None
    a["관심 지역 가게 수"] = {k: int(cnt.get(k, 0)) for k in (highlight or [])}
    return r


def district_profile(df: pd.DataFrame, focus: str | None = None, user: str = "내국인관광객",
                     title: str | None = None) -> AnalysisResult:
    """허브-지구: 지구 유형별 시간대 비중·토일 비중·손님 구성(비중, 응용집계)."""
    rows, applied = [], {}
    for dist, g in df.groupby("districtType"):
        row = {"구분": dist}
        t = g[(g["dim"] == "시간대") & (g["userType"] == user)].groupby("cat")["useCost"].sum()
        for k in ("오전", "점심", "오후", "저녁", "밤"):
            row[f"{k} 비중(%)"] = _pct(t.get(k, 0) / t.sum()) if t.sum() else None
        w = g[(g["dim"] == "요일") & (g["userType"] == user)].groupby("cat")["useCost"].sum()
        row["토·일 비중(%)"] = _pct((w.get("토", 0) + w.get("일", 0)) / w.sum()) if w.sum() else None
        if w.sum():
            row["가장 많은 요일"], row["가장 적은 요일"] = str(w.idxmax()), str(w.idxmin())
        u = g[g["dim"] == "이용자"].groupby("cat")["useCost"].sum()
        for k in ("내국인관광객", "제주도민", "중국인관광객", "법인"):
            row[f"{k} 비중(%)"] = _pct(u.get(k, 0) / u.sum()) if u.sum() else None
        rows.append(row)
    order = ["내국인 주요 관광지", "중국인 주요 관광지", "상업지", "제주시 구도심", "서귀포시 구도심"]
    t = pd.DataFrame(rows)
    t["_o"] = t["구분"].map({k: i for i, k in enumerate(order)}).fillna(9)
    t = t.sort_values("_o").drop(columns="_o").reset_index(drop=True)
    applied["관심 지구"] = focus
    applied["기간"] = f"{df['dtYearMonth'].min()}~{df['dtYearMonth'].max()}"
    for r in rows:
        applied[r["구분"]] = {k: v for k, v in r.items() if k != "구분"}
    checks = [f"기간 확인: {fmt_month_short(df['dtYearMonth'].min())}~{fmt_month_short(df['dtYearMonth'].max())}"]
    return AnalysisResult(title or "지구 유형별 요일·시간대·손님 구성", t, Kind.APPLIED_AGG,
                          {"applied": applied, "simple": {}}, checks)


def trend(df: pd.DataFrame, time_col: str, measure: str, filters=None, title: str | None = None) -> AnalysisResult:
    """기간별 합계, 전기 대비·전년 같은 달 대비 증감률(%)."""
    d = apply_filters(df, filters)
    s = d.groupby(time_col)[measure].sum().sort_index()
    t = pd.DataFrame({time_col: s.index, measure: s.values})
    t["전기 대비(%)"] = (t[measure].pct_change() * 100).round(1)
    checks = []
    if time_col in ("base_year_month", "dtYearMonth") and len(s):
        idx = pd.period_range(pd.Period(s.index.min(), "M"), pd.Period(s.index.max(), "M"), freq="M")
        expect = [p.strftime("%Y%m") for p in idx]
        missing = [m for m in expect if m not in set(s.index)]
        if missing:
            checks.append(f"기간 누락: {', '.join(fmt_month_short(m) for m in missing)}")
        else:
            checks.append(f"기간 확인: {fmt_month_short(expect[0])}~{fmt_month_short(expect[-1])} 빠진 달 없음")
        yoy = {}
        for ym, v in s.items():
            prev = f"{int(ym[:4]) - 1}{ym[4:]}"
            if prev in s.index and s[prev]:
                yoy[ym] = round((v / s[prev] - 1) * 100, 1)
        t["전년 같은 달 대비(%)"] = t[time_col].map(yoy)
    facts = {"applied": {}, "simple": {"기간 수": int(len(s))}}
    if len(s) and s.mean():
        t["지수(평균=100)"] = (t[measure] / s.mean() * 100).round(1)       # 평소 달 = 100
    if len(s) >= 2:
        # '첫 달 대비 마지막 달'은 계절이 다른 달을 비교하므로 쓰지 않는다. 24개월 이상이면 전년 같은 달과 비교.
        facts["applied"]["가장 높은 기간"] = str(s.idxmax())
        facts["applied"]["가장 낮은 기간"] = str(s.idxmin())
        facts["applied"]["최고/최저 배율"] = round(float(s.max() / s.min()), 2) if s.min() else None
        facts["applied"]["최고/최저 배율(화면)"] = round(float(s.max() / s.min()), 1) if s.min() else None
        idx = dict(zip(t[time_col], t["지수(평균=100)"])) if "지수(평균=100)" in t else {}
        facts["applied"]["성수기(지수 120 이상)"] = [k for k, v in idx.items() if v >= 120]
        facts["applied"]["비수기(지수 80 미만)"] = [k for k, v in idx.items() if v < 80]
        facts["applied"]["월 지수"] = {k: float(v) for k, v in idx.items()}
        if "전년 같은 달 대비(%)" in t and t["전년 같은 달 대비(%)"].notna().any():
            last = t.dropna(subset=["전년 같은 달 대비(%)"]).iloc[-1]
            facts["applied"]["최근 달 전년 같은 달 대비(%)"] = float(last["전년 같은 달 대비(%)"])
            facts["applied"]["최근 달"] = str(last[time_col])
    return AnalysisResult(title or f"{time_col}별 {measure} 추이", t, Kind.SIMPLE_AGG, facts, checks,
                          {"type": "line", "x": time_col, "y": measure})


def _slot_hours(label: str) -> int | None:
    """'07~11시' → 4, '22시~07시' → 9 (명세서 [참고4] 시간대 기준)."""
    import re
    m = re.findall(r"(\d{1,2})", label)
    if len(m) < 2:
        return None
    a, b = int(m[0]), int(m[1])
    return (b - a) % 24 or 24


def pattern(df: pd.DataFrame, cat_col: str, measure: str, order: list[str] | None = None, filters=None,
            title: str | None = None, exclude: list[str] | None = None,
            hours: dict[str, int] | None = None) -> AnalysisResult:
    """요일·시간대 같은 순서 있는 범주의 분포(비중)와 최고 시점.

    exclude: 비중 계산에서 뺄 값. 카드 요일별(1-12)의 '공휴일'은 원래 요일에도 함께 집계되므로
    (운영진 답변 2026-11-02) 빼지 않으면 같은 매출이 두 번 세어진다.
    hours: 시간대별 길이(시간). 점심(3시간)과 밤(9시간)처럼 길이가 달라 '1시간당 비중'으로도 비교한다.
    동점: 비중 차이가 0.5%p 미만이면 함께 '가장 많은 시점'으로 본다.
    """
    if exclude:
        df = df[~df[cat_col].isin(exclude)]
    r = share_by(df, cat_col, measure, filters)
    if exclude:
        ex = ", ".join(exclude)
        r.checks.append(f"중복 방지: {ex}{josa(ex, '은/는')} 원래 요일에도 포함되어 있어 비중 계산에서 뺐습니다.")
    t = r.table
    if order:
        t = t.set_index(cat_col).reindex([o for o in order if o in set(t[cat_col])]).reset_index()
    if hours:
        t["시간"] = pd.to_numeric(t[cat_col].map(hours), errors="coerce")     # 빈 표여도 숫자형(글자형 나눗셈 오류 방지)
        t["1시간당 비중(%)"] = (pd.to_numeric(t["비중(%)"], errors="coerce") / t["시간"]).round(2)
    r.table, r.title = t, title or f"{cat_col}별 {measure} 분포"
    r.facts["applied"] = {f"{k} 비중(%)": float(v) for k, v in zip(t[cat_col], t["비중(%)"])}
    if len(t):
        top = float(t["비중(%)"].max())
        peaks = [str(x) for x, v in zip(t[cat_col], t["비중(%)"]) if top - float(v) < 0.5]
        low = t.loc[t["비중(%)"].idxmin()]
        r.facts["applied"]["가장 많은 시점"] = "·".join(peaks)
        r.facts["applied"]["최고 시점 비중(%)"] = top
        r.facts["applied"]["가장 적은 시점"] = str(low[cat_col])
        r.facts["applied"]["최저 시점 비중(%)"] = float(low["비중(%)"])
        r.facts["applied"]["고르게 나뉠 때 비중(%)"] = round(100 / len(t), 1)
        if hours and t["1시간당 비중(%)"].notna().all():
            ph = t.sort_values("1시간당 비중(%)", ascending=False)
            r.facts["applied"]["1시간당 가장 바쁜 시점"] = str(ph[cat_col].iloc[0])
            r.facts["applied"]["1시간당 비중(%)"] = float(ph["1시간당 비중(%)"].iloc[0])
            if len(ph) > 1 and float(ph["1시간당 비중(%)"].iloc[1]):
                r.facts["applied"]["1시간당 1위/2위 배율"] = round(
                    float(ph["1시간당 비중(%)"].iloc[0]) / float(ph["1시간당 비중(%)"].iloc[1]), 2)
    r.chart = {"type": "bar", "x": cat_col, "y": "비중(%)"}
    return r


COMP_LABELS = {"도민": "도민", "제주도민": "도민", "NA": "법인·기타", "법인": "법인·기타", "내국인": "내국인 관광객",
               "내국인관광객": "내국인 관광객", "개별": "관광객", "단체": "관광객"}


def compare_share(df: pd.DataFrame, focus: dict[str, list[str]], seg_col: str, seg_values: list[str],
                  measure: str, base: dict[str, list[str]] | None = None, title: str | None = None,
                  focus_label: str = "관심 대상", base_label: str = "비교 기준",
                  col_labels: dict[str, str] | None = None) -> AnalysisResult:
    """관심 집단(focus)과 기준 집단(base, 기본=전체)에서 특정 구분값 비중을 비교.

    예: 애월읍 카페의 관광객(개별+단체) 매출 비중 vs 제주 전체 카페의 관광객 비중.
    """
    def _share(d):
        tot = float(d[measure].sum())
        part = float(d.loc[d[seg_col].isin(seg_values), measure].sum())
        return (part / tot if tot else np.nan), tot, len(d)

    fd, bd = apply_filters(df, focus), apply_filters(df, base)
    f_share, f_tot, f_n = _share(fd)
    b_share, b_tot, b_n = _share(bd)
    nat = {"중국": "중국인", "일본": "일본인"}
    seg_label = ((nat.get(seg_values[0], "외국인") if len(seg_values) == 1 else "외국인") if seg_col == "user_type" else
                 "관광객" if set(seg_values) <= {"개별", "단체", "내국인관광객"} else "+".join(seg_values))

    def _comp(d):   # 손님 구성(100% 막대용): 관심 구분 / 도민 / 그 밖
        tot = float(d[measure].sum())
        if not tot:
            return {}
        lab = d[seg_col].map(lambda v: seg_label if v in seg_values else COMP_LABELS.get(v, "기타"))
        return {k: round(float(v) / tot * 100, 1) for k, v in d.groupby(lab)[measure].sum().items()}
    t = pd.DataFrame({
        "구분": [focus_label, base_label],
        "조건": [describe_filters(focus, col_labels), describe_filters(base, col_labels)],
        f"{'+'.join(seg_values)} 비중(%)": [_pct(f_share), _pct(b_share)],
    })
    idx = round(f_share / b_share * 100, 1) if b_share else None
    facts = {"applied": {"관심 대상 비중(%)": _pct(f_share), "비교 기준 비중(%)": _pct(b_share),
                         "차이(%p)": round(_pct(f_share) - _pct(b_share), 1), "지수(기준=100)": idx,
                         "구성": {focus_label: _comp(fd), base_label: _comp(bd)}},
             "simple": {"관심 대상 합계": f_tot, "비교 기준 합계": b_tot, "관심 대상 행 수": int(f_n)}}
    checks = []
    if f_n < 30:
        checks.append(f"주의: 관심 대상 데이터가 {f_n}행뿐이라 비중이 불안정할 수 있습니다.")
    return AnalysisResult(title or f"{'+'.join(seg_values)} 비중 비교", t, Kind.APPLIED_AGG, facts, checks,
                          {"type": "bar", "x": "구분", "y": t.columns[-1]})


def group_share(df: pd.DataFrame, groups: list[str], seg_col: str, seg_values: list[str], measure: str,
                filters=None, title: str | None = None) -> AnalysisResult:
    """그룹(예: 시 × 도심/읍면)마다 특정 구분값(예: 내국인관광객)의 비중과, 전체 비중.

    공개 데이터 597로 '이 지역만의 특징인지, 읍면이면 어디나 그런지'를 가려 보는 데 쓴다.
    """
    d = apply_filters(df, filters)
    tot = d.groupby(groups)[measure].sum()
    part = d[d[seg_col].isin(seg_values)].groupby(groups)[measure].sum()
    share = (part.reindex(tot.index).fillna(0) / tot * 100).round(1)
    t = share.reset_index().rename(columns={measure: f"{'+'.join(seg_values)} 비중(%)"})
    t["구분"] = t[groups].astype(str).agg(" ".join, axis=1)
    all_tot = float(d[measure].sum())
    overall = round(float(d.loc[d[seg_col].isin(seg_values), measure].sum()) / all_tot * 100, 1) if all_tot else None
    col = f"{'+'.join(seg_values)} 비중(%)"
    t = t[["구분", col]].sort_values(col).reset_index(drop=True)
    facts = {"applied": {**{f"{g} 비중(%)": float(v) for g, v in zip(t["구분"], t[col])}, "전체 비중(%)": overall},
             "simple": {"행 수": int(len(d))}}
    return AnalysisResult(title or "그룹별 비중", t, Kind.APPLIED_AGG, facts, ["검산: 그룹별 비중은 각 그룹 합계 기준"],
                          {"type": "barh", "x": "구분", "y": col})


def season_by(df: pd.DataFrame, time_col: str, by: str, measure: str, filters=None,
              title: str | None = None) -> AnalysisResult:
    """그룹(예: 관광객/도민)마다 '가장 많은 달 ÷ 가장 적은 달' 배율. 최근 12개월(또는 전체 기간)을 쓴다."""
    d = apply_filters(df, filters)
    months = sorted(d[time_col].unique())[-24:]
    d = d[d[time_col].isin(months)]
    # 같은 달끼리 평균(여러 해가 섞이면 달별 평균)
    m = d.assign(_m=d[time_col].astype(str).str[4:6]).groupby([by, "_m", time_col])[measure].sum()
    m = m.groupby(level=[0, 1]).mean()
    rows = []
    for g, s in m.groupby(level=0):
        s = s.droplevel(0)
        if len(s) >= 2 and s.min():
            rows.append({by: g, "최고 달": f"{int(s.idxmax())}월", "최저 달": f"{int(s.idxmin())}월",
                         "최고/최저 배율": round(float(s.max() / s.min()), 2)})
    t = pd.DataFrame(rows)
    facts = {"applied": {f"{r[by]} 최고/최저 배율": r["최고/최저 배율"] for r in rows}, "simple": {}}
    return AnalysisResult(title or "그룹별 계절 배율", t, Kind.APPLIED_AGG, facts, [], {"type": "none"})


def region_compare(df: pd.DataFrame, regions: list[str], measure: str, seg_col: str = "tour_type",
                   seg_values: list[str] | None = None, filters=None, time_col: str = "base_year_month",
                   title: str | None = None) -> AnalysisResult:
    """동네끼리 나란히 비교: 동네마다 관광객 몫(%), 같은 업종 매출 순위·몫(%), 성수기÷비수기 배율.

    모두 비율·순위·배율(응용집계)이라 그대로 반출할 수 있다. filters는 업종 조건(동네 조건은 넣지 않는다).
    """
    seg_values = list(seg_values or ["개별", "단체"])
    d = apply_filters(df, filters)
    tot_by = d.groupby("bjd")[measure].sum().sort_values(ascending=False)
    tot_by = tot_by[tot_by > 0]
    rank = {b: i + 1 for i, b in enumerate(tot_by.index)}
    all_tot = float(tot_by.sum())
    base = round(float(d.loc[d[seg_col].isin(seg_values), measure].sum()) / all_tot * 100, 1) if all_tot else None
    rows, checks = [], []
    for r in regions:
        dr = d[d["bjd"] == r]
        tot = float(dr[measure].sum())
        row = {"동네": r, "관광객 비중(%)": None, "매출 순위": rank.get(r), "매출 몫(%)": None,
               "성수기÷비수기(배)": None, "성수기": "", "비수기": ""}
        if tot:
            row["관광객 비중(%)"] = round(float(dr.loc[dr[seg_col].isin(seg_values), measure].sum()) / tot * 100, 1)
            row["매출 몫(%)"] = round(tot / all_tot * 100, 1)
            m = dr.groupby(time_col)[measure].sum().sort_index()
            if len(m) >= 12 and float(m.min()) > 0:
                row["성수기÷비수기(배)"] = round(float(m.max()) / float(m.min()), 1)
                row["성수기"], row["비수기"] = f"{int(str(m.idxmax())[4:6])}월", f"{int(str(m.idxmin())[4:6])}월"
        if len(dr) < 30:
            checks.append(f"주의: {r} 데이터가 {len(dr)}행뿐이라 비교가 불안정할 수 있습니다.")
        rows.append(row)
    t = pd.DataFrame(rows)
    checks.append(f"검산: 동네 {len(regions)}곳을 같은 기준(업종·기간)으로 비교했습니다.")
    facts = {"applied": {"동네": rows, "지역 수": len(tot_by), "제주 평균 관광객 비중(%)": base},
             "simple": {"동네별 행 수": {r: int((d["bjd"] == r).sum()) for r in regions}}}
    return AnalysisResult(title or "동네 비교", t, Kind.APPLIED_AGG, facts, checks,
                          {"type": "bar", "x": "동네", "y": "관광객 비중(%)"})
