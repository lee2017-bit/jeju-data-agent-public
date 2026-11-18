"""센터 데이터 명세서(catalog)를 따르는 가상 CSV 생성기.

목적: 반출 불가 센터 데이터는 밖에서 받을 수 없으므로, 개발·시연·테스트용으로
명세서와 컬럼명·값 형식·코드값이 같은 가상 데이터를 만든다(운영진 허용, 2026-10-28 답변).

원칙
- 컬럼 순서·이름·형식은 명세서 그대로. 코드값은 명세서의 [참고] 코드표와 비고 목록에서만 뽑는다.
- 수치는 가짜다. 분포는 시연이 그럴듯하도록 단순한 규칙(계절성, 관광지 가중치 등)만 둔다.
- 시군구·권역 같은 지리 정합성은 근사치다(명세서에 법정동→시군구 대응표가 없음).
- 같은 seed면 같은 결과(재현성).

사용 예:
    python -m jeju_agent.synth 1-08 --months 202505-202604 --out data/synthetic
"""

from __future__ import annotations

import argparse
import json
import re
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "catalog" / "center_catalog.json"

# 서귀포시 법정동(동 지역). 읍·면은 행정동 코드표의 '시 + 읍면' 이름으로 판별한다.
SEOGWIPO_DONG = {
    "서귀동", "동홍동", "서홍동", "법환동", "보목동", "토평동", "상효동", "신효동", "하효동",
    "강정동", "도순동", "대포동", "월평동", "하원동", "회수동", "색달동", "중문동", "상예동",
    "하예동", "호근동", "영남동", "서호동",
}
# 시연용 관광 비중 가중치(가상). 관광지 읍면일수록 관광객 매출이 많게.
TOURIST_WEIGHT = {"애월읍": 1.8, "성산읍": 1.9, "안덕면": 1.6, "구좌읍": 1.5, "한림읍": 1.4,
                  "중문동": 2.0, "색달동": 1.9, "용담이동": 1.5, "연동": 1.3, "우도면": 2.0}
# 시연 시나리오에 필요한 (동, 업종)은 항상 존재하게 한다.
DEMO_PRESENT = {("애월읍", "비알콜 음료점업"), ("애월읍", "한식 음식점업"), ("노형동", "한식 음식점업"),
                ("연동", "한식 음식점업"), ("성산읍", "비알콜 음료점업")}
# 업종별 평균 객단가(원, 가상)
TICKET = {"호텔업": 180_000, "휴양콘도 운영업": 160_000, "여관업": 70_000, "면세점": 250_000,
          "정기 항공 운송업": 120_000, "자동차 임대업": 110_000, "비알콜 음료점업": 9_000,
          "한식 음식점업": 28_000, "체인화 편의점": 8_000, "슈퍼마켓": 25_000}


PUBLIC = ROOT / "catalog" / "public_datasets.json"


def load_catalog(path: Path = CATALOG, include_public: bool = True) -> dict:
    """센터 명세서 표 + 제주데이터허브 공개 데이터 표(같은 구조)."""
    cat = json.loads(path.read_text(encoding="utf-8"))
    if include_public and PUBLIC.exists():
        pub = json.loads(PUBLIC.read_text(encoding="utf-8"))
        cat["tables"] = cat["tables"] + pub.get("tables", [])
    return cat


def get_table(cat: dict, tid: str) -> dict:
    for t in cat["tables"]:
        if t["id"] == tid:
            return t
    raise KeyError(f"명세서에 없는 표: {tid}")


def ref_rows(table: dict, keyword: str) -> list[list[str]]:
    for r in table.get("references", []):
        if keyword in r["title"]:
            return r["rows"]
    return []


def enum_from_note(note: str) -> list[str]:
    """비고의 '도시, 읍면' 또는 '7개 권역 (a, b, c)' 같은 목록을 값 목록으로."""
    i = note.find("(")
    text = note[i + 1:note.rfind(")")] if i >= 0 and "," in note[i:] else note
    parts = [p.strip() for p in text.split(",")]
    if len(parts) >= 2 and all(0 < len(p) <= 12 for p in parts):
        return parts
    return []


def _city_of(bjd: str, emd_names: list[str]) -> str:
    if bjd.endswith(("읍", "면")):
        for n in emd_names:
            if n.endswith(" " + bjd):
                return n.split()[0]
    return "서귀포시" if bjd in SEOGWIPO_DONG else "제주시"


def _region_of(place: str, city: str, regions: list[str]) -> str:
    """권역 배정(가상, 근사치): 같은 시의 권역 중 이름 해시로 고정 배정."""
    cand = [r for r in regions if r.startswith(city)]
    if not cand:
        return ""
    return cand[zlib.crc32(place.encode("utf-8")) % len(cand)]


# 월별 계절 지수: 제주데이터허브 597 실데이터(2017~2018)의 (도심/읍면 × 관광객/도민) 달별 평균 = 1.
# 읍면 관광객은 8월 최고·2월 최저(1.85배), 도심 도민은 1.16배로 고른 편 → 가상 데이터도 같은 모양을 따른다.
SEASON = {
    ("도심", False): {1: .977, 2: .831, 3: .951, 4: 1.071, 5: 1.087, 6: 1.05, 7: 1.107, 8: 1.172, 9: .991,
                    10: 1.009, 11: .943, 12: .81},
    ("도심", True): {1: 1.006, 2: .926, 3: 1.008, 4: .986, 5: 1.058, 6: .998, 7: 1.042, 8: 1.018, 9: 1.045,
                   10: 1.005, 11: .997, 12: .911},
    ("읍면", False): {1: .83, 2: .719, 3: .874, 4: 1.067, 5: 1.103, 6: 1.093, 7: 1.14, 8: 1.329, 9: 1.061,
                    10: 1.066, 11: .917, 12: .801},
    ("읍면", True): {1: .923, 2: .861, 3: .961, 4: .962, 5: 1.046, 6: .987, 7: 1.052, 8: 1.093, 9: 1.082,
                   10: 1.03, 11: 1.001, 12: 1.0},
}


def _season(month: int, local: bool = False, area: str = "도심") -> float:
    return SEASON[(area, local)][month]


def _months(spec: str) -> list[str]:
    a, b = spec.split("-")
    rng = pd.period_range(pd.Period(a, "M"), pd.Period(b, "M"), freq="M")
    return [p.strftime("%Y%m") for p in rng]


WEEK = (["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "공휴일"],
        [1.0, 0.95, 0.95, 1.0, 1.15, 1.35, 1.25, 0.3])
TIMESLOT = (["오전", "점심", "오후", "저녁", "밤"], [0.7, 1.3, 1.0, 1.2, 0.4])
# 업종별 시간대 모양(가상, 순서는 TIMESLOT과 같음). 없는 업종은 TIMESLOT 기본값(카페 등 점심 집중).
# 시간대 길이가 달라(오전·오후·저녁 4시간, 점심 3시간, 밤 9시간) 1시간당으로 보면 아래처럼 앞서는 때가 정해진다.
TIME_BY_BIZ = (
    (("호텔업", "여관업", "휴양콘도 운영업"), [0.9, 0.5, 1.8, 1.1, 0.5]),                 # 체크인하는 오후
    (("한식 음식점업", "중식 음식점업", "일식 음식점업", "서양식 음식점업", "기타 외국식 음식점업",
      "피자, 햄버거, 샌드위치 및 유사 음식점업"), [0.3, 1.2, 0.6, 2.0, 0.5]),             # 저녁(점심도 큼)
    (("일반유흥 주점업", "기타 주점업"), [0.05, 0.15, 0.2, 1.1, 3.6]),                     # 밤
    (("자동차 임대업", "정기 항공 운송업", "여행사업", "버스 운송업", "택시 운송업", "내항 여객 운송업",
      "골프장 운영업"), [1.8, 0.9, 1.0, 0.6, 0.2]),                                       # 오전
    (("체인화 편의점", "슈퍼마켓", "기타 대형 종합 소매업", "기타음식료품위주종합소매업"), [0.9, 1.0, 1.1, 1.4, 1.2]),  # 저녁
    (("면세점", "관광 민예품 및 선물용품 소매업", "화장품 및 방향제 소매업"), [0.6, 1.1, 1.8, 0.9, 0.1]),           # 오후
)


def _crc(text: str) -> int:
    return zlib.crc32(text.encode("utf-8")) % 100


def _col(values: list, idx: np.ndarray) -> pd.Series:
    """값 목록 + 번호 배열 → 문자열 열. pyarrow(Streamlit 설치 시 함께 설치됨)가 있으면 수십 배 빠르다."""
    try:
        import pyarrow as pa
        arr = pa.DictionaryArray.from_arrays(pa.array(np.asarray(idx, dtype=np.int32)),
                                             pa.array([str(v) for v in values], type=pa.large_string()))
        return pd.Series(arr.dictionary_decode(), dtype="str")
    except ImportError:
        return pd.Series(np.array([str(v) for v in values], dtype=object)[idx], dtype="str")


def gen_card_bjd(table: dict, months: list[str], seed: int = 42, emd_names: list[str] | None = None,
                 extra: tuple[str, tuple[list[str], list[float]]] | None = None,
                 bjd_fallback: list[str] | None = None, only: set[tuple[str, str]] | None = None) -> pd.DataFrame:
    """카드 이용 현황(읍면동)_v01/v02 형식(1-07, 1-08). extra로 요일(1-12)·시간대(1-14) 축을 더한다.

    행을 하나씩 만들지 않고 배열로 한 번에 만든다(1-12 기준 약 60만 행을 1초 안에).
    LLM은 쓰지 않는다. 같은 seed면 같은 결과.
    """
    rng = np.random.default_rng(seed)
    cols = [c["name"] for c in table["columns"]]
    note = {c["name"]: c["note"] for c in table["columns"]}
    bjds = [r[0] for r in ref_rows(table, "법정동")] or list(bjd_fallback or [])
    biz = [(r[0], r[1]) for r in ref_rows(table, "업종")]
    ages = [r[0] for r in ref_rows(table, "연령대")]
    regions = enum_from_note(note.get("dstrct_se", ""))
    user_types = enum_from_note(note.get("user_type", "")) or ["내국인", "제주도민"]
    emd_names = emd_names or []
    if extra:
        dim_vals, wts = extra[1]
        dim_w = [w / sum(wts) * len(wts) for w in wts]
    else:
        dim_vals, dim_w = [None], [1.0]

    # 1) 있는 (동, 업종, 이용자 구분, 요일·시간대) 조합 — 달마다 바뀌지 않게 이름 해시로 고정
    combos = []
    for bi, bjd in enumerate(bjds):
        for zi, (code, name) in enumerate(biz):
            if only is not None and (bjd, name) not in only:
                continue
            demo = (bjd, name) in DEMO_PRESENT or only is not None   # 시연 시나리오·실제 가게가 있는 조합은 항상 존재
            if not demo and _crc(f"{bjd}|{code}|{seed}") >= 80:
                continue
            for ui, ut in enumerate(user_types):
                if not demo and ut not in ("내국인", "제주도민") and _crc(f"{bjd}|{code}|{ut}|{seed}") >= 70:
                    continue                                  # 도민·내국인은 늘 있음(빠지면 '관광객 100%' 같은 이상한 체험 결과)
                for di, dv in enumerate(dim_vals):
                    if extra and not demo and ut not in ("내국인", "제주도민") \
                            and _crc(f"{bjd}|{code}|{ut}|{dv}|{seed}") >= 80:   # 손님이 적은 구분만 요일·시간대가 비기도 함
                        continue
                    combos.append((bi, zi, ui, di))
    if not combos or not months:
        return pd.DataFrame(columns=cols)
    C = np.asarray(combos)
    K, M = len(C), len(months)
    mi = np.repeat(np.arange(M), K)                     # 달 → 동 → 업종 → 이용자 → 축 순서
    bi, zi, ui, di = (np.tile(C[:, j], M) for j in range(4))
    n = len(mi)

    # 2) 조합별 기준값(가상): 계절성 × 관광지 가중치 × 이용자 구분 × 요일·시간대 가중치
    is_local = np.array([u in ("제주도민", "법인") for u in user_types])[ui]
    rural = np.array([b.endswith(("읍", "면")) for b in bjds])[bi]
    mon = np.array([int(ym[4:]) for ym in months])[mi]
    season = np.ones(n)
    for (area, local), prof in SEASON.items():        # (도심/읍면, 관광객/도민) 조합마다 597의 달별 모양
        sel = (rural == (area == "읍면")) & (is_local == local)
        season[sel] = np.array([prof[m] for m in range(1, 13)])[mon[sel] - 1]
    tw = np.array([TOURIST_WEIGHT.get(b, 1.0) for b in bjds])[bi]
    base_ut = {"제주도민": (60, 0), "내국인": (0, 45), "법인": (6, 0), "중국": (0, 5), "일본": (0, 2),
               "동남아": (0, 2), "기타외국": (0, 2)}
    fixed = np.array([base_ut.get(u, (5, 0))[0] for u in user_types], dtype=float)[ui]
    per_tw = np.array([base_ut.get(u, (5, 0))[1] for u in user_types], dtype=float)[ui]
    base = fixed + per_tw * tw
    dw = np.array(dim_w)[di]
    # 한 행은 수백 명의 결제를 합친 값이라 달마다 흔들림이 작다 → 잡음을 작게 두어 계절 모양이 드러나게 한다.
    lam = 5 * base * season * dw * rng.uniform(.97, 1.03, n) / (len(dim_vals) ** .5)
    users = np.maximum(1, rng.poisson(lam))
    if extra and extra[0] == "time":                 # 업종별 시간대 모양 — 뽑기 뒤에 곱해 다른 업종 값(난수 순서)은 그대로
        prof = {}
        for names, w in TIME_BY_BIZ:
            for nm in names:
                prof[nm] = [x / sum(w) * len(w) for x in w]
        fac = np.ones((len(biz), len(dim_vals)))
        for zi_, (_, name) in enumerate(biz):
            if name in prof:
                fac[zi_] = np.array(prof[name]) / np.array(dim_w)
        users = np.maximum(1, np.round(users * fac[zi, di]).astype(np.int64))
    uses = np.maximum(users, np.round(users * rng.normal(1.3, .03, n)).astype(np.int64))
    ticket = np.array([TICKET.get(name, 30_000) for _, name in biz], dtype=float)[zi]
    amt = (uses * ticket * rng.uniform(.97, 1.03, n)).astype(np.int64)

    # 3) 관광객 구분·연령·성별(법인은 NA·알수없음) — 값 목록의 번호로 만든다
    corp = ui == (user_types.index("법인") if "법인" in user_types else -1)
    local = ui == (user_types.index("제주도민") if "제주도민" in user_types else -1)
    tour = np.where(rng.random(n) < .85, 0, 1)                     # 개별, 단체
    tour[local], tour[corp] = 2, 3                                  # 도민, NA
    age_vals = ages + ["NA"]
    age = rng.integers(0, max(1, len(ages)), n) if ages else np.zeros(n, dtype=int)
    age[corp] = len(age_vals) - 1
    sex = np.where(rng.random(n) < .5, 0, 1)                         # 남성, 여성
    sex[corp] = 2                                                   # 알수없음

    city = [_city_of(b, emd_names) for b in bjds]
    data = {
        "base_year_month": _col(months, mi), "pt_year": _col([m[:4] for m in months], mi),
        "pt_month": _col([str(int(m[4:])) for m in months], mi),
        "dstrct_se": _col([_region_of(b, c, regions) for b, c in zip(bjds, city)], bi),
        "city": _col(city, bi), "area_type": _col(["읍면" if b.endswith(("읍", "면")) else "도시" for b in bjds], bi),
        "bjd": _col(bjds, bi), "biz_cd": _col([c for c, _ in biz], zi), "biz_nm": _col([nm for _, nm in biz], zi),
        "user_type": _col(user_types, ui), "tour_type": _col(["개별", "단체", "도민", "NA"], tour),
        "age": _col(age_vals if ages else ["NA"], age), "sex": _col(["남성", "여성", "알수없음"], sex),
        "user_cnt": users.astype(np.int64), "use_cnt": uses.astype(np.int64), "use_amt": amt,
    }
    if extra:
        data[extra[0]] = _col(dim_vals, di)
    df = pd.DataFrame(data)
    return df[[c for c in cols if c in df.columns]]


def gen_floating_pop_emd(table: dict, days: list[str], seed: int = 42) -> pd.DataFrame:
    """내국인 유동인구(읍면동)_v02 형식(4-11). 시간·성별·연령·거주지별 인구(소수점)."""
    rng = np.random.default_rng(seed)
    cols = [c["name"] for c in table["columns"]]
    note = {c["name"]: c["note"] for c in table["columns"]}
    emds = ref_rows(table, "행정동")
    ages = [r[0] for r in ref_rows(table, "연령대") if len(r) < 3 or r[2] == "SKT"]
    regions = enum_from_note(note.get("dstrct_se", ""))
    rows = []
    for d in days:
        s = _season(int(d[4:6]))
        for code, name in emds:
            city, emd = name.split()[0], name.split()[-1]
            region = _region_of(emd, city, regions)
            tw = TOURIST_WEIGHT.get(emd, 1.0)
            for h in range(1, 25):
                day_curve = 0.4 + 0.6 * np.exp(-((h - 14) / 5) ** 2)
                for sex in ("남성", "여성"):
                    for age in ages:
                        for resd in ("제주", "그외"):
                            base = 120 if resd == "제주" else 25 * tw * s
                            resd_pop = base * rng.uniform(.5, 1.5) * (1.2 - 0.4 * day_curve)
                            work_pop = base * .3 * day_curve * rng.uniform(.5, 1.5)
                            visit_pop = base * .5 * day_curve * tw * rng.uniform(.5, 1.5)
                            rows.append({
                                "base_date": d, "pt_year": d[:4], "pt_month": str(int(d[4:6])), "time": str(h),
                                "dstrct_se": region, "emd_cd": code, "emd_nm": name, "sex": sex, "age": age,
                                "resd_pop_cnt": f"{resd_pop:.4f}", "work_pop_cnt": f"{work_pop:.4f}",
                                "visit_pop_cnt": f"{visit_pop:.4f}", "resd": resd,
                            })
    df = pd.DataFrame(rows)
    return df[[c for c in cols if c in df.columns]]


GENERATORS = {"1-07": "card_bjd", "1-08": "card_bjd", "1-12": "card_week", "1-14": "card_time", "4-11": "pop_emd"}


def _store_backed(min_stores: int = 3) -> set[tuple[str, str]]:
    """동봉한 상가정보(실제)에 같은 업종 가게가 min_stores곳 이상 있는 (법정동, 카드 업종)."""
    files = sorted((Path(__file__).resolve().parents[1] / "data" / "public").glob("상가정보_제주_*.csv"))
    if not files:
        return set()
    d = pd.read_csv(files[-1], dtype={"card_biz": str}, encoding="utf-8-sig").dropna(subset=["card_biz"])
    g = d.groupby(["bjd", "card_biz"])["store_cnt"].sum()
    return {k for k, v in g.items() if v >= min_stores}


def generate(tid: str, period: str, seed: int = 42, cat: dict | None = None) -> pd.DataFrame:
    cat = cat or load_catalog()
    t = get_table(cat, tid)
    kind = GENERATORS.get(tid)
    if kind in ("card_bjd", "card_week", "card_time"):
        emd = [r[1] for r in ref_rows(get_table(cat, "4-11"), "행정동")]
        extra = {"card_week": ("week", WEEK), "card_time": ("time", TIMESLOT)}.get(kind)
        # 1-12·1-14 명세서에는 법정동 코드표가 없어 1-08의 법정동 73개를 쓴다.
        bjds = [r[0] for r in ref_rows(get_table(cat, "1-08"), "법정동")]
        months = _months(period)
        main = gen_card_bjd(t, months, seed, emd, extra, bjds)
        # 실제 상가정보에 가게가 있는 (동, 업종)인데 위에서 빠진 조합은 따로 만들어 붙인다(시드를 달리해
        # 기존 행의 값은 그대로 둔다). 예: 조천읍 양식당 44곳인데 가상 매출이 없으면 '함덕 브런치' 질문이 빈 답이 됨.
        biz = {name: code for code, name in ((r[0], r[1]) for r in ref_rows(get_table(cat, "1-08"), "업종"))}
        miss = {(b, n) for b, n in _store_backed() if b in bjds and n in biz and (b, n) not in DEMO_PRESENT
                and _crc(f"{b}|{biz[n]}|{seed}") >= 80}
        if not miss:
            return main
        add = gen_card_bjd(t, months, seed + 7919, emd, extra, bjds, only=miss)
        return pd.concat([main, add], ignore_index=True)
    if kind == "pop_emd":
        a, b = period.split("-")
        days = [d.strftime("%Y%m%d") for d in pd.date_range(a, b, freq="D")]
        return gen_floating_pop_emd(t, days, seed)
    raise NotImplementedError(f"{tid} 가상 데이터 생성기는 아직 없습니다. 지원: {', '.join(GENERATORS)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="센터 명세서 기반 가상 CSV 생성")
    ap.add_argument("table", help="표 번호(예: 1-08)")
    ap.add_argument("--period", required=True, help="월 단위 표: 202505-202604 / 일 단위 표: 20260401-20260407")
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--encoding", default="utf-8-sig", help="utf-8-sig(기본) 또는 cp949")
    a = ap.parse_args()
    df = generate(a.table, a.period, a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t = get_table(load_catalog(), a.table)
    path = out / f"[가상]{a.table}_{t['name']}_{a.period}.csv"
    df.to_csv(path, index=False, encoding=a.encoding)
    print(f"{path} ({len(df):,}행, {len(df.columns)}열)")


if __name__ == "__main__":
    main()
