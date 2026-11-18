"""동네별 가게 수(경쟁) — 소상공인시장진흥공단 상가(상권)정보(공공데이터포털 15083033, 실제 공개 데이터).

- 센터 카드 데이터에는 가게 수가 없어 '경쟁 강도'를 판정할 수 없었다. 상가정보는 제주 59,101곳(2026년 9월 말)을
  법정동·업종(소분류 247종)으로 알려 주므로, 같은 동네·같은 업종 가게 수와 순위를 실제 값으로 보여 줄 수 있다.
- 법정동 이름은 센터 명세서 1-08의 73개 법정동과 그대로 일치한다(2026-11-04 확인).
- 이용허락범위 제한 없음(공공데이터포털 표기). 출처: 소상공인시장진흥공단 상가(상권)정보.
- 앱에는 동네×업종별 가게 수로 줄인 작은 파일(data/public/상가정보_제주_*.csv)만 넣는다. 새로 받기:
    python -m jeju_agent.stores update      (공공데이터포털 파일, 키 필요 없음, 전국 zip 약 350MB를 받아 제주만 남김)
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data" / "public"
STORES_ID = "공개-상가"
DATASET_PK = "15083033"
PAGE = f"https://www.data.go.kr/data/{DATASET_PK}/fileData.do"

# 상가정보 소분류 → 센터 카드 업종(1-08 업종명). 카드 업종 하나에 여러 소분류가 붙을 수 있다.
SMALL_TO_CARD = {
    "카페": "비알콜 음료점업",
    "빵/도넛": "빵 및 과자류 소매업", "떡/한과": "빵 및 과자류 소매업",
    "피자": "피자, 햄버거, 샌드위치 및 유사 음식점업", "버거": "피자, 햄버거, 샌드위치 및 유사 음식점업",
    "토스트/샌드위치/샐러드": "피자, 햄버거, 샌드위치 및 유사 음식점업",
    "일반 유흥 주점": "일반유흥 주점업", "요리 주점": "기타 주점업", "생맥주 전문": "기타 주점업",
    "호텔/리조트": "호텔업", "여관/모텔": "여관업", "펜션": "여관업",
    "슈퍼마켓": "슈퍼마켓", "편의점": "체인화 편의점", "반찬/식료품 소매업": "기타음식료품위주종합소매업",
    "그 외 기타 종합 소매업": "그외 기타 종합 소매업", "정육점": "육류 소매업", "수산물 소매업": "수산물 소매업",
    "채소/과일 소매업": "과실 및 채소 소매업", "건강보조식품 소매업": "건강보조식품 소매업", "주유소": "차량용 주유소 운영업",
    "화장품 소매업": "화장품 및 방향제 소매업", "기념품점": "관광 민예품 및 선물용품 소매업",
    "자동차 대여업": "자동차 임대업", "스포츠/레크리에이션 용품 대여업": "스포츠 및 레크레이션 용품 임대업",
    "여행사": "여행사업", "전시/컨벤션/행사 대행 서비스업": "전시 및 행사 대행업",
    "기타 스포츠시설 운영업": "그외 기타 스포츠시설 운영업", "수상/해양 레저업": "기타 수상오락 서비스업",
}
MID_TO_CARD = {"한식": "한식 음식점업", "중식": "중식 음식점업", "일식": "일식 음식점업", "서양식": "서양식 음식점업",
               "동남아시아": "기타 외국식 음식점업"}


def card_biz(mid: str, small: str) -> str:
    return SMALL_TO_CARD.get(str(small).strip()) or MID_TO_CARD.get(str(mid).strip()) or ""


def aggregate(raw: pd.DataFrame, base_ym: str) -> pd.DataFrame:
    """상가정보 원본(제주) → 법정동 × 업종 가게 수. 상호·주소·좌표는 남기지 않는다."""
    d = raw.rename(columns={"시군구명": "sigungu", "법정동명": "bjd", "상권업종대분류명": "big",
                            "상권업종중분류명": "mid", "상권업종소분류명": "small"})
    for c in ("sigungu", "bjd", "big", "mid", "small"):
        d[c] = d[c].astype(str).str.strip()
    g = d.groupby(["sigungu", "bjd", "big", "mid", "small"]).size().reset_index(name="store_cnt")
    g["card_biz"] = [card_biz(m, s) for m, s in zip(g["mid"], g["small"])]
    g.insert(0, "base_year_month", base_ym)
    return g.sort_values(["bjd", "big", "mid", "small"]).reset_index(drop=True)


def bundled_path() -> Path | None:
    files = sorted(PUBLIC_DIR.glob("상가정보_제주_*_동네업종별_가게수.csv"))
    return files[-1] if files else None


def load_stores(cat: dict):
    """동봉한 집계 파일을 앱의 표(LoadedTable)로. 없으면 None."""
    from .loader import from_frame
    p = bundled_path()
    if p is None:
        return None
    df = pd.read_csv(p, dtype={"base_year_month": str}, encoding="utf-8-sig")
    return from_frame(df, STORES_ID, cat)


def _latest_file_args(html: str) -> tuple[str, str]:
    m = re.search(r"fn_fileDataDown\('(\d+)',\s*'(uddi:[^']+)'", html)
    if not m:
        raise RuntimeError("공공데이터포털 페이지에서 내려받기 정보를 찾지 못했습니다.")
    return m.group(1), m.group(2)


def update(out_dir: Path = PUBLIC_DIR, opener=urllib.request.urlopen) -> Path:
    """공공데이터포털에서 최신 상가정보(전국 zip)를 받아 제주만 집계해 저장한다. 키 필요 없음."""
    with opener(PAGE, timeout=60) as r:
        pk, uddi = _latest_file_args(r.read().decode("utf-8", "replace"))
    meta_url = (f"https://www.data.go.kr/tcs/dss/selectFileDataDownload.do?publicDataPk={pk}"
                f"&publicDataDetailPk={uddi}&fileDetailSn=1")
    with opener(meta_url, timeout=60) as r:
        meta = json.loads(r.read().decode("utf-8"))
    fid = meta.get("atchFileId") or meta["fileDataRegistVO"]["atchFileId"]
    name = (meta.get("fileDataRegistVO") or {}).get("dataNm", "")
    base_ym = (re.search(r"(\d{6})\d{2}$", name) or re.search(r"(\d{6})", name)).group(1)
    url = f"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={fid}&fileDetailSn=1"
    with tempfile.TemporaryDirectory() as tmp:
        zpath = Path(tmp) / "stores.zip"
        with opener(url, timeout=600) as r, zpath.open("wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        with zipfile.ZipFile(zpath) as z:
            info = next(i for i in z.infolist()
                        if "제주" in re.sub(r"#U([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), i.filename)
                        or "제주" in i.filename)
            with z.open(info) as f:
                raw = pd.read_csv(f, dtype=str, usecols=["시군구명", "법정동명", "상권업종대분류명", "상권업종중분류명",
                                                          "상권업종소분류명"])
    agg = aggregate(raw, base_ym)
    out = out_dir / f"상가정보_제주_{base_ym}_동네업종별_가게수.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    agg.to_csv(out, index=False, encoding="utf-8-sig")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="상가(상권)정보 제주 집계 만들기")
    ap.add_argument("cmd", choices=["update", "build"])
    ap.add_argument("--csv", help="build: 이미 받아 둔 제주 원본 CSV 경로")
    ap.add_argument("--ym", help="build: 기준 연월(예: 202609)")
    a = ap.parse_args()
    if a.cmd == "update":
        print("저장:", update())
        return
    raw = pd.read_csv(a.csv, dtype=str, usecols=["시군구명", "법정동명", "상권업종대분류명", "상권업종중분류명", "상권업종소분류명"])
    agg = aggregate(raw, a.ym)
    out = PUBLIC_DIR / f"상가정보_제주_{a.ym}_동네업종별_가게수.csv"
    agg.to_csv(out, index=False, encoding="utf-8-sig")
    print("저장:", out, len(agg), "행")


if __name__ == "__main__":
    main()
