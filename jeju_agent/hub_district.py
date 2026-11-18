"""제주데이터허브 '관광지 및 상업지구' 카드 데이터(실제 공개 데이터) — 지구 유형별 요일·시간대·손님 구성.

- 원본(사용자가 PC에서 get_hub.bat으로 받아 첨부, 2026-11-04): data/public/허브_요일별·시간대별·이용자유형별_카드_*.csv
  기간 2016.09~2017.11(15개월). 지구 5종: 상업지, 내국인 주요 관광지, 중국인 주요 관광지, 제주시 구도심, 서귀포시 구도심.
  요일·시간대는 내국인관광객·중국인관광객만, 이용자유형은 법인·제주도민·내국인관광객·중국인관광객.
- 앱에서는 세 파일을 한 표(허브-지구)로 합쳐 쓴다: districtType, dim(요일·시간대·이용자), cat, userType, dtYearMonth, useCost.
- 질문한 동네가 어느 지구에 속하는지는 원자료에 없다. 그래서 '가장 가까운 지구 유형'을 정해(읍면·중문관광단지 일대 → 내국인 주요 관광지,
  제주시 원도심 동 → 제주시 구도심, 그 밖 제주시 동 → 상업지, 서귀포시 동 → 서귀포시 구도심) 화면에 '추정'이라고 적는다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data" / "public"
DISTRICT_ID = "허브-지구"
DISTRICTS = ["내국인 주요 관광지", "중국인 주요 관광지", "상업지", "제주시 구도심", "서귀포시 구도심"]
WEEK = ["월", "화", "수", "목", "금", "토", "일"]
SLOTS = ["오전", "점심", "오후", "저녁", "밤"]
OLD_TOWN = ("일도", "이도", "삼도", "건입", "용담")          # 제주시 원도심(구도심) 동
RESORT = ("중문동", "색달동", "대포동")                       # 서귀포 중문관광단지 일대 → 관광지형으로 추정


def closest_district(regions: list[str], city_of) -> str | None:
    """질문한 동네와 가장 가까운 지구 유형(추정). 동네가 없으면 None."""
    if not regions:
        return None
    r = regions[0]
    if r.endswith(("읍", "면")) or r in RESORT:
        return "내국인 주요 관광지"
    if city_of(r) == "서귀포시":
        return "서귀포시 구도심"
    return "제주시 구도심" if r.startswith(OLD_TOWN) else "상업지"


def _latest(kind: str) -> Path | None:
    files = sorted(PUBLIC_DIR.glob(f"허브_{kind}_카드_*.csv"))
    return files[-1] if files else None


def combined() -> pd.DataFrame | None:
    parts = []
    for kind, dim, col in (("요일별", "요일", "dtWeek"), ("시간대별", "시간대", "dateTimeCategory"),
                           ("이용자유형별", "이용자", "userType")):
        p = _latest(kind)
        if p is None:
            continue
        d = pd.read_csv(p, dtype=str, encoding="utf-8-sig")
        d = d.apply(lambda s: s.str.strip())
        out = pd.DataFrame({"districtType": d["districtType"], "dim": dim, "cat": d[col],
                            "userType": d["userType"] if dim != "이용자" else "전체",
                            "dtYearMonth": d["dtYearMonth"], "useCost": pd.to_numeric(d["useCost"], errors="coerce")})
        parts.append(out)
    return pd.concat(parts, ignore_index=True) if parts else None


def load_district(cat: dict):
    from .loader import from_frame
    df = combined()
    return None if df is None else from_frame(df, DISTRICT_ID, cat)
