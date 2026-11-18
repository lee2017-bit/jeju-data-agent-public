"""제주데이터허브 Open API 받기 — 공개 데이터를 Agent가 직접 받아 CSV로 저장(운영진 허용, 2026-10-31 답변).

- 키: 환경변수 JEJUDATAHUB_APP_KEY 또는 운영자 설정. 제출물에는 넣지 않는다.
- 응답: {"totCnt", "hasMore", "data": [...]}, 페이지당 최대 100건. 값 앞뒤 공백은 지운다.
- 센터 데이터(반출 불가)와 달리 공개 데이터이므로 외부 전송·반출 제약이 없다.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


def build_url(api: dict, app_key: str, params: dict) -> str:
    q = urllib.parse.urlencode(params)
    return f"{api['base']}{api['api_id']}/{urllib.parse.quote(app_key, safe='')}?{q}"


def fetch_all(table: dict, app_key: str | None = None, start: str = "201601", end: str = "202112",
              filters: dict | None = None, opener=urllib.request.urlopen, pause: float = 0.2,
              max_pages: int = 500, progress=None) -> pd.DataFrame:
    api = table["api"]
    key = app_key or os.environ.get("JEJUDATAHUB_APP_KEY", "")
    if not key:
        raise ValueError("제주데이터허브 프로젝트키가 없습니다(JEJUDATAHUB_APP_KEY).")
    rows: list[dict] = []
    total = None
    for page in range(1, max_pages + 1):
        params = {"startDate": start, "endDate": end, api.get("page_param", "number"): page,
                  api.get("limit_param", "limit"): api.get("max_limit", 100), **(filters or {})}
        with opener(build_url(api, key, params), timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        batch = data.get("data") or []
        total = data.get("totCnt", total)
        rows.extend(batch)
        if progress:
            progress(len(rows), total)
        if not data.get("hasMore") or not batch:
            break
        time.sleep(pause)
    df = pd.DataFrame(rows)
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]):
            df[c] = df[c].astype(str).str.strip()
    cols = [c["name"] for c in table["columns"] if c["name"] in df.columns]
    return df[cols + [c for c in df.columns if c not in cols]]


def save_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path
