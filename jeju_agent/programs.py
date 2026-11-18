"""내가 해당되는 지원사업 찾기 — 창업진흥원 K-Startup 사업공고 조회서비스(공공데이터포털).

- API: https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01
  (무료, 이용허락범위 제한 없음, 실시간, 개발계정 10,000건/일. 가이드 v2.0 기준 필드)
- 인증키는 환경변수 KSTARTUP_SERVICE_KEY(없으면 DATA_GO_KR_KEY, 공공데이터포털 계정 공통 키)에서 받는다(제출물에 넣지 않음).
- 보내는 것: 지역·창업기간·연령대 같은 조회 조건뿐. 센터 데이터·개인 식별정보는 보내지 않는다.
- 네트워크가 안 되면 마지막으로 받아 둔 목록(data/programs_snapshot.json)을 쓴다.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data" / "programs_snapshot.json"
ENDPOINT = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"

APPLY_FIELDS = {  # 응답 필드 → 신청 방법
    "aply_mthd_vst_rcpt_istc": "방문",
    "aply_mthd_onli_rcpt_istc": "온라인",
    "aply_mthd_eml_rcpt_istc": "이메일",
    "aply_mthd_pssr_rcpt_istc": "우편",
    "aply_mthd_fax_rcpt_istc": "팩스",
    "aply_mthd_etc_istc": "기타",
}
STAGES = ["예비창업자", "1년미만", "2년미만", "3년미만", "5년미만", "7년미만", "10년미만"]


TRAITS = ["청년(만 39세 이하)", "여성", "장애인", "소상공인", "농어업인", "사회적경제기업", "재창업", "수출·해외진출"]


@dataclass
class Profile:
    region: str = "제주"
    stage: str = "예비창업자"         # STAGES 중 하나
    age: int | None = None
    keywords: list[str] = field(default_factory=list)   # 업종·관심 분야(예: 카페, 관광, 외식)
    city: str = ""                    # 제주시/서귀포시(시 단위 공고 구분)
    business: str = ""                # 하려는(하는) 업종, 예: 카페
    traits: list[str] = field(default_factory=list)     # TRAITS 중 해당하는 것
    employees: int | None = None      # 상시 근로자 수(사업자만)
    note: str = ""                    # 그 밖에(예: 작년 예비창업패키지 선정)
    needs: list[str] = field(default_factory=list)      # 필요한 도움(융자·교육 등) — 정렬에만 씀

    def describe(self) -> list[str]:
        out = [f"지역: {self.region}{(' ' + self.city) if self.city else ''}",
               f"창업 단계: {self.stage}"]
        if self.age:
            out.append(f"나이: 만 {self.age}세")
        if self.business:
            out.append(f"업종: {self.business}")
        if self.traits:
            out.append("해당 사항: " + ", ".join(self.traits))
        if self.employees is not None:
            out.append(f"상시 근로자: {self.employees}명")
        if self.note:
            out.append(f"기타: {self.note}")
        return out


@dataclass
class Program:
    title: str
    field: str
    region: str
    start: str
    end: str
    org: str
    target: str
    stage: str
    age: str
    apply_methods: dict[str, str]
    url: str
    summary: str = ""
    source: str = "K-Startup(창업진흥원)"
    detail: str = ""                  # 자격 확인용 공고 본문(대상·내용, 최대 1500자) — 화면에는 그대로 싣지 않음
    period_text: str = ""
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    after_open: bool = False          # 예비창업자에게: 가게(사업자)를 연 뒤 신청할 수 있는 공고

    @property
    def visit_required(self) -> bool:
        return bool(self.apply_methods.get("방문")) and not self.apply_methods.get("온라인")


def _d(s: str) -> date | None:
    s = (s or "").strip()[:10].replace("-", "")
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def parse_item(it: dict) -> Program:
    methods = {v: (it.get(k) or "").strip() for k, v in APPLY_FIELDS.items() if (it.get(k) or "").strip()}
    url = (it.get("detl_pg_url") or it.get("biz_aply_url") or "").strip()
    if url and not url.startswith("http"):
        url = "https://" + url
    return Program(
        title=(it.get("biz_pbanc_nm") or it.get("intg_pbanc_biz_nm") or "").strip(),
        field=(it.get("supt_biz_clsfc") or "").strip(),
        region=(it.get("supt_regin") or "").strip(),
        start=(it.get("pbanc_rcpt_bgng_dt") or "")[:10],
        end=(it.get("pbanc_rcpt_end_dt") or "")[:10],
        org=(it.get("pbanc_ntrp_nm") or it.get("sprv_inst") or "").strip(),
        target=" ".join(x for x in [it.get("aply_trgt") or "", it.get("aply_trgt_ctnt") or ""] if x).strip(),
        stage=(it.get("biz_enyy") or "").strip(),
        age=(it.get("biz_trgt_age") or "").strip(),
        apply_methods=methods,
        url=url,
        summary=(it.get("pbanc_ctnt") or "").strip()[:300],
        detail=" ".join(x for x in [it.get("aply_trgt_ctnt") or "", it.get("aply_excl_trgt_ctnt") or "",
                                     it.get("pbanc_ctnt") or ""] if x).strip()[:1500],
    )


def _get(url: str, timeout: int, tries: int = 4) -> dict:
    last = None
    for i in range(tries):  # 공공 API는 연결이 가끔 끊긴다 → 잠깐 쉬고 다시
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def fetch(service_key: str, per_page: int = 100, max_pages: int = 10, timeout: int = 20) -> list[dict]:
    """모집 중인 공고 전체. 조건은 cond[필드::EQ] 형식(실측 2026-11-02)."""
    items: list[dict] = []
    for page in range(1, max_pages + 1):
        q = {"serviceKey": service_key, "page": page, "perPage": per_page, "returnType": "json",
             "cond[rcrt_prgs_yn::EQ]": "Y"}
        data = _get(ENDPOINT + "?" + urllib.parse.urlencode(q), timeout)
        batch = data.get("data") or data.get("items") or []
        items.extend(batch)
        if len(items) >= int(data.get("matchCount") or 0) or len(batch) < per_page:
            break
    return items


_CACHE: dict = {}
_LOCKS: dict = {}
FAIL_RETRY = 300          # 실시간 조회가 실패하면 5분 동안은 저장본으로(다시 기다리지 않음)


def _source_list(name: str, fetcher, parser, key: str, ttl: int, wait: bool = True) -> tuple[list[Program], str]:
    """실시간 공고(캐시 ttl초) → 실패하면 저장본. 실패도 5분 기억해 화면을 누를 때마다 다시 기다리지 않는다.
    wait=False: 다른 스레드(앱 시작 때 미리 받기)가 받는 중이면 기다리지 않고 저장본을 바로 쓴다."""
    snap = SNAPSHOT.with_name(f"programs_snapshot_{name}.json")
    hit = _CACHE.get(name)
    if hit and time.time() - hit[0] < ttl:
        return hit[1], hit[2]
    note, failed = "", False
    if key:
        lock = _LOCKS.setdefault(name, threading.Lock())
        if lock.acquire(blocking=wait or not snap.exists()):
            try:
                hit = _CACHE.get(name)                     # 기다리는 사이 다른 스레드가 받아 두었으면 그것
                if hit and time.time() - hit[0] < ttl:
                    return hit[1], hit[2]
                try:
                    raw = fetcher(key)
                    snap.parent.mkdir(parents=True, exist_ok=True)
                    prev = json.loads(snap.read_text(encoding="utf-8")).get("items") if snap.exists() else None
                    if prev != raw:    # 공고가 바뀐 때만 저장본을 새로 쓴다(시각만 바뀌는 변경 방지)
                        snap.write_text(json.dumps({"fetched_at": datetime.now().isoformat(timespec="minutes"),
                                                    "items": raw}, ensure_ascii=False), encoding="utf-8")
                    progs = [parser(i) for i in raw]
                    _CACHE[name] = (time.time(), progs, f"{name} 실시간 {len(progs)}건")
                    return _CACHE[name][1], _CACHE[name][2]
                except Exception as e:  # noqa: BLE001  네트워크·키 오류 → 저장본
                    note = f"{name} 실시간 조회 실패({'인터넷 연결' if isinstance(e, OSError) else '응답 형식'} 문제)"
                    failed = True
            finally:
                lock.release()
        else:
            note = f"{name} 실시간 공고 받는 중"
    else:
        note = f"{name} 인증키 없음"
    if snap.exists():
        d = json.loads(snap.read_text(encoding="utf-8"))
        out = [parser(i) for i in d.get("items", [])], f"{note}, 저장본 사용({d.get('fetched_at', '날짜 미상')} 기준)"
    else:
        out = [], f"{note}, 저장본 없음"
    if failed:                                             # 5분 뒤에 다시 시도
        _CACHE[name] = (time.time() - ttl + FAIL_RETRY, *out)
    return out


def load_programs(service_key: str | None = None, today: date | None = None, ttl: int = 1800,
                  wait: bool = True) -> tuple[list[Program], str]:
    """K-Startup(창업 공고) + 기업마당(중앙·지자체·유관기관 공고). (목록, 출처 설명)"""
    from .llm import load_settings
    key = (service_key or load_settings().get("data_go_kr_key") or os.environ.get("KSTARTUP_SERVICE_KEY", "")
           or os.environ.get("DATA_GO_KR_KEY", ""))
    a, na = _source_list("K-Startup", fetch, parse_item, key, ttl, wait)
    b, nb = _source_list("기업마당", fetch_bizinfo, parse_bizinfo_item, key, ttl, wait)
    return a + b, f"{na} · {nb}"


def _stage_ok(p: Program, stage: str) -> bool:
    if not p.stage:
        return True
    if stage == "예비창업자":
        return "예비" in p.stage
    # '3년미만' 사업자는 '3년미만'·'5년미만'·'7년미만' 대상 공고에 해당
    try:
        my = STAGES.index(stage)
    except ValueError:
        return True
    return any(s in p.stage for s in STAGES[my:] if s != "예비창업자")


def _age_ok(p: Program, age: int | None) -> bool:
    if age is None or not p.age:
        return True
    a = p.age
    if age < 20:
        return "20세 미만" in a
    if age <= 39:
        return "39세 이하" in a
    return "40세 이상" in a


# 서울 자치구(기관 이름이 '마포청년창업…'·'광진경제허브센터'처럼 구 이름으로 시작하면 그 구 사업)
SEOUL_GU = ["종로", "용산", "성동", "광진", "동대문", "중랑", "성북", "강북", "도봉", "노원", "은평", "서대문", "마포",
            "양천", "강서", "구로", "금천", "영등포", "동작", "관악", "서초", "강남", "송파", "강동"]
# 경기도 시(제목에 'OO시'로 나오면 그 시 사업, 예: '2026 의왕시 청년e-Room 창업아이디어 공모전')
GYEONGGI_SI = ["의왕", "안양", "성남", "용인", "고양", "부천", "화성", "안산", "남양주", "평택", "시흥", "파주", "의정부",
               "김포", "광명", "군포", "하남", "오산", "이천", "구리", "안성", "포천", "양주", "여주", "동두천", "과천"]
OTHER_REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남",
                 "전북", "전남", "경북", "경남", "성동구", "강남구", "마포구", "판교", "수원", "창원", "포항", "춘천",
                 "청주", "천안", "전주", "목포", "여수", "순천", "안동", "구미", "김해", "진주",
                 *[g + "구" for g in SEOUL_GU], *[c + "시" for c in GYEONGGI_SI]]


_PLACE_LIMIT = re.compile(r"([가-힣]{2,}(?:특별시|광역시|특별자치시|특별자치도|도|시|군|구))\s*(?:내|소재|지역|거주|관내)")
_ORG_PLACE = re.compile(r"^\s*([가-힣]{2,}(?:시|군|구))\s")
_TITLE_PLACE = re.compile(r"^\s*[\[(]([가-힣]{2,}(?:시|군|구|도))")


def _other_region(p: Program, region: str) -> str:
    """'전국' 공고라도 제목이나 신청 대상 문장에 다른 지역 이름이 있으면 그 지역 사업일 가능성이 크다
    (실측: 울산 상담회·성동구 아카데미, '[구리시 청년내일센터]', 신청 대상 '충청남도 내 창업 예정인' 등)."""
    if region in p.title or region in p.target:
        return ""
    for r in OTHER_REGIONS:
        if r in p.title or (r + " 지역") in p.target or (r + " 소재") in p.target or (r + "지역") in p.target:
            return r
    m = _TITLE_PLACE.search(p.title)
    if m and region not in m.group(1):
        return m.group(1)
    m = _ORG_PLACE.search(p.org or "")              # 기관명이 '강동구 청년해냄센터'처럼 다른 시·군·구로 시작
    if m and region not in m.group(1) and "서귀포" not in m.group(1):
        return m.group(1)
    gu = next((g for g in SEOUL_GU if (p.org or "").startswith(g)), "")
    if gu:
        return gu + "구"
    if "대학교" in (p.org or "") and region not in (p.org or "") and region not in p.region:
        return "타 지역 대학"                        # 다른 지역 대학 보육·아카데미는 대개 자기 입주기업 대상
    for m in _PLACE_LIMIT.finditer(p.target):
        name = m.group(1)
        if region not in name and name not in ("국내", "전국", "해당 지역", "본 지역"):
            return name
    return ""


GENERIC_SOHO = ["소상공인", "자영업", "중소기업육성", "상점가", "골목상권", "창업자금"]
# 다른 업종(콘텐츠·예술·수출 등) 공고: 업종 관련어가 제목에 있어도 뺀다(예: 한식당 '식품'으로 '쌀가공식품 수출' 통과 방지)
HARD_EXCLUDE = ["수출", "해외", "콘텐츠", "예술", "영상물", "문화산업", "게임", "웹툰", "R&D", "연구개발", "딥테크"]
# 업종과 무관한 경우가 많은 공고(제목에만 적용 — 요약문에 적용하면 식품진흥기금처럼 맞는 공고까지 빠진다)
# 가게(카페·식당·숙박 등) 창업과 거리가 먼 공고: 기술·투자·입주(보육)·기관 대상·특정 학교 출신 등.
# 실측(2026-11-03, 카페 예비창업자): AI 플랫폼·위치정보 교육·TIPS·5억 투자·관악 입주·전자책 판매 강의가 '해당'으로 나왔다.
NOT_FOR_SHOP = re.compile(
    r"인공지능|(?<![A-Za-z])(?:AI|AIoT|ICT|TIPS|IR|VC|SaaS|SW|IP|EUV)(?![A-Za-z])|팁스|"
    r"기술(?:창업|기반|개발|투자|금융|가치|사업화|이전|지도|지원|보호|거래|혁신|평가|분쟁|침해)|딥테크|특허|지식재산|"
    r"시제품|부품|소재|제조|장비|로봇|엔지니어링|소프트웨어|정보보호|조달|전문인력|기능인력|3D프린팅|위치정보|마이데이터|빅데이터|헬스케어|모빌리티|바이오|디스플레이|반도체|플랫폼|투자|액셀러레이|입주|보육센터|"
    r"비상주|주관기관|운영기관|창업도시|벤처기업\s*인증|연구인력|비자|Visa|규제샌드박스|전자책|쇼핑몰|출신")
# 수출·해외 판촉·제품 인증 공고(제조·유통 기업용). 실측: 카페 운영자에게 '하얼빈 빙설축제 판촉전',
# '중국 로컬유통망 입점', '제주-칭다오 노선 활성화', '우수제품 시험성적서 비용'이 나왔다.
NOT_FOR_SHOP_EXPORT = re.compile(r"중국|베트남|하얼빈|칭다오|상하이|해외|수출|글로벌|K-푸드|판촉전|노선|콜드|"
                                 r"시험성적서|품질인증|소비재")
# 제주 공고는 수가 적고 가게와 관련된 경우가 많아('온라인 플랫폼 입점 지원' 등) 기술 중심 말만 본다
NOT_FOR_SHOP_JEJU = re.compile(r"인공지능|(?<![A-Za-z])(?:AI|ICT|TIPS)(?![A-Za-z])|팁스|기술창업|기술개발|딥테크|특허|"
                               r"위치정보|마이데이터|빅데이터|바이오|디스플레이|반도체")
NOT_FOR_SHOP_TARGET = re.compile(r"기술창업|기술기반|(?<![A-Za-z])TIPS(?![A-Za-z])|팁스|위치정보|벤처기업\s*인증|"
                                 r"디스플레이|반도체|바이오|헬스케어|모빌리티|딥테크|(?:대학교|대학|고등학교)\s*출신")
# 공고 본문(앞부분)에 이런 말이 있으면 기술 스타트업 육성(투자·스케일업) 프로그램이다(예: 창업-BuS 'TIPS 추천·투자 유치')
NOT_FOR_SHOP_DETAIL = re.compile(r"(?<![A-Za-z])TIPS(?![A-Za-z])|팁스|액셀러레이팅|스케일업|기술창업|혁신기술")
# 제목이 가게·대상 특성을 직접 말하면 걸러내지 않는다(예: '소상공인 투자연계(LIPS)', '여성기업 육성' — 자격은 판정 단계에서 본다)
SHOP_TITLE = re.compile(r"소상공인|자영업|전통시장|상점가|골목|여성|장애인|재창업")
SHOP_LIKE = ("카페", "외식", "음식", "식품", "음료", "숙박", "관광", "소매", "유통", "기념품", "공예", "운송", "농어촌민박")


def not_for_shop(p: "Program", local: bool) -> bool:
    """가게 창업자에게 무관한 기술·투자·입주·기관 대상 공고인가(제목·신청 대상 문장 기준)."""
    if SHOP_TITLE.search(p.title):
        return False
    pat = NOT_FOR_SHOP_JEJU if local else NOT_FOR_SHOP
    if pat.search(p.title) or NOT_FOR_SHOP_EXPORT.search(p.title) or NOT_FOR_SHOP_TARGET.search(p.target[:400]) or \
            NOT_FOR_SHOP_DETAIL.search((p.detail or p.summary)[:700]):
        return True
    return not local and ("시설" in p.field and "보육" in p.field)       # K-Startup '시설ㆍ공간ㆍ보육'(입주 공간)


EXCLUDE_TITLE = ["해양수산", "어업", "어촌", "농업인", "영화", "MICE", "R&D", "연구개발", "딥테크", "바이오", "반도체",
                 "양자", "우주", "방산", "스마트팜", "수출", "해외", "채소", "축산", "수산물", "감귤", "양식장", "어선", "농가",
                 "화물", "임산물", "서점", "연구소", "물류"]
# 가게(카페·식당 등)에는 맞지 않는 제조·가공 공고. 제목에 '식품'이 있어도 업종 키워드 예외를 두지 않는다.
MAKER_TITLE = ("수산식품", "가공설비", "가공시설", "제조시설")


def match(programs: list[Program], prof: Profile, today: date | None = None, stats: dict | None = None) -> list[Program]:
    """조건에 맞는 모집 중 공고(점수순). stats를 주면 거른 이유별 건수를 채운다(화면의 '거른 이유 보기')."""
    today = today or date.today()
    out = []
    drop = Counter()
    for p in programs:
        p.after_open = False
        end = _d(p.end)
        if end and end < today:
            drop["마감 지남"] += 1
            continue
        if p.region and prof.region not in p.region and "전국" not in p.region:
            drop["다른 지역 공고"] += 1
            continue
        if prof.region not in p.region and _other_region(p, prof.region):
            drop["다른 지역 기관·대학 공고"] += 1
            continue
        hard = any(w in p.title for w in HARD_EXCLUDE) and "수출·해외진출" not in prof.traits \
            and not any(w in prof.business for w in ("콘텐츠", "영상", "예술", "게임"))
        maker = any(w in p.title for w in MAKER_TITLE) and not any(w in prof.business for w in ("제조", "가공"))
        if hard or maker or (any(w in p.title for w in EXCLUDE_TITLE) and not any(w in p.title for w in prof.keywords)
                    and not any(t in ("농어업인", "수출·해외진출") for t in prof.traits)):
            drop["다른 업종·기술개발·수출 공고"] += 1
            continue
        shop = any(k in SHOP_LIKE for k in prof.keywords) or bool(prof.business)
        if shop and not_for_shop(p, prof.region in p.region):
            drop["기술·투자·입주 중심 공고(가게 창업과 무관)"] += 1
            continue
        if shop and p.source.startswith("기업마당") and prof.region not in p.region and not any(
                k and k in " ".join([p.title, p.target, p.summary, p.detail]) for k in prof.keywords + GENERIC_SOHO):
            drop["업종과 관련 없는 사업자 공고"] += 1      # 전국 기업마당 공고는 업종·소상공인 말이 있을 때만(제조·수출 등 제외)
            continue
        if "사회적기업" in p.title and "사회적경제기업" not in prof.traits:
            drop["사회적기업 대상 공고"] += 1
            continue
        other_city = {"제주시": "서귀포시", "서귀포시": "제주시"}.get(prof.city, "")
        if other_city and other_city in p.title and prof.city not in p.title:
            drop["다른 행정시 공고"] += 1
            continue
        reasons = ["제주 지역 공고" if prof.region in p.region else "전국 공고"]
        if not _stage_ok(p, prof.stage):
            drop["창업 단계(업력)가 맞지 않음"] += 1
            continue
        if p.stage:
            reasons.append(f"창업기간 조건 충족({prof.stage})")
        if not _age_ok(p, prof.age):
            drop["나이 조건이 맞지 않음"] += 1
            continue
        if p.source.startswith("기업마당") and prof.stage == "예비창업자" and p.field not in ("창업", "") \
                and "예비" not in (p.target + p.summary):
            if prof.region not in p.region:
                drop["사업자 대상 전국 공고(예비창업자)"] += 1
                continue   # 전국 사업자 대상 공고는 예비창업자에게 너무 많다 → 제주 공고만 '가게 연 뒤'로 보여 준다
            p.after_open = True      # 기업마당 공고는 대부분 사업자 대상 → 예비창업자에겐 '가게를 연 뒤' 묶음으로
        score = 2.0 if prof.region in p.region else 1.0
        if prof.city and prof.city in (p.title + p.org):
            score += 1.0
            reasons.append(f"{prof.city} 공고")
        text = " ".join([p.title, p.field, p.target, p.summary, p.detail])
        if p.after_open and not any(k and k in text for k in prof.keywords + GENERIC_SOHO):
            drop["업종과 관련 없는 사업자 공고"] += 1     # 예: 카페 창업자에게 양식장·영상 제작비 공고
            continue
        hits = [k for k in prof.keywords if k and k in text]
        if hits:
            score += len(hits)
            reasons.append("관련 업종: " + ", ".join(hits[:3]))
        need_hits = [k for k in prof.needs if k and k in text]     # '필요한 도움'은 순서에만 쓴다(판정에는 안 씀)
        score += 0.5 * len(need_hits)
        if end:
            left = (end - today).days
            reasons.append(f"마감 {left}일 남음")
            if left <= 14:
                score += 0.5
        p.score, p.reasons = score, reasons
        out.append(p)
    out.sort(key=lambda p: (-p.score, p.end or "9999"))
    if stats is not None:
        stats.update(total=len(programs), kept=len(out), dropped=dict(drop.most_common()))
    return out


def to_dict(p: Program) -> dict:
    d = asdict(p)
    d["visit_required"] = p.visit_required
    return d


# ── 기업마당(중소벤처기업부_중소기업 지원사업 공고 조회 서비스, 공공데이터포털 15157820) ──────────
# 중앙부처·지자체·유관기관 공고. XML 응답. 이용조건: 공공누리 제3유형(출처표시·변경금지) → 공고명·기관·기간·링크를
# 원문 그대로 보여 주고 출처를 표시한다. 신청 방법은 '사업신청방법내용' 문장에서 자동 분류(추정)한다.
BIZINFO_ENDPOINT = "https://apis.data.go.kr/1421000/bizinfo/pblancBsnsService"
SIDO = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충청북도", "충청남도", "충북", "충남",
        "전라북도", "전북", "전라남도", "전남", "경상북도", "경북", "경상남도", "경남", "제주"]
METHOD_PATTERNS = [("방문", r"방문|직접\s*제출|내방"), ("온라인", r"온라인|홈페이지|누리집|시스템|www\.|https?://"),
                   ("이메일", r"메일|e-?mail"), ("우편", r"우편|등기")]


def fetch_bizinfo(service_key: str, per_page: int = 500, max_pages: int = 10, timeout: int = 60) -> list[dict]:
    import xml.etree.ElementTree as ET
    items: list[dict] = []
    for page in range(1, max_pages + 1):
        q = {"serviceKey": service_key, "pageNo": page, "numOfRows": per_page}
        url = BIZINFO_ENDPOINT + "?" + urllib.parse.urlencode(q)
        last = None
        for i in range(4):
            try:
                with urllib.request.urlopen(url, timeout=timeout) as r:
                    root = ET.fromstring(r.read().decode("utf-8"))
                break
            except Exception as e:  # noqa: BLE001
                last = e
                time.sleep(1.5 * (i + 1))
        else:
            raise last
        body = root.find("body")
        batch = [{c.tag: (c.text or "").strip() for c in it} for it in body.iter("item")]
        items.extend(batch)
        if len(items) >= int(body.findtext("totalCount") or 0) or not batch:
            break
    return items


def _bizinfo_region(it: dict) -> str:
    j = it.get("jrsdInsttNm", "")
    if "제주" in j or it.get("pblancNm", "").startswith("[제주]") or "제주" in it.get("excInsttNm", ""):
        return "제주"
    for sd in SIDO:
        if sd in j:
            return j
    return "전국"


def parse_bizinfo_item(it: dict) -> Program:
    import re as _re
    period = it.get("reqstBeginEndDe", "")
    m = _re.findall(r"\d{4}-\d{2}-\d{2}", period)
    start, end = (m[0], m[1]) if len(m) >= 2 else ("", "")
    text = it.get("reqstMthPapersCn", "")
    methods = {k: "사업신청방법 문장에서 자동 분류(추정)" for k, w in METHOD_PATTERNS if _re.search(w, text, _re.I)}
    org = it.get("excInsttNm", "")
    if org in ("", "직접수행", "기초자치단체"):
        org = it.get("jrsdInsttNm", "")
    summary = _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", it.get("bsnsSumryCn", ""))).strip()
    return Program(title=it.get("pblancNm", ""), field=it.get("pldirSportRealmLclasCodeNm", ""),
                   region=_bizinfo_region(it), start=start, end=end, org=org,
                   target=it.get("trgetNm", ""), stage="", age="", apply_methods=methods,
                   url=it.get("pblancUrl", ""), summary=summary[:300],
                   source="기업마당(중소벤처기업부)", period_text=period,
                   detail=" ".join(x for x in [summary, it.get("hashtags", ""),
                                               "신청 방법·서류: " + text if text else ""] if x)[:1500])
