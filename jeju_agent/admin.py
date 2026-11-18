"""운영자 PIN: 운영자 설정(API 키·데이터 폴더·바로가기)은 PIN을 아는 사람만 연다.

- PIN 원문은 저장하지 않는다. PBKDF2-SHA256(무작위 salt, 20만 회) 해시만 config/local_settings.json에 둔다.
- PIN은 숫자 6~12자리(4자리는 1만 가지라 잠금이 있어도 오래 시도하면 뚫린다).
- PIN은 설치할 때(install.bat) 정하거나 명령으로 정한다: python -m jeju_agent.admin set-pin
  이미 PIN이 있으면 현재 PIN을 먼저 물어 방문자가 덮어쓰지 못하게 한다.
- PIN이 없으면 운영자 설정은 열리지 않는다(방문자가 먼저 PIN을 정해 잠가 버리는 일을 막음).
- 틀린 횟수는 설정 파일에 남겨 앱을 다시 켜도 이어진다. 5번 틀리면 5분 → 15분 → 60분 잠금.
- 잊었을 때: python -m jeju_agent.admin reset → PIN과 저장된 키(AI·데이터허브·공공데이터포털)를 함께 지운다.
  방문자가 실행해도 키는 얻지 못하고 AI가 꺼질 뿐이라 운영자가 바로 알아챈다.

정직하게: 키는 같은 PC 계정이면 설정 파일을 열어 볼 수 있다. PIN은 실수·호기심을 막는 장치이고,
비용을 지키는 진짜 장치는 공급자 쪽 프로젝트 월 예산 한도와 앱의 월 한도, 정기적인 키 교체다(README).
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import os
import time
from datetime import datetime

from .llm import load_settings, save_settings

ITER = 200_000
MAX_TRIES = 5
LOCK_STEPS = [300, 900, 3600]          # 5번 틀릴 때마다 5분 → 15분 → 60분
KEY_FIELDS = ("api_key", "jejudatahub_app_key", "data_go_kr_key")


def _hash(pin: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, ITER).hex()


def valid_pin(pin: str) -> bool:
    return pin.isdigit() and 6 <= len(pin) <= 12


def has_pin() -> bool:
    return bool(load_settings().get("operator_pin_hash"))


def _verify(pin: str, s: dict) -> bool:
    h, salt = s.get("operator_pin_hash"), s.get("operator_pin_salt")
    return bool(h and salt and pin) and hmac.compare_digest(_hash(pin, bytes.fromhex(salt)), h)


def set_pin(pin: str, current: str | None = None) -> None:
    s = load_settings()
    if s.get("operator_pin_hash") and not _verify(current or "", s):
        raise PermissionError("현재 PIN이 맞지 않습니다. PIN을 잊었다면 reset으로 초기화하세요.")
    if not valid_pin(pin):
        raise ValueError("PIN은 숫자 6~12자리로 정해 주세요.")
    salt = os.urandom(16)
    s.update(operator_pin_hash=_hash(pin, salt), operator_pin_salt=salt.hex(), operator_pin_fails=[],
             operator_pin_lock_level=0)
    save_settings(s)


def locked_for() -> int:
    """연속으로 틀려 잠긴 경우 남은 초."""
    s = load_settings()
    until = float(s.get("operator_pin_locked_until", 0) or 0)
    return max(0, int(until - time.time()))


def check_pin(pin: str) -> bool:
    if locked_for():
        return False
    s = load_settings()
    ok = _verify(pin, s)
    if ok:
        s.update(operator_pin_fails=[], operator_pin_lock_level=0, operator_pin_locked_until=0)
    else:
        fails = list(s.get("operator_pin_fails", [])) + [time.time()]
        if len(fails) >= MAX_TRIES:
            lvl = int(s.get("operator_pin_lock_level", 0) or 0)
            s["operator_pin_locked_until"] = time.time() + LOCK_STEPS[min(lvl, len(LOCK_STEPS) - 1)]
            s["operator_pin_lock_level"] = lvl + 1
            fails = []
        s["operator_pin_fails"] = fails
    save_settings(s)
    return ok


def reset() -> None:
    """PIN 분실 시: PIN과 저장된 키를 함께 지우고 기록을 남긴다."""
    from .llm import USAGE
    s = load_settings()
    for k in ("operator_pin_hash", "operator_pin_salt", "operator_pin_fails", "operator_pin_lock_level",
              "operator_pin_locked_until", *KEY_FIELDS):
        s.pop(k, None)
    save_settings(s)
    USAGE.parent.mkdir(parents=True, exist_ok=True)
    with USAGE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "model": "-",
                            "purpose": "운영자 PIN 초기화(키 삭제)", "in": 0, "out": 0, "cost_usd": 0},
                           ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="운영자 PIN 관리")
    ap.add_argument("cmd", choices=["set-pin", "status", "reset"])
    ap.add_argument("--pin", help="(자동 설치용) 새 PIN을 인자로 줄 때. 생략하면 화면에서 묻습니다.")
    ap.add_argument("--current", help="(자동 설치용) 현재 PIN")
    a = ap.parse_args()
    if a.cmd == "status":                       # 종료 코드: 0 설정됨, 3 없음(설치 스크립트가 씀)
        print("운영자 PIN: " + ("설정됨" if has_pin() else "없음"))
        raise SystemExit(0 if has_pin() else 3)
    if a.cmd == "reset":
        if input("PIN과 저장된 API 키를 모두 지웁니다. 계속하려면 '초기화'를 입력하세요: ").strip() != "초기화":
            raise SystemExit("취소했습니다.")
        reset()
        print("PIN과 키를 지웠습니다. set_pin.bat으로 PIN을 다시 정하고, 운영자 페이지에서 키를 다시 넣어 주세요.")
        return
    current = a.current
    if has_pin() and current is None:
        current = getpass.getpass("현재 운영자 PIN(화면에 보이지 않음): ")
    pin = a.pin or getpass.getpass("새 운영자 PIN(숫자 6~12자리, 화면에 보이지 않음. 건너뛰려면 Enter): ")
    if not pin.strip():
        print("PIN을 정하지 않았습니다. 운영자 설정은 PIN을 정한 뒤에 열립니다(set_pin.bat).")
        return
    if not a.pin and pin != getpass.getpass("한 번 더 입력: "):
        raise SystemExit("두 PIN이 다릅니다. 다시 실행해 주세요.")
    try:
        set_pin(pin.strip(), current)
    except (ValueError, PermissionError) as e:
        raise SystemExit(str(e)) from None
    print("운영자 PIN을 저장했습니다(해시만 저장).")


if __name__ == "__main__":
    main()
