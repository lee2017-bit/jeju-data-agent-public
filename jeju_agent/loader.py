"""센터 CSV 읽기: 인코딩 판별, 'NA' 보존, 헤더 정리, 어느 표인지 자동 판별, 형 변환.

센터에서 받은 CSV의 헤더가 영문(컬럼명)인지 한글(라벨)인지, 인코딩이 UTF-8인지 CP949인지
아직 확인되지 않아 모두 받아들이도록 만든다.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .semantics import ColumnRole, table_roles

ENCODINGS = ("utf-8-sig", "cp949", "euc-kr")


@dataclass
class LoadedTable:
    df: pd.DataFrame
    table: dict | None
    score: float
    encoding: str
    roles: dict[str, ColumnRole] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    synthetic: bool = False      # 가상 데이터(시연용)면 True — 보고서에 '가상' 표시, 출처를 센터로 쓰지 않음

    @property
    def table_id(self) -> str | None:
        return self.table["id"] if self.table else None


def _read_bytes(src) -> bytes:
    if isinstance(src, (str, Path)):
        return Path(src).read_bytes()
    if hasattr(src, "getvalue"):
        return src.getvalue()
    return src.read()


def read_csv_any(src) -> tuple[pd.DataFrame, str]:
    raw = _read_bytes(src)
    last = None
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError as e:
            last = e
            continue
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, na_values=[""])
        df.columns = [str(c).strip() for c in df.columns]
        for c in df.columns:  # 공개 API 값에는 앞 공백이 붙어 있다(" 제주시")
            df[c] = df[c].str.strip()
        return df, enc
    raise ValueError(f"CSV 인코딩을 판별하지 못했습니다(UTF-8/CP949 아님): {last}")


def identify_table(columns: list[str], catalog: dict) -> list[tuple[float, dict, dict[str, str]]]:
    """컬럼 일치도로 표 후보를 점수순으로. 한글 라벨 헤더면 영문 이름으로 바꾸는 대응표도 함께 준다."""
    cols = {c.strip() for c in columns}
    out = []
    for t in catalog["tables"]:
        names = [c["name"].strip() for c in t["columns"]]
        labels = {c["label"].strip(): c["name"].strip() for c in t["columns"]}
        by_name = len(cols & set(names))
        by_label = len(cols & set(labels))
        if by_label > by_name:
            rename = {k: v for k, v in labels.items() if k in cols}
            hit = by_label
        else:
            rename, hit = {}, by_name
        union = len(cols | set(names)) if not rename else len(cols | set(labels))
        score = hit / union if union else 0.0
        out.append((score, t, rename))
    out.sort(key=lambda x: -x[0])
    return out


def coerce(df: pd.DataFrame, roles: dict[str, ColumnRole]) -> pd.DataFrame:
    df = df.copy()
    for c, r in roles.items():
        if c in df.columns and r.role == "measure" and not pd.api.types.is_numeric_dtype(df[c]):
            df[c] = pd.to_numeric(df[c].str.replace(",", "", regex=False), errors="coerce")
    return df


def normalize_values(df: pd.DataFrame, table: dict) -> tuple[pd.DataFrame, list[str]]:
    """명세서(목록)에 적어 둔 값 정리 규칙을 적용한다.

    - value_map: 같은 뜻의 다른 표기를 하나로(예: 597 연령대 '20 미만'·'20대미만' → '20대 미만')
    - total_values: 합계 행(예: 업종 '전체')은 다른 행과 더하면 두 번 세어지므로 뺀다
    """
    notes = []
    for col, mapping in (table.get("value_map") or {}).items():
        if col in df.columns:
            hit = df[col].isin(list(mapping))
            if hit.any():
                df[col] = df[col].replace(mapping)
                notes.append(f"{col}의 표기 차이를 하나로 맞췄습니다({', '.join(sorted(set(mapping)))} → "
                             f"{', '.join(sorted(set(mapping.values())))}).")
    for col, vals in (table.get("total_values") or {}).items():
        if col in df.columns:
            hit = df[col].isin(vals)
            if hit.any():
                df = df[~hit]
                notes.append(f"{col}='{'/'.join(vals)}' 합계 행 {int(hit.sum()):,}개는 중복 집계를 막으려고 뺐습니다.")
    return df, notes


def load_center_csv(src, catalog: dict, min_score: float = 0.6) -> LoadedTable:
    df, enc = read_csv_any(src)
    cands = identify_table(list(df.columns), catalog)
    score, table, rename = cands[0]
    notes = []
    if score < min_score:
        notes.append(f"명세서의 어느 표와도 충분히 일치하지 않습니다(최고 일치도 {score:.0%}: {table['id']} {table['name']}).")
        return LoadedTable(df, None, score, enc, notes=notes)
    if rename:
        df = df.rename(columns=rename)
        notes.append("한글 헤더를 명세서의 영문 컬럼명으로 바꿨습니다.")
    second = cands[1]
    if second[0] == score:
        notes.append(f"컬럼이 같은 표가 여럿입니다({table['id']}, {second[1]['id']}). 파일 이름이나 기간으로 확인이 필요합니다.")
    roles = table_roles(table)
    spec = [c["name"].strip() for c in table["columns"]]
    missing = [c for c in spec if c not in df.columns]
    extra = [c for c in df.columns if c not in spec]
    if missing:
        notes.append(f"명세서에 있는데 파일에 없는 컬럼: {', '.join(missing)}")
    df, vnotes = normalize_values(df, table)
    notes += vnotes
    df = coerce(df, roles)
    return LoadedTable(df, table, score, enc, roles, missing, extra, notes)


def from_frame(df: pd.DataFrame, table_id: str, catalog: dict, synthetic: bool = False) -> LoadedTable:
    """이미 메모리에 있는 표(가상 데이터 등)를 CSV로 다시 쓰고 읽지 않고 바로 불러온다."""
    table = next(t for t in catalog["tables"] if t["id"] == table_id)
    roles = table_roles(table)
    spec = [c["name"].strip() for c in table["columns"]]
    df, notes = normalize_values(df, table)
    lt = LoadedTable(coerce(df, roles), table, 1.0, "memory", roles,
                     [c for c in spec if c not in df.columns], [c for c in df.columns if c not in spec], notes)
    lt.synthetic = synthetic
    return lt
