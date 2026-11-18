"""데이터 받는 길 안내: 표마다 '바로 열기' 링크·파일 경로·조회문, 운영자 사전 적재 폴더, 내려받기 폴더 자동 인식.

센터 시스템에 Agent가 직접 접속하는 방식은 허용되지 않는다(운영진 답변 2026-10-28).
그래서 이용자가 '찾지 않고 한 번에' 받을 수 있게 표마다 링크·경로를 설정 파일로 둔다.
센터의 실제 링크 구조는 아직 확인 전이라 운영자가 한 번 채워 넣는 구조로 만든다.

config/data_sources.json 예:
{
  "preload_dir": "C:/JejuDataAgent/data/preloaded",   # 운영자가 미리 넣어 둔 CSV
  "watch_dir": "~/Downloads",                        # 이용자가 내려받는 폴더
  "tables": {
    "1-08": {"url": "https://...{from_ym}...", "path": "", "query": "SELECT ... WHERE pt_year BETWEEN ..."}
  }
}
url·query 안의 {from_ym} {to_ym} {from_year} {to_year} {bjd} {biz_nm}는 질문에 맞게 채운다.
"""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .loader import ENCODINGS, identify_table

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "data_sources.json"


@dataclass
class DownloadGuide:
    table_id: str
    table_name: str
    url: str = ""
    path: str = ""
    query: str = ""
    file_name: str = ""
    steps: list[str] = field(default_factory=list)
    configured: bool = False


@dataclass
class FoundFile:
    path: Path
    table_id: str | None
    table_name: str
    score: float
    period: str = ""
    modified: float = 0.0


def load_config(path: Path = CONFIG) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"preload_dir": "", "watch_dir": "~/Downloads", "tables": {}}


def save_config(cfg: dict, path: Path = CONFIG) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def _fill(template: str, ctx: dict) -> str:
    out = template
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def guide_for(table: dict, cfg: dict, from_ym: str, to_ym: str, regions=None, business=None) -> DownloadGuide:
    tid = table["id"]
    entry = cfg.get("tables", {}).get(tid, {})
    ctx = {"from_ym": from_ym, "to_ym": to_ym, "from_year": from_ym[:4], "to_year": to_ym[:4],
           "bjd": ",".join(regions or []), "biz_nm": ",".join(business or [])}
    g = DownloadGuide(tid, table["name"], url=_fill(entry.get("url", ""), ctx), path=entry.get("path", ""),
                      query=_fill(entry.get("query", ""), ctx), configured=bool(entry))
    g.file_name = f"{tid}_{from_ym}-{to_ym}.csv"
    if g.url:
        g.steps.append("아래 '바로 열기'를 누르면 이 데이터 화면이 열립니다.")
    elif g.path:
        g.steps.append(f"파일 탐색기에서 이 위치를 엽니다: {g.path}")
    else:
        g.steps.append(f"센터 데이터 조회 화면의 데이터 목록에서 '{table['name']}'를 고릅니다(표 번호 {tid}).")
    if g.query:
        g.steps.append("'조회문 복사'를 눌러 조회 화면에 붙여 넣고 실행합니다.")
    else:
        g.steps.append(f"기간을 {from_ym[:4]}년 {int(from_ym[4:])}월 ~ {to_ym[:4]}년 {int(to_ym[4:])}월로 입력합니다(월 단위)."
                       " 조건(지역·업종)은 비워 두고 전체로 받으면 다른 질문에도 다시 쓸 수 있습니다.")
    g.steps.append("조회가 끝나면 CSV로 내려받습니다('내려받기' 폴더). 저장하면 이 화면이 자동으로 알아봅니다.")
    return g


def sniff_header(path: Path, max_bytes: int = 65536) -> tuple[list[str], str]:
    raw = path.open("rb").read(max_bytes)
    for enc in ENCODINGS:
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            # 잘린 마지막 글자 때문일 수 있으니 줄 단위로 한 번 더
            try:
                text = raw[: raw.rfind(b"\n")].decode(enc)
            except UnicodeDecodeError:
                continue
        first = text.splitlines()[0] if text else ""
        cols = [c.strip().strip('"') for c in first.split(",")]
        return cols, enc
    return [], ""


def _period(path: Path, enc: str, cols: list[str]) -> str:
    for c in ("base_year_month", "년월", "base_date", "날짜"):
        if c in cols:
            try:
                s = pd.read_csv(path, usecols=[c], dtype=str, encoding=enc)[c].dropna()
                return f"{s.min()}~{s.max()}" if len(s) else ""
            except Exception:
                return ""
    return ""


def scan_folder(folder: str | Path, catalog: dict, since: float = 0.0, with_period: bool = False,
                min_score: float = 0.6) -> list[FoundFile]:
    """폴더의 CSV를 훑어 명세서 표와 맞는 파일을 찾는다(헤더만 읽어 빠르게)."""
    if not str(folder or "").strip():          # 빈 설정이면 현재 폴더를 훑지 않는다
        return []
    p = Path(str(folder)).expanduser()
    if not p.is_dir():
        return []
    found = []
    for f in sorted(p.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        mt = f.stat().st_mtime
        if mt < since:
            continue
        cols, enc = sniff_header(f)
        if not cols:
            continue
        score, t, _ = identify_table(cols, catalog)[0]
        if score < min_score:
            continue
        found.append(FoundFile(f, t["id"], t["name"], score, _period(f, enc, cols) if with_period else "", mt))
    return found


def preloaded(cfg: dict, catalog: dict) -> dict[str, FoundFile]:
    """운영자 사전 적재 폴더에서 표별 가장 최근 파일."""
    out: dict[str, FoundFile] = {}
    for ff in scan_folder(cfg.get("preload_dir", ""), catalog, with_period=True):
        if ff.table_id and ff.table_id not in out:
            out[ff.table_id] = ff
    return out


def recent_downloads(cfg: dict, catalog: dict, minutes: int = 120) -> list[FoundFile]:
    return scan_folder(cfg.get("watch_dir", "~/Downloads"), catalog, since=time.time() - minutes * 60)


def visitor_files(paths: list[str], watch_dir: str) -> list[Path]:
    """퇴실 전에 지울 파일: 이 방문자가 내려받아 앱이 읽어 들인 CSV 중 내려받기 폴더 안에 아직 있는 것만.
    (폴더 밖 파일·CSV가 아닌 파일·앱이 읽지 않은 파일은 건드리지 않는다)"""
    root = Path(watch_dir or "~/Downloads").expanduser().resolve()
    out: list[Path] = []
    for f in paths:
        fp = Path(f).expanduser().resolve()
        if fp.suffix.lower() == ".csv" and fp.is_file() and fp.is_relative_to(root) and fp not in out:
            out.append(fp)
    return out


def delete_files(files: list[Path]) -> list[str]:
    """지우고, 지우지 못한 파일 이름을 돌려준다(다른 프로그램에서 열려 있는 경우 등)."""
    failed = []
    for f in files:
        try:
            f.unlink(missing_ok=True)
        except OSError:
            failed.append(f.name)
    return failed
