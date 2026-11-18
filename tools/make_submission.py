"""제출용 zip 만들기: git에 올라간 파일만 묶는다(.env·운영자 설정·AI 사용 기록·실행 결과·.venv는 원래 git에 없어 들어가지 않음).

    python tools/make_submission.py          → dist/제주사장님상권비서_제출_YYYYMMDD.zip

- 내부 작업 메모(docs/research, CLAUDE.md)는 뺀다.
- 맨 위 '제출문서/'에 PDF 4종(기획서·결과 설명자료·데이터 활용 명세서·사용자 매뉴얼)을 한 번 더 넣어 바로 찾게 한다.
- 키처럼 보이는 문자열이 있으면 멈춘다(실수로 커밋한 키가 제출물에 들어가지 않게).
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = "jeju-data-agent"
EXCLUDE = ("docs/research/", "CLAUDE.md")
DOCS = {
    "제출문서/1_기획서.pdf": "docs/proposal/기획서.pdf",
    "제출문서/2_결과_설명자료.pdf": "docs/submission/결과_설명자료.pdf",
    "제출문서/3_데이터_활용_명세서.pdf": "docs/submission/데이터_활용_명세서.pdf",
    "제출문서/4_사용자_매뉴얼.pdf": "docs/submission/사용자_매뉴얼.pdf",
}
SECRET = re.compile(rb"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{20,}|serviceKey=[A-Za-z0-9%+/=]{20,}|(?<![A-Z0-9])AKIA[0-9A-Z]{16}")
TEXT_EXT = {".py", ".md", ".txt", ".json", ".toml", ".bat", ".ps1", ".html", ".css", ".csv", ".example", ""}


def tracked() -> list[str]:
    out = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return [p for p in out.stdout.decode("utf-8").split("\0") if p and not p.startswith(EXCLUDE)]


def main() -> int:
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, capture_output=True,
                           text=True).stdout.strip()
    if dirty:
        print("주의: 커밋하지 않은 변경이 있습니다. zip에는 지금 디스크의 내용이 들어갑니다.\n" + dirty)
    files = tracked()
    leaks = [p for p in files if (ROOT / p).suffix in TEXT_EXT and SECRET.search((ROOT / p).read_bytes())]
    if leaks:
        print("키처럼 보이는 문자열이 있어 멈춥니다: " + ", ".join(leaks))
        return 1
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    out = dist / f"제주사장님상권비서_제출_{date.today():%Y%m%d}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(ROOT / p, f"{TOP}/{p}")
        for arc, src in DOCS.items():
            if (ROOT / src).exists():
                z.write(ROOT / src, f"{TOP}/{arc}")
            else:
                print(f"없음(빠짐): {src}")
    mb = out.stat().st_size / 1e6
    print(f"{out} — 파일 {len(files) + len(DOCS)}개, {mb:.1f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
