"""제주 사장님 상권비서 패키지."""

import hashlib as _hashlib
from pathlib import Path as _Path


def code_signature() -> str:
    """패키지 .py 파일들의 이름·크기·수정 시각 요약. 메모리의 모듈이 디스크 코드와 같은지 확인할 때 쓴다."""
    d = _Path(__file__).resolve().parent
    return _hashlib.sha1("|".join(f"{f.name}:{f.stat().st_size}:{f.stat().st_mtime_ns}"
                                  for f in sorted(d.glob("*.py"))).encode()).hexdigest()


LOADED_SIG = code_signature()  # 이 패키지를 불러온 순간의 코드
