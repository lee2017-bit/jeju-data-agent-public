"""제주빅데이터센터 데이터 명세서(xlsx)를 읽어 Agent가 쓰는 데이터 목록(JSON)을 만든다.

사용법:
    python tools/build_catalog.py reference/center-data-spec_v12_2026-01-28.xlsx catalog/center_catalog.json

명세서 시트 구조(v12 기준):
    - '목록' 시트: No / 카테고리 / 데이터명 / 반출 / 제공처
    - 표 시트: 5~8행 메타데이터(카테고리, 데이터명, 설명, 등록일자·반출·제공처),
      'No' 헤더 행 아래로 컬럼 명세, 그 아래 [참고n] 코드표
    - 참고표 시트: 첫 행 제목, 3행 헤더, 이후 코드 목록
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl


def _s(v) -> str:
    if v is None:
        return ""
    return str(v).replace("\r", "").strip()


def _find(row, label: str) -> str:
    """행에서 label 셀 다음에 오는 첫 값을 돌려준다."""
    for i, v in enumerate(row):
        if _s(v).replace(" ", "") == label.replace(" ", ""):
            for w in row[i + 1:]:
                if _s(w):
                    return _s(w)
    return ""


def parse_list_sheet(ws) -> dict[str, dict]:
    out: dict[str, dict] = {}
    category = ""
    for row in ws.iter_rows(values_only=True):
        cells = [_s(v) for v in row]
        no = cells[0] if cells else ""
        if not (re.fullmatch(r"\d-\d{2}", no) or no == "-"):
            continue
        rest = [c for c in cells[1:] if c]
        # 카테고리 셀은 그룹 첫 행에만 있다: '경제 (25)'
        if rest and re.match(r"^\S+\s*\(\d+\)$", rest[0]):
            category = re.sub(r"\s*\(\d+\)$", "", rest[0])
            rest = rest[1:]
        if len(rest) < 3:
            continue
        name, export, provider = rest[0], rest[1], rest[2]
        key = no if no != "-" else name
        out[key] = {"no": no, "category": category, "name": name,
                    "export_raw": export, "provider": provider}
    return out


def parse_table_sheet(ws) -> dict:
    rows = [tuple(r) for r in ws.iter_rows(values_only=True)]
    meta = {"category": "", "name": "", "description": "", "registered": "",
            "export_raw": "", "provider": ""}
    header_idx = None
    for i, row in enumerate(rows[:20]):
        cells = [_s(v) for v in row]
        joined = " ".join(cells)
        if not meta["category"] and _find(row, "카테고리"):
            meta["category"] = _find(row, "카테고리")
        if not meta["name"] and _find(row, "데이터명(한글)"):
            meta["name"] = _find(row, "데이터명(한글)")
        if not meta["description"] and _find(row, "설명"):
            meta["description"] = _find(row, "설명")
        if "등록일자" in joined:
            meta["registered"] = _find(row, "등록일자")[:10]
            meta["export_raw"] = _find(row, "반출")
            meta["provider"] = _find(row, "제공처")
        if cells and cells[0] == "No" and any("컬럼" in c or "Column" in c for c in cells[1:3]):
            header_idx = i
            break

    columns = []
    notes_start = None
    if header_idx is not None:
        for j in range(header_idx + 1, len(rows)):
            cells = [_s(v) for v in rows[j]]
            if not cells or not re.fullmatch(r"\d+", cells[0] or ""):
                if any(c.startswith("[참고") for c in cells if c):
                    notes_start = j
                    break
                if not any(cells):
                    continue
                notes_start = j
                break
            columns.append({
                "name": cells[1].strip(),
                "label": cells[2].strip(),
                "dtype": cells[3].strip().upper(),
                "example": cells[4].strip() if len(cells) > 4 else "",
                "note": " ".join(c for c in cells[5:] if c).strip(),
            })

    references = parse_reference_blocks(rows[notes_start:]) if notes_start is not None else []

    period = ""
    m = re.search(r"기간\s*:\s*([^\n]+)", meta["description"])
    if m:
        period = m.group(1).strip()
    meta["description"] = re.sub(r"\s+", " ", meta["description"].replace("-", " ").strip())
    return {**meta, "period": period, "columns": columns, "references": references}


def parse_reference_blocks(rows: list[tuple]) -> list[dict]:
    """컬럼 명세 아래의 [참고n] 코드표를 블록 단위로 읽는다.

    한 행에 여러 블록이 옆으로 나란히 놓여 있다:
        [참고1] 법정동 | | | [참고2] 업종코드 및 업종명 | ...
        No | 업종코드 |   | No | 업종코드 | 업종명 | ...
    블록 제목이 있는 열부터 다음 블록 제목 직전 열까지를 한 블록으로 본다.
    한 시트 안에 제목 행이 여러 번 나올 수 있다.
    """
    blocks: list[dict] = []
    i = 0
    while i < len(rows):
        cells = [_s(v) for v in rows[i]]
        starts = [j for j, c in enumerate(cells) if c.startswith("[참고")]
        if not starts:
            i += 1
            continue
        width = max(len(r) for r in rows)
        bounds = starts + [width]
        header = [_s(v) for v in rows[i + 1]] if i + 1 < len(rows) else []
        new_blocks = []
        for k, s in enumerate(starts):
            e = bounds[k + 1]
            cols = [(j, header[j]) for j in range(s, min(e, len(header))) if header[j]]
            new_blocks.append({"title": cells[s], "cols": cols, "rows": [], "open": True})
        j = i + 2
        while j < len(rows):
            rc = [_s(v) for v in rows[j]]
            if any(c.startswith("[참고") for c in rc):
                break
            for b in new_blocks:
                if not b["open"] or not b["cols"]:
                    continue
                vals = [rc[c] if c < len(rc) else "" for c, _ in b["cols"]]
                if any(vals):
                    b["rows"].append(vals)
                elif b["rows"]:
                    b["open"] = False
            if not any(b["open"] for b in new_blocks):
                break
            j += 1
        for b in new_blocks:
            names = [h for _, h in b["cols"]]
            rows_ = b["rows"]
            # 'No' 일련번호 열은 버린다
            if names and names[0] == "No":
                names, rows_ = names[1:], [r[1:] for r in rows_]
            blocks.append({"title": b["title"], "columns": names, "rows": rows_})
        i = j
    return blocks


def parse_code_sheet(ws) -> dict:
    rows = [[_s(v) for v in r] for r in ws.iter_rows(values_only=True)]
    title = next((r[0] for r in rows if r and r[0]), ws.title)
    header_i = next(i for i, r in enumerate(rows) if i > 0 and any(r))
    header = [h for h in rows[header_i] if h]
    data = [r[:len(header)] for r in rows[header_i + 1:] if any(r[:len(header)])]
    return {"title": title, "columns": header, "rows": data}


def build(xlsx: Path) -> dict:
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    listing = parse_list_sheet(wb["목록"])
    version = ""
    for row in wb["목록"].iter_rows(max_row=5, values_only=True):
        for v in row:
            m = re.search(r"\((v\d+),\s*([\d.]+)\)", _s(v))
            if m:
                version = f"{m.group(1)} ({m.group(2)})"

    tables, code_tables = [], []
    for title in wb.sheetnames:
        if title == "목록":
            continue
        ws = wb[title]
        if title.startswith("(참고표"):
            code_tables.append({"sheet": title.strip(), **parse_code_sheet(ws)})
            continue
        m = re.match(r"^(\d-\d{2})\s+(.*)$", title.strip())
        if not m:
            continue
        tid = m.group(1)
        t = parse_table_sheet(ws)
        lst = listing.get(tid, {})
        export_raw = t["export_raw"] or lst.get("export_raw", "")
        tables.append({
            "id": tid,
            "sheet": title.strip(),
            "name": (t["name"] or lst.get("name", m.group(2))).strip().rstrip("]").strip(),
            "category": (t["category"] or lst.get("category", "")).strip(),
            "provider": t["provider"] or lst.get("provider", ""),
            "raw_export_allowed": ("불가" not in export_raw) and bool(export_raw),
            "export_raw": export_raw,
            "registered": t["registered"],
            "period": t["period"],
            "description": t["description"],
            "columns": t["columns"],
            "references": t["references"],
        })

    return {
        "source": xlsx.name,
        "spec_version": version,
        "table_count": len(tables),
        "tables": tables,
        "code_tables": code_tables,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        return 2
    src, dst = Path(argv[1]), Path(argv[2])
    cat = build(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    no_cols = [t["id"] for t in cat["tables"] if not t["columns"]]
    print(f"{cat['spec_version']}: 표 {cat['table_count']}개, 코드표 {len(cat['code_tables'])}개 → {dst}")
    if no_cols:
        print("경고: 컬럼을 읽지 못한 표:", ", ".join(no_cols))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
