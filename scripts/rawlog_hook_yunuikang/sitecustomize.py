"""raw-log 훅용 sitecustomize — 기존 `scripts/sitecustomize.py` 를 0-diff 로 둔 채 확장.

왜 이 파일이 따로 필요한가
--------------------------
Python 은 sys.path 에서 **처음 발견한** `sitecustomize` 하나만 import 한다.
기존 `scripts/sitecustomize.py` 는 MORI typed-eviction 패치와 Tier C 계측을 건다.
raw 로거를 추가하려면 그 파일을 고치거나(=무수정 원칙 위반) 더 앞선 경로에 새
sitecustomize 를 두어야 한다.  후자를 택한다.

동작
----
러너가 PYTHONPATH 를 `<이 디렉터리>:<repo>/scripts` 순으로 준다.
그러면 이 파일이 먼저 로드되고, 아래에서 원본을 **경로로 직접 실행**해
기존 동작(SGLANG_MORI_PATCH · MORI_TIERC)을 하나도 빠뜨리지 않고 재현한 뒤,
raw 로거를 추가로 건다.

이 파일은 SGLang 이 spawn 하는 스케줄러 서브프로세스에서도 실행된다
(그 프로세스들은 sglang 을 새로 import 하므로 부모의 monkeypatch 를 물려받지 않는다).
"""
import os
import sys

# 1) 원본 sitecustomize 를 경로로 실행 — 기존 동작 100% 보존.
_here = os.path.dirname(os.path.abspath(__file__))
_orig = os.path.join(os.path.dirname(_here), "sitecustomize.py")
if os.path.exists(_orig):
    try:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "sitecustomize_orig_yunuikang", _orig)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
    except Exception as e:      # 절대로 인터프리터 시작을 깨뜨리지 않는다
        print(f"[sitecustomize-rawlog] 원본 체이닝 실패: {e!r}", file=sys.stderr)
else:
    print(f"[sitecustomize-rawlog] 원본 없음: {_orig}", file=sys.stderr)

# 2) raw 로거 (엔진 쪽 kv_events).  MORI_RAWLOG=1 일 때만 동작한다.
if os.environ.get("MORI_RAWLOG") == "1":
    try:
        import mori_rawlog_yunuikang
        mori_rawlog_yunuikang.install()
    except Exception as e:
        print(f"[sitecustomize-rawlog] raw 로거 skip: {e!r}", file=sys.stderr)
