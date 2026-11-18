"""체험(시연) 데이터 한 번에 불러오기.

- 센터 표(1-08·1-12·1-14 등): 명세서와 같은 형식의 가상 데이터를 파이썬 계산으로 만든다(LLM 아님, 1초 안팎).
- 공개 데이터(제주데이터허브 597): 저장소에 동봉한 실제 CSV(data/public)를 쓴다.
센터 PC에서 진짜 데이터를 받으면 같은 표 번호로 바꿔 끼우면 된다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .loader import LoadedTable, from_frame, load_center_csv
from .planner import PUBLIC_ID, Plan
from .synth import GENERATORS, generate

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data" / "public"
DEMO_PERIOD = "202505-202604"      # 센터 카드 데이터 제공 시작(2025.05)부터 12개월
DEMO_SEED = 11


def bundled_public() -> Path | None:
    files = sorted(PUBLIC_DIR.glob("허브597_*.csv"))
    return files[-1] if files else None


def load_public(cat: dict) -> LoadedTable | None:
    path = bundled_public()
    if not path:
        return None
    lt = load_center_csv(path, cat)
    return lt if lt.table_id == PUBLIC_ID else None


def synthetic_table(tid: str, cat: dict, period: str = DEMO_PERIOD, seed: int = DEMO_SEED) -> LoadedTable:
    lt = from_frame(generate(tid, period, seed=seed, cat=cat), tid, cat, synthetic=True)
    _compact(lt)
    return lt


def _compact(lt: LoadedTable) -> None:
    """글자 열(동네·업종·요일 등 값 종류가 적은 열)을 범주형으로 바꿔 메모리를 줄인다(요일표 약 250MB → 수십 MB).
    무료 호스팅(메모리 약 1~2.7GB)에서 여러 사람이 써도 버티게 하려는 것. 값과 결과는 그대로다."""
    df = lt.df
    n = max(len(df), 1)
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique(dropna=False) <= max(50, n // 100):
            df[c] = df[c].astype("category").cat.as_ordered()   # 범주는 글자 순으로 정렬됨 → 최솟값·정렬이 글자와 같음


def demo_tables(plan: Plan, cat: dict, have: set[str] | None = None) -> dict[str, LoadedTable]:
    """계획에 필요한 표 중 아직 없는 것을 모두 채운다. 반환: {표 번호: LoadedTable}"""
    have = have or set()
    out: dict[str, LoadedTable] = {}
    for r in plan.requests:
        if r.table_id not in have and r.table_id in GENERATORS:
            out[r.table_id] = synthetic_table(r.table_id, cat)
    if PUBLIC_ID not in have:
        pub = load_public(cat)
        if pub is not None:
            out[PUBLIC_ID] = pub
    return out
