"""명세서 컬럼에 '역할'을 붙인다: 시간·지역·업종·구분·측정값·식별자.

분석 도구가 표마다 따로 짜이지 않도록, 컬럼 이름·라벨·타입으로 역할을 자동 추정한다.
규칙은 명세서 v12의 표 71종 컬럼 목록을 보고 정했다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TIME_MONTH = {"base_year_month", "dtYearMonth"}
TIME_DATE = {"base_date", "base_ymd"}
TIME_HOUR = {"time", "base_hour"}
TIME_WEEKDAY = {"week", "day_of_week"}
PARTITION = {"pt_year", "pt_month"}

REGION_ORDER = [  # 넓은 단위 → 좁은 단위
    "province", "sido", "sigungu", "city", "city_nm", "gungu", "city_name", "dstrct_se", "cityGubun", "area_type",
    "emd", "emd_nm", "emd_name", "address_emd", "bjd", "bjd_nm",
]
BUSINESS = {"marketType", "biz_nm", "biz_mid_nm", "biz_small_nm", "market_type", "market_theme", "induty",
            "ksic10_biz_nm", "menu_large_nm", "menu_mid_nm", "menu_small_nm", "menu_sub_nm",
            "goods_large_type", "goods_medium_type", "goods_small_type"}
SEGMENT = {"userType", "ageGroup", "gender", "user_type", "tour_type", "age", "age_group", "sex", "gender", "nationality", "resd",
           "visit_type", "job", "family_type", "pay_type", "user_category", "owner_gb"}
SENSITIVE = {"mac_address", "user_card_id", "user_id", "user_trans_id", "biz_num", "corporation_num",
             "trans_biz_num", "driver_id", "vhc_id", "tag_gno", "device_no"}
NON_ADDITIVE = re.compile(r"(per_|unit_price|average|rate|temperature|speed|latitude|longitude|altitude|"
                          r"wind|rainfall|_date|_time$)")
MEASURE_NAME = re.compile(r"(_cnt|_amt|_count|_amount|^amount$|^cnt$|^count$|_tot$|_price$|^userCount$|^useCount$|^useCost$|"
                          r"income|profit|employees|rainfall|temperature|speed|upload|download|session_time|"
                          r"^em_g$|^em_amt$|fee_amount|sale_count|sale_amount)")
NUMERIC_TYPES = re.compile(r"^(INT|BIGINT|DOUBLE|FLOAT|DECIMAL)")


@dataclass(frozen=True)
class ColumnRole:
    name: str
    label: str
    role: str          # time_month/time_date/time_hour/time_weekday/partition/region/business/segment/measure/id/other
    additive: bool = False
    level: int = -1    # region 세분화 순서(클수록 좁은 단위)


def infer_role(name: str, label: str, dtype: str) -> ColumnRole:
    n = name.strip()
    if n in PARTITION:
        return ColumnRole(n, label, "partition")
    if n in TIME_MONTH:
        return ColumnRole(n, label, "time_month")
    if n in TIME_DATE:
        return ColumnRole(n, label, "time_date")
    if n in TIME_HOUR:
        return ColumnRole(n, label, "time_hour")
    if n in TIME_WEEKDAY:
        return ColumnRole(n, label, "time_weekday")
    if n in REGION_ORDER:
        return ColumnRole(n, label, "region", level=REGION_ORDER.index(n))
    if n in BUSINESS:
        return ColumnRole(n, label, "business")
    if n in SEGMENT:
        return ColumnRole(n, label, "segment")
    if n in SENSITIVE or n.endswith(("_cd", "_id", "_code", "_num")) or n in {"kedcd", "ked_code", "grid", "grid_500", "grid_500m", "grid_1km", "link_id"}:
        return ColumnRole(n, label, "id")
    if NUMERIC_TYPES.match(dtype.upper()) or MEASURE_NAME.search(n):
        return ColumnRole(n, label, "measure", additive=not NON_ADDITIVE.search(n))
    return ColumnRole(n, label, "other")


def table_roles(table: dict) -> dict[str, ColumnRole]:
    return {c["name"].strip(): infer_role(c["name"], c["label"].strip(), c["dtype"]) for c in table["columns"]}


def by_role(roles: dict[str, ColumnRole], role: str) -> list[str]:
    cols = [r for r in roles.values() if r.role == role]
    if role == "region":
        cols.sort(key=lambda r: r.level)
    return [r.name for r in cols]
