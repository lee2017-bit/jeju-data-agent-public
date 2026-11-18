"""결론을 보여 주는 차트(matplotlib). 화면용(제목 없음)과 반출용(결론 제목·부제·출처)을 같은 함수로 그린다.

규칙(설계안): '내 것'(관심 동네·바쁜 시간대)만 주황으로, 나머지는 회색. 기준선(평소=100, 고르게 팔리면 14.3%)을
점선으로. 영문·회전 라벨 없음. 가상 데이터는 그림 안에 워터마크. 반출은 PNG만(정책).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .agent import StepOutcome  # noqa: E402
from .insight import Card  # noqa: E402

ACCENT, PRIMARY, MUTED, LIGHT, LOWC, AXIS, GRID, TEXT = (
    "#EA580C", "#1D4ED8", "#CBD5E1", "#E2E8F0", "#93C5FD", "#64748B", "#E2E8F0", "#0F172A")
COMP_COLORS = {"관광객": ACCENT, "내국인 관광객": ACCENT, "외국인": ACCENT, "도민": PRIMARY, "법인·기타": MUTED,
               "기타": LIGHT}


def _setup():
    from .report import setup_korean_font
    setup_korean_font()
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": MUTED,
                         "axes.grid": False, "font.size": 11, "text.color": TEXT, "axes.labelcolor": AXIS,
                         "xtick.color": TEXT, "ytick.color": AXIS})


def _width_in(fig, text: str, fontsize: float, bold: bool = False) -> float:
    t = fig.text(0, 0, text, fontsize=fontsize, fontweight="bold" if bold else "normal")
    w = t.get_window_extent(renderer=fig.canvas.get_renderer()).width / fig.dpi
    t.remove()
    return w


def _fit_title(fig, title: str, avail: float) -> tuple[float, list[str]]:
    """제목이 한 줄에 들어가게 글자를 조금 줄이고(13.5→11.5), 그래도 넘치면 두 줄로 나눈다."""
    for fs in (13.5, 12.5, 11.5):
        if _width_in(fig, title, fs, True) <= avail:
            return fs, [title]
    for sep in (" — ", ": ", ", "):                 # 뜻이 끊기는 자리에서 먼저 나눈다
        if sep in title:
            i = title.index(sep) + (len(sep) if sep != " — " else 0)
            a_, b_ = title[:i].rstrip(), title[i:].strip()
            if max(_width_in(fig, a_, 12.5, True), _width_in(fig, b_, 12.5, True)) <= avail:
                return 12.5, [a_, b_]
    words = title.split(" ")
    best = min(range(1, len(words)), key=lambda k: abs(len(" ".join(words[:k])) - len(title) / 2)) if len(words) > 1 else 1
    return 12.5, [" ".join(words[:best]), " ".join(words[best:])]


def _finish(fig, ax, path: Path, title: str | None, subtitle: str, source: str, synthetic: bool, dpi: int):
    W, H = fig.get_size_inches()
    badge = "체험용 가상 데이터 · 실제 수치 아님"
    badge_w = _width_in(fig, badge, 8.5) + 0.3 if synthetic else 0.0
    fs, lines = (13.5, [])
    if title:
        fs, lines = _fit_title(fig, title, W * 0.973 - badge_w - 0.1)
        if len(lines) > 1:                           # 두 줄이면 그만큼 그림을 늘려 아래 차트가 눌리지 않게
            H += 0.3 * (len(lines) - 1)
            fig.set_size_inches(W, H)
    if synthetic:   # 그림만 따로 돌아다녀도 가상임이 보이게(오른쪽 위 호박색 상자)
        fig.text(0.985, 1 - 0.06 / H, badge, ha="right", va="top", fontsize=8.5,
                 color="#92400E", bbox={"boxstyle": "round,pad=0.35", "fc": "#FEF3C7", "ec": "#F59E0B", "lw": 0.8},
                 zorder=10)
    top = 1.0
    if title:
        fig.text(0.012, 1 - 0.06 / H, "\n".join(lines), ha="left", va="top", fontsize=fs, fontweight="bold",
                 color=TEXT, linespacing=1.3)
        y = 0.06 + 0.30 * len(lines) + 0.11            # 부제가 시작하는 높이(위에서 인치)
        if subtitle:
            fig.text(0.012, 1 - y / H, subtitle, fontsize=9.5, color=AXIS, va="top", linespacing=1.5)
            y += 0.35 + 0.25 * subtitle.count("\n")
        else:
            y -= 0.05
        top = 1 - y / H
    bottom = 0.0
    if source:
        fig.text(0.012, 0.01, source, fontsize=7.5, color=AXIS)
        bottom = 0.06 * 4.1 / H
    fig.tight_layout(rect=(0, bottom, 1, top))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)
    return path


def chart_customers(o: StepOutcome, ax):
    comp = o.result.facts["applied"].get("구성", {})
    rows = list(comp.items())[::-1]                      # 위: 관심 대상, 아래: 비교 기준
    order = ["관광객", "내국인 관광객", "외국인", "도민", "법인·기타", "기타"]
    for y, (name, parts) in enumerate(rows):
        left = 0.0
        for k in [k for k in order if k in parts]:
            v = parts[k]
            ax.barh(y, v, left=left, color=COMP_COLORS.get(k, LIGHT), height=0.55, edgecolor="white", linewidth=1.5)
            if v >= 9:
                ax.text(left + v / 2, y, f"{k} {v:.1f}%", ha="center", va="center", fontsize=10,
                        color="white" if k in ("관광객", "내국인 관광객", "외국인", "도민") else TEXT, fontweight="bold")
            left += v
    ax.set_yticks(range(len(rows)), [r[0] for r in rows], fontsize=11)
    ax.set_xlim(0, 100)
    ax.set_xticks([])
    ax.spines[["bottom", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)


def chart_season(o: StepOutcome, ax):
    idx = o.result.facts["applied"].get("월 지수", {})
    keys = list(idx)
    labels, prev = [], None
    for k in keys:
        y, m = k[:4], int(k[4:6])
        labels.append(f"{y[2:]}년\n{m}월" if prev is not None and y != prev else f"{m}월")
        prev = y
    vals = [idx[k] for k in keys]
    colors = [ACCENT if v >= 120 else (LOWC if v < 80 else MUTED) for v in vals]
    hi = max(range(len(vals)), key=vals.__getitem__) if vals else None
    if hi is not None and colors[hi] == MUTED:
        colors[hi] = ACCENT
    bars = ax.bar(range(len(vals)), vals, color=colors, width=0.7)
    ax.bar_label(bars, labels=[f"{round(v)}" for v in vals], fontsize=9, color=TEXT, padding=2)
    ax.axhline(100, ls="--", lw=1, color=AXIS)
    ax.set_xticks(range(len(vals)), labels, fontsize=9.5)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_ylim(0, max(vals + [100]) * 1.15)


def chart_week(o: StepOutcome, ax, card: Card | None):
    t = o.result.table
    names = [w for w in t["week"]]
    vals = list(t["비중(%)"])
    three = (card.vals.get("three", "") if card else "").split("·")
    lo = card.vals.get("lo") if card else None
    colors = [ACCENT if n[0] in three else (LOWC if n == lo else MUTED) for n in names]
    bars = ax.bar([n[0] for n in names], vals, color=colors, width=0.65)
    ax.bar_label(bars, labels=[f"{v:.1f}%" for v in vals], fontsize=9.5, padding=2)
    ax.axhline(100 / 7, ls="--", lw=1, color=AXIS)
    if lo in names:
        k = names.index(lo)
        ax.text(k, vals[k] / 2, "휴무\n후보", ha="center", va="center", fontsize=8.5, color=PRIMARY)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_ylim(0, max(vals) * 1.22)


def chart_time(o: StepOutcome, ax, hours_label: dict[str, str]):
    t = o.result.table
    names = list(t["time"])
    vals = list(t["비중(%)"])
    ph = o.result.facts["applied"].get("1시간당 가장 바쁜 시점")
    colors = [ACCENT if n == ph else MUTED for n in names]
    bars = ax.bar(range(len(names)), vals, color=colors, width=0.65)
    labels = [f"{v:.1f}%" for v in vals]
    ax.bar_label(bars, labels=labels, fontsize=9.5, padding=2)
    if "1시간당 비중(%)" in t:
        for k, (v, h) in enumerate(zip(vals, t["1시간당 비중(%)"])):
            ax.text(k, v / 2, f"1시간당\n{h:.1f}%", ha="center", va="center", fontsize=8.5,
                    color="white" if names[k] == ph else TEXT)
    ax.set_xticks(range(len(names)), [f"{n}\n{hours_label.get(n, '')}" for n in names], fontsize=9.5)
    ax.set_yticks([])
    ax.spines["left"].set_visible(False)
    ax.set_ylim(0, max(vals) * 1.2)


def chart_location(o: StepOutcome, ax, focus: list[str]):
    t = o.result.table
    names, vals, ranks = list(t["bjd"])[::-1], list(t["비중(%)"])[::-1], list(t["순위"])[::-1]
    colors = [ACCENT if n in focus else MUTED for n in names]
    bars = ax.barh(range(len(names)), vals, color=colors, height=0.65)
    ax.bar_label(bars, labels=[f"{v:.1f}%" for v in vals], fontsize=9, padding=3)
    ax.set_yticks(range(len(names)), [f"{r}위 {n}" for r, n in zip(ranks, names)], fontsize=9.5)
    for lab, n in zip(ax.get_yticklabels(), names):
        if n in focus:
            lab.set_color(ACCENT)
            lab.set_fontweight("bold")
    ax.set_xticks([])
    ax.spines[["bottom"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, max(vals) * 1.18)


def chart_regions(o: StepOutcome, ax):
    a = o.result.facts.get("applied", {})
    rows = [r for r in a.get("동네", []) if r.get("관광객 비중(%)") is not None][::-1]
    names = [f"{r['동네']} · 매출 {r['매출 순위']}위" if r.get("매출 순위") else r["동네"] for r in rows]
    vals = [r["관광객 비중(%)"] for r in rows]
    bars = ax.barh(range(len(rows)), vals, color=ACCENT, height=0.55)
    ax.bar_label(bars, labels=[f"{v:.1f}%" for v in vals], fontsize=10, padding=3, fontweight="bold")
    ax.set_yticks(range(len(rows)), names, fontsize=10)
    base = a.get("제주 평균 관광객 비중(%)")
    if base is not None:
        ax.axvline(base, color=MUTED, linestyle="--", linewidth=1.2)
        ax.text(base, len(rows) - 0.45, f" 제주 평균 {base}%", fontsize=9, color="#475569", va="bottom")
    ax.set_xticks([])
    ax.spines[["bottom"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, max(vals + [base or 0]) * 1.25)
    ax.set_ylim(-0.6, len(rows) - 0.1)


def chart_stores(o: StepOutcome, ax, focus: list[str]):
    t = o.result.table
    names, vals, ranks = list(t["bjd"])[::-1], list(t["가게 수"])[::-1], list(t["순위"])[::-1]
    colors = [ACCENT if n in focus else MUTED for n in names]
    bars = ax.barh(range(len(names)), vals, color=colors, height=0.65)
    ax.bar_label(bars, labels=[f"{v}곳" for v in vals], fontsize=9, padding=3)
    ax.set_yticks(range(len(names)), [f"{r}위 {n}" for r, n in zip(ranks, names)], fontsize=9.5)
    for lab, n in zip(ax.get_yticklabels(), names):
        if n in focus:
            lab.set_color(ACCENT)
            lab.set_fontweight("bold")
    ax.set_xticks([])
    ax.spines[["bottom"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, max(vals) * 1.18 if vals else 1)


SLOT_COLORS = {"오전": "#E2E8F0", "점심": "#FDBA74", "오후": ACCENT, "저녁": PRIMARY, "밤": "#1E293B"}


def chart_district(o: StepOutcome, ax, focus: str | None):
    t = o.result.table
    names = list(t["구분"])[::-1]
    for y, name in enumerate(names):
        row = t[t["구분"] == name].iloc[0]
        left = 0.0
        for k, col in SLOT_COLORS.items():
            v = float(row.get(f"{k} 비중(%)") or 0)
            ax.barh(y, v, left=left, color=col, height=0.6, edgecolor="white", linewidth=1.2)
            if v >= 8:
                ax.text(left + v / 2, y, f"{k} {v:.0f}%", ha="center", va="center", fontsize=8.5,
                        color="white" if k in ("오후", "저녁", "밤") else TEXT)
            left += v
    ax.set_yticks(range(len(names)), names, fontsize=10)
    for lab, n in zip(ax.get_yticklabels(), names):
        if n == focus:
            lab.set_color(ACCENT)
            lab.set_fontweight("bold")
    ax.set_xlim(0, 100)
    ax.set_xticks([])
    ax.spines[["bottom", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)


def chart_public(o: StepOutcome, ax, focus_label: str):
    t = o.result.table
    col = [c for c in t.columns if "비중" in c][0]
    names, vals = list(t["구분"]), list(t[col])
    colors = [ACCENT if focus_label.startswith(n) else MUTED for n in names]
    bars = ax.barh(range(len(names)), vals, color=colors, height=0.6)
    ax.bar_label(bars, labels=[f"{v:.1f}%" for v in vals], fontsize=9.5, padding=3)
    overall = o.result.facts["applied"].get("전체 비중(%)")
    if overall is not None:
        ax.axvline(overall, ls="--", lw=1, color=AXIS)
        ax.text(overall, len(names) - 0.45, f"제주 전체 {overall}%", fontsize=9, color=AXIS, ha="center")
    ax.set_yticks(range(len(names)), names, fontsize=10)
    ax.set_xticks([])
    ax.spines[["bottom"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, 100)


LEGEND = {"season": "점선 = 평소 달(기간 평균) 100 · 주황 성수기(120 이상) · 하늘색 비수기(80 미만)",
          "week": "점선 = 요일마다 고르게 팔리면 하루 14.3% · 하늘색 = 휴무 후보",
          "time": "주황 = 1시간당 가장 바쁜 시간대(시간대마다 길이가 달라 1시간당으로 비교)",
          "location": "막대 = 제주 전체 같은 업종 매출 중 그 동네의 몫 · 주황 = 관심 동네",
          "stores": "막대 = 같은 업종 가게 수(소상공인 상가정보, 실제 값) · 주황 = 관심 동네",
          "visitors": "점선 = 평소 달 100 · 외지인 방문자 수(한국관광공사, 이동통신 기반 실제 값)",
          "district": "막대 = 지구 유형별 내국인 관광객 카드 매출의 시간대 구성(제주데이터허브, 실제 값) · 주황 글씨 = 가장 가까운 유형",
          "public": "점선 = 제주 전체 · 주황 = 관심 지역이 속한 그룹"}
SIZES = {"customers": (8, 2.4), "season": (8, 3.4), "week": (8, 3.2), "time": (8, 3.3), "location": (8, 4.0),
         "stores": (8, 4.0), "visitors": (8, 3.4), "district": (8, 3.2),
         "public": (8, 2.9), "regions": (8, 2.6)}


def render(card: Card, o: StepOutcome, path: Path, *, focus: list[str] | None = None, focus_label: str = "",
           hours_label: dict[str, str] | None = None, title: str | None = None, subtitle: str = "",
           source: str = "", dpi: int = 150) -> Path | None:
    """card.key에 맞는 차트를 path(PNG)에 그린다. title을 주면 반출용(결론 제목·부제·출처 포함)."""
    _setup()
    w, h = SIZES.get(card.key, (8, 3.2))
    if title:
        h += 0.9
    else:                       # 화면용: 좁은 칸(약 600px)에 들어가므로 그림을 작게 그려 글자를 크게 보이게
        w, h = w * 0.72, h * 0.8
    fig, ax = plt.subplots(figsize=(w, h))
    k = card.key
    if k == "customers":
        chart_customers(o, ax)
    elif k == "season":
        chart_season(o, ax)
    elif k == "week":
        chart_week(o, ax, card)
    elif k == "time":
        chart_time(o, ax, hours_label or {})
    elif k == "location":
        chart_location(o, ax, focus or [])
    elif k == "stores":
        chart_stores(o, ax, focus or [])
    elif k == "visitors":
        chart_season(o, ax)
    elif k == "district":
        chart_district(o, ax, (o.result.facts.get("applied") or {}).get("관심 지구"))
    elif k == "public":
        chart_public(o, ax, focus_label)
    elif k == "regions":
        chart_regions(o, ax)
    else:
        plt.close(fig)
        return None
    return _finish(fig, ax, path, title, subtitle, source, card.synthetic, dpi)
