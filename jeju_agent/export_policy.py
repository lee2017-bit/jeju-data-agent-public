"""제주빅데이터센터 데이터 반출 정책(2026.09.01 개정)을 코드로 옮긴 점검기.

근거: reference/center-export-policy_2026-09-01.pdf

정책 요지
- 반출 불가 데이터(카드·외식업 POS·탐나는전·기업·유동인구 등)
  - 원본·발췌: 반출 불가
  - 단순집계(합계·평균·최소·최대·중앙값·영역 내 개수 등): 10 미만 수치가 없을 때만 가능
    (처리방법: 범주처리 / 삭제처리 / 비식별처리)
  - 응용집계(차이·증감율·비율·순위·범주·지수·모델링 결과·검정값): 수치 포함 반출 가능
  - 시각화: PNG/JPG만, 그림 안의 수치도 위 기준을 따름
  - 민간 제공처 데이터는 원칙적으로 텍스트·스프레드시트(csv, txt, 엑셀) 반출 불가
- 반출 가능 데이터(버스·교통량·와이파이·날씨·쓰레기 등): 원본부터 모두 가능
- 공통: 소스코드에 데이터 샘플 출력(head() 등)이 있으면 반출 불가,
  반출 신청 시 자료마다 출처(원본데이터 명칭)와 활용 사유 기재 필수

해석이 갈리는 부분(정책 4쪽 "제공단위 총합·평균도 원칙적으로 반출 불가" vs 10쪽 "10 미만 미포함 시 가능")은
엄격하게 해석한다: 반출 불가 데이터의 단순집계는 '조건부'로 표시하고 응용집계·그림을 우선 권장한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import pandas as pd

THRESHOLD = 10
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


class Kind(str, Enum):
    RAW = "원본"
    EXTRACT = "발췌"
    SIMPLE_AGG = "단순집계"
    APPLIED_AGG = "응용집계"
    CHART = "시각화"


class Verdict(str, Enum):
    OK = "반출 가능"
    CONDITIONAL = "조건부(심사 필요)"
    BLOCKED = "반출 불가"


@dataclass
class Check:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)


def is_restricted(table: dict) -> bool:
    """명세서 기준 원본 반출 불가 표인지."""
    return not table.get("raw_export_allowed", False)


def judge(kind: Kind, tables: list[dict], file_ext: str | None = None) -> Check:
    """산출물 종류와 사용한 표 목록으로 반출 가능성을 1차 판정한다."""
    restricted = [t["id"] for t in tables if is_restricted(t)]
    if not restricted:
        return Check(Verdict.OK, ["사용한 데이터가 모두 원본 반출 가능 데이터입니다."])

    names = ", ".join(restricted)
    if kind in (Kind.RAW, Kind.EXTRACT):
        return Check(Verdict.BLOCKED, [f"반출 불가 데이터({names})의 {kind.value}은 반출할 수 없습니다."])

    text_like = file_ext is not None and file_ext.lower() not in IMAGE_EXTS
    if kind == Kind.CHART:
        if file_ext is None or file_ext.lower() not in IMAGE_EXTS:
            return Check(Verdict.BLOCKED, ["시각화는 PNG 또는 JPG 그림 파일로만 반출할 수 있습니다."])
        return Check(Verdict.CONDITIONAL, ["그림 안에 표시된 수치도 반출 기준(10 미만 불가)을 따라야 합니다."])

    if kind == Kind.APPLIED_AGG:
        reasons = ["응용집계(비율·증감율·순위·지수 등)는 수치를 포함해 반출할 수 있습니다."]
        if text_like:
            reasons.append("민간 제공처 데이터는 원칙적으로 텍스트·엑셀 반출이 불가하므로 보고서·그림 형태를 권장합니다.")
            return Check(Verdict.CONDITIONAL, reasons)
        return Check(Verdict.OK, reasons)

    # SIMPLE_AGG
    reasons = [
        "단순집계는 10 미만 수치가 없어야 반출할 수 있습니다.",
        "정책 4쪽은 반출 불가 데이터의 제공단위 총합·평균도 원칙적으로 반출 불가로 보므로 심사가 필요합니다.",
    ]
    if text_like:
        reasons.append("민간 제공처 데이터는 원칙적으로 텍스트·엑셀 반출이 불가합니다.")
    return Check(Verdict.CONDITIONAL, reasons)


@dataclass
class SuppressionResult:
    data: pd.DataFrame
    suppressed_cells: int
    dropped_rows: int
    method: str


def suppress_small_values(df: pd.DataFrame, value_cols: list[str], method: str = "mask",
                          threshold: int = THRESHOLD) -> SuppressionResult:
    """단순집계 표에서 10 미만 수치를 처리한다.

    method:
      - "mask": 해당 칸을 비우고 '10 미만'으로 표기(비식별처리)
      - "drop": 10 미만 수치가 하나라도 있는 행을 삭제(삭제처리)
    0은 '해당 없음'이 아니라 실제 값이므로 함께 처리한다.
    """
    out = df.copy()
    small = pd.DataFrame(False, index=out.index, columns=value_cols)
    for c in value_cols:
        s = pd.to_numeric(out[c], errors="coerce")
        small[c] = s.notna() & (s.abs() < threshold)
    n_cells = int(small.to_numpy().sum())

    if method == "drop":
        mask_rows = small.any(axis=1)
        out = out.loc[~mask_rows].reset_index(drop=True)
        return SuppressionResult(out, n_cells, int(mask_rows.sum()), "삭제처리")

    for c in value_cols:
        out[c] = out[c].astype("object")
        out.loc[small[c], c] = f"{threshold} 미만"
    return SuppressionResult(out, n_cells, 0, "비식별처리")


def find_small_values(df: pd.DataFrame, value_cols: list[str], threshold: int = THRESHOLD) -> int:
    n = 0
    for c in value_cols:
        s = pd.to_numeric(df[c], errors="coerce")
        n += int((s.notna() & (s.abs() < threshold)).sum())
    return n


_DATA_PRINT = re.compile(
    r"(\.head\s*\(|\.tail\s*\(|\.sample\s*\(|^\s*print\s*\(\s*\w*df\w*\s*\)|^\s*display\s*\(|^\s*\w*df\w*\s*$)",
    re.MULTILINE,
)


def code_has_data_print(code: str) -> bool:
    """반출할 코드에 데이터 샘플 출력이 남아 있는지(있으면 반출 불가)."""
    return bool(_DATA_PRINT.search(code))


def check_file_for_export(path: str | Path, tables: list[dict], kind: Kind) -> Check:
    p = Path(path)
    return judge(kind, tables, p.suffix)


def export_request_lines(items: list[dict]) -> list[str]:
    """반출 신청서용 문구. items: {file, tables:[{id,name}], period, purpose}"""
    lines = []
    for i, it in enumerate(items, 1):
        src = ", ".join(f"{t['name']}({t['id']})" for t in it["tables"])
        lines.append(
            f"{i}. 파일: {it['file']}\n"
            f"   출처(원본데이터 명칭): 제주빅데이터센터, {src}, 기간 {it.get('period', '미기재')}\n"
            f"   활용 사유: {it.get('purpose', '미기재')}"
        )
    return lines
