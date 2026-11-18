"""공공데이터포털 Open API로 받는 실제 공개 데이터 2종(활용신청한 계정의 인증키 필요, 2026-11-04 신청·확인).

1) 한국관광공사_빅데이터_지역별 방문자수_GW(15101972) — 이동통신 기반 시군구별 일별 방문자 수(현지인·외지인·외국인).
   제주시·서귀포시만 남겨 최근 12개월을 저장한다. '방문자'는 일상생활권을 벗어나 머문 사람으로, 관광객과 같은 뜻은 아니다.
2) 행정안전부_법정동별(행정동 통반단위) 주민등록 인구 및 세대현황(15108071) — 법정동(리) 단위 인구를 법정동으로 더한다.
   법정동 이름이 센터 명세서 1-08의 73개 법정동과 그대로 같다(2026-11-04 확인).

키: 환경변수 DATA_GO_KR_KEY(또는 운영자 설정의 공공데이터포털 인증키). 저장소에는 넣지 않는다.
새로 받기: python -m jeju_agent.datagokr update
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "data" / "public"
VISIT_ID, POP_ID = "공개-방문자", "공개-인구"
VISIT_URL = "https://apis.data.go.kr/B551011/DataLabService/locgoRegnVisitrDDList"
POP_URL = "https://apis.data.go.kr/1741000/stdgPpltnHhStus/selectStdgPpltnHhStus"
JEJU_SGG = {"50110": "제주시", "50130": "서귀포시"}
TOU = {"1": "현지인", "2": "외지인", "3": "외국인"}


def _key(key: str | None = None) -> str:
    if key:
        return key
    k = os.environ.get("DATA_GO_KR_KEY", "")
    if not k:
        try:
            from .llm import load_settings
            k = load_settings().get("data_go_kr_key", "")
        except Exception:  # noqa: BLE001
            k = ""
    if not k:
        raise ValueError("공공데이터포털 인증키가 없습니다(DATA_GO_KR_KEY).")
    return k


def _get(url: str, params: dict, key: str, opener=urllib.request.urlopen, tries: int = 4) -> dict:
    q = urllib.parse.urlencode(params)
    for i in range(tries):                      # 연결이 끊기는 일이 가끔 있어 몇 번 다시 시도한다
        try:
            with opener(f"{url}?serviceKey={urllib.parse.quote(key, safe='')}&{q}", timeout=90) as r:
                text = r.read().decode("utf-8")
            break
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError("응답이 JSON이 아닙니다(키 미등록·호출 한도 초과일 수 있음): " + text[:120]) from None


def fetch_visitors(start: date, end: date, key: str | None = None, opener=urllib.request.urlopen,
                   window: int = 12) -> pd.DataFrame:
    """제주시·서귀포시 일별 방문자 수(현지인·외지인·외국인). 한 번에 12일씩(하루 약 800행) 받는다."""
    key = _key(key)
    rows = []
    d = start
    while d <= end:
        e = min(end, d + timedelta(days=window - 1))
        data = _get(VISIT_URL, {"MobileOS": "ETC", "MobileApp": "jeju-data-agent", "_type": "json",
                                "startYmd": d.strftime("%Y%m%d"), "endYmd": e.strftime("%Y%m%d"),
                                "numOfRows": 10000, "pageNo": 1}, key, opener)
        items = (((data.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
        for it in items:
            sgg = JEJU_SGG.get(str(it.get("signguCode")))
            if sgg:
                ymd = str(it["baseYmd"])
                rows.append({"base_ymd": ymd, "base_year_month": ymd[:6], "sigungu": sgg,
                             "daywk": it.get("daywkDivNm", ""), "tou_div": TOU.get(str(it.get("touDivCd")), ""),
                             "tou_num": round(float(it.get("touNum") or 0), 1)})
        d = e + timedelta(days=1)
    return pd.DataFrame(rows)


def fetch_population(ym: str, key: str | None = None, opener=urllib.request.urlopen) -> pd.DataFrame:
    """제주 법정동별 주민등록 인구(리 단위를 법정동으로 더함)."""
    key = _key(key)
    rows = []
    for cd in ("5011000000", "5013000000"):
        data = _get(POP_URL, {"stdgCd": cd, "srchFrYm": ym, "srchToYm": ym, "lv": "3", "regSeCd": "1", "type": "JSON",
                              "numOfRows": 1000, "pageNo": 1}, key, opener)
        rows += ((data.get("Response") or {}).get("items") or {}).get("item") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["pop"] = df["totNmprCnt"].astype(int)
    df["hh"] = df["hhCnt"].astype(int)
    g = df.groupby(["sggNm", "stdgNm"], as_index=False)[["pop", "hh"]].sum()
    g = g.rename(columns={"sggNm": "sigungu", "stdgNm": "bjd"})
    g.insert(0, "base_year_month", ym)
    return g.sort_values(["sigungu", "bjd"]).reset_index(drop=True)


def update(out_dir: Path = PUBLIC_DIR, key: str | None = None, today: date | None = None,
           opener=urllib.request.urlopen) -> list[Path]:
    """최근 12개월 방문자 수(지난달 말까지)와 가장 최근 달 인구를 받아 저장한다."""
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    last = today.replace(day=1) - timedelta(days=1)                     # 지난달 말
    for back in range(0, 3):                                             # 아직 안 올라온 달이면 한 달씩 앞으로
        end = last if back == 0 else (end.replace(day=1) - timedelta(days=1))
        start = (end.replace(day=1) - timedelta(days=330)).replace(day=1)
        if fetch_visitors(end, end, key, opener).empty:
            continue
        df = fetch_visitors(start, end, key, opener)
        p = out_dir / f"방문자_제주_{start:%Y%m}-{end:%Y%m}_일별.csv"
        df.to_csv(p, index=False, encoding="utf-8-sig")
        saved.append(p)
        break
    ym = last.strftime("%Y%m")
    for _ in range(3):
        pop = fetch_population(ym, key, opener)
        if not pop.empty:
            p = out_dir / f"인구_제주_{ym}_법정동.csv"
            pop.to_csv(p, index=False, encoding="utf-8-sig")
            saved.append(p)
            break
        y, m = int(ym[:4]), int(ym[4:])
        ym = f"{y - 1}12" if m == 1 else f"{y}{m - 1:02d}"
    return saved


def _latest(pattern: str) -> Path | None:
    files = sorted(PUBLIC_DIR.glob(pattern))
    return files[-1] if files else None


def load_visitors(cat: dict):
    from .loader import from_frame
    p = _latest("방문자_제주_*_일별.csv")
    if p is None:
        return None
    df = pd.read_csv(p, dtype={"base_ymd": str, "base_year_month": str}, encoding="utf-8-sig")
    return from_frame(df, VISIT_ID, cat)


def load_population(cat: dict):
    from .loader import from_frame
    p = _latest("인구_제주_*_법정동.csv")
    if p is None:
        return None
    df = pd.read_csv(p, dtype={"base_year_month": str}, encoding="utf-8-sig")
    return from_frame(df, POP_ID, cat)


def main() -> None:
    ap = argparse.ArgumentParser(description="공공데이터포털 공개 데이터(방문자 수·인구) 받기")
    ap.add_argument("cmd", choices=["update"])
    ap.parse_args()
    for p in update():
        print("저장:", p)


if __name__ == "__main__":
    main()
