"""한국어 표현 도우미: 조사(이/가 등), 연월 표기, 표 머리글 한글화.

화면·보고서에 영문 컬럼명(bjd, use_amt)이나 '식음료의  가운데' 같은 깨진 문장이 나오지 않게 한다.
"""

from __future__ import annotations

import re

import pandas as pd

# 숫자를 읽었을 때 받침이 있는지(0 영, 1 일, 3 삼, 6 육, 7 칠, 8 팔 → 받침 있음)
_DIGIT_BATCHIM = {"0": True, "1": True, "2": False, "3": True, "4": False, "5": False,
                  "6": True, "7": True, "8": True, "9": False}


def _has_batchim(word: str) -> bool:
    w = re.sub(r"\([^)]*\)\s*$", "", word.strip())      # '매출(카드 이용금액)' → '매출'
    w = w.rstrip(" .,'\"")
    if not w:
        return False
    ch = w[-1]
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    if ch.isdigit():
        return _DIGIT_BATCHIM[ch]
    if ch == "%":
        return False                                    # 퍼센트
    return False


def josa(word: str, pair: str) -> str:
    """josa('매출', '이/가') → '이', josa('결제 건수', '이/가') → '가'. pair는 '받침 있을 때/없을 때'."""
    with_b, without_b = pair.split("/")
    return with_b if _has_batchim(word) else without_b


def with_josa(word: str, pair: str) -> str:
    return f"{word}{josa(word, pair)}"


def fmt_month(ym: str) -> str:
    """'201812' → '2018년 12월'."""
    s = str(ym)
    return f"{s[:4]}년 {int(s[4:6])}월" if len(s) == 6 and s.isdigit() else s


def fmt_month_short(ym: str) -> str:
    """'201812' → '2018.12'."""
    s = str(ym)
    return f"{s[:4]}.{s[4:6]}" if len(s) >= 6 and s[:6].isdigit() else s


# 분석 도구가 만드는 열 이름 중 한글화가 필요한 것
DERIVED = {"전기 대비(%)": "전월 대비(%)"}
FRIENDLY = {  # 명세서 라벨보다 쉬운 말
    "base_year_month": "연월", "dtYearMonth": "연월", "bjd": "지역(법정동)", "biz_nm": "업종",
    "user_type": "이용자 구분", "tour_type": "관광객 구분", "week": "요일", "time": "시간대",
    "sigungu": "시", "cityGubun": "도심·읍면", "marketType": "업종", "userType": "이용자 구분",
    "ageGroup": "연령대", "gender": "성별", "age": "연령대", "sex": "성별",
    "use_amt": "카드 이용금액(원)", "use_cnt": "이용건수", "user_cnt": "이용자 수",
    "useCost": "카드 이용금액(원)", "useCount": "이용건수", "userCount": "이용자 수",
}


def column_labels(table: dict | None) -> dict[str, str]:
    labels = {c["name"]: c["label"] for c in (table or {}).get("columns", [])}
    labels.update(FRIENDLY)
    labels.update(DERIVED)
    return labels


def korean_table(df: pd.DataFrame, table: dict | None) -> pd.DataFrame:
    """표 머리글을 한글로, 연월 값은 '2018.12'로."""
    t = df.copy()
    for c in t.columns:
        if c in ("base_year_month", "dtYearMonth"):
            t[c] = t[c].astype(str).map(fmt_month_short)
    return t.rename(columns=column_labels(table))
