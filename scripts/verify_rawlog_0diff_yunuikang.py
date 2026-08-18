#!/usr/bin/env python3
"""가드레일 기계 검증 — raw 로거가 결정 로직을 바꾸지 않았음을 증명한다.

두 가지를 검사한다.

  [1] git 무수정
      baseline(`ThunderAgent/scheduler/router.py`·`backend/state.py`·
      `profile/state.py`), 원본 trace, 기존 driver/serve 스크립트가 tracked diff
      0줄인지.  (신규 `*_yunuikang` 파일은 untracked 이므로 무관)

  [2] run_session 결정 로직 0-diff
      `mori_replay_driver_rawlog_yunuikang.run_session_logged` 에서 **로깅 호출만**
      제거한 뒤, 원본 `mori_replay_driver_yunuikang.run_session` 과
      **토큰 단위**로 비교한다 (공백·주석·docstring 무시).

      제거 대상 = `LOG.<...>(...)` 표현식문, `MRD.` 접두, 로깅 전용 지역변수 대입,
      그리고 함수 시그니처(로깅용 인자가 추가됨).  그 외 문장이 하나라도 다르면 FAIL.

사용:  python scripts/verify_rawlog_0diff_yunuikang.py
종료코드 0 = PASS
"""
import ast
import io
import os
import subprocess
import sys
import tokenize

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIG = os.path.join(REPO, "scripts", "mori_replay_driver_yunuikang.py")
COPY = os.path.join(REPO, "scripts", "mori_replay_driver_rawlog_yunuikang.py")

# 로깅 전용으로 추가된 지역변수 — 결정에 쓰이지 않는다 (검사에서 확인).
LOG_ONLY_NAMES = {"submit_ts", "end_ts", "kv_tokens_end", "ptok", "det", "cached"}


def _src(path):
    with open(path) as f:
        return f.read()


def _find_func(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise SystemExit(f"함수 {name} 을 찾을 수 없음")


def _is_log_stmt(stmt):
    """`LOG.xxx(...)` 형태의 표현식문인가."""
    if not isinstance(stmt, ast.Expr):
        return False
    call = stmt.value
    if isinstance(call, ast.Await):
        call = call.value
    if not isinstance(call, ast.Call):
        return False
    f = call.func
    return isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "LOG"


def _is_log_assign(stmt):
    """로깅 전용 지역변수 대입인가 (`submit_ts = LOG.ts()` 등)."""
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return False
    t = stmt.targets[0]
    return isinstance(t, ast.Name) and t.id in LOG_ONLY_NAMES


def strip_logging(node):
    """AST 를 재귀적으로 훑어 로깅 문장을 제거한 새 노드를 만든다."""
    def _is_log_only_if(s):
        """`if <cond>:` 의 몸통이 **전부 로깅**이고 else 가 없는 경우.
        (예: `if guard: LOG.event('context_truncate', ...)`)
        이런 if 는 통째로 로깅이므로 제거한다.  else 가 있거나 로깅 아닌 문장이
        하나라도 섞여 있으면 제거하지 않는다 — 실제 제어흐름일 수 있으므로."""
        return (isinstance(s, ast.If) and not s.orelse and s.body
                and all(_is_log_stmt(x) or _is_log_assign(x) for x in s.body))

    # 1차 패스: 로깅만 담긴 if 를 통째로 제거한다.  **자식을 방문하기 전에** 해야
    # 한다 — 먼저 내려가면 몸통이 Pass 로 바뀌어 "전부 로깅" 판정을 못 한다.
    class DropLogIf(ast.NodeTransformer):
        def visit(self, n):
            for field in ("body", "orelse", "finalbody"):
                val = getattr(n, field, None)
                if isinstance(val, list):
                    setattr(n, field, [s for s in val if not _is_log_only_if(s)])
            return super().generic_visit(n)

    node = DropLogIf().visit(node)

    # 2차 패스: 남은 로깅 표현식문·로깅 전용 대입을 제거한다.
    class Cleaner(ast.NodeTransformer):
        def visit(self, n):
            n = super().generic_visit(n)
            for field in ("body", "orelse", "finalbody"):
                val = getattr(n, field, None)
                # IfExp/comprehension 의 body·orelse 는 리스트가 아니라 식이다 — 건너뛴다
                if isinstance(val, list):
                    kept = [s for s in val
                            if not _is_log_stmt(s) and not _is_log_assign(s)]
                    # 몸통이 비면 pass 를 넣어 문법을 유지
                    if not kept and field == "body" and isinstance(
                            n, (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler,
                                ast.FunctionDef, ast.AsyncFunctionDef, ast.With)):
                        kept = [ast.Pass()]
                    setattr(n, field, kept)
            return n
    return Cleaner().visit(node)


def normalize(node, drop_args=()):
    """비교용 정규화: docstring 제거, `MRD.` 접두 제거, 시그니처의 로깅 인자 제거."""
    node = ast.parse(ast.unparse(node)).body[0]
    # docstring
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body = node.body[1:]
    node.name = "F"
    # 시그니처에서 로깅 전용 인자 제거
    node.args.args = [a for a in node.args.args if a.arg not in drop_args]
    node.args.defaults = node.args.defaults[:max(0, len(node.args.defaults) - len(drop_args))]

    class DropMRD(ast.NodeTransformer):
        def visit_Attribute(self, n):
            self.generic_visit(n)
            if isinstance(n.value, ast.Name) and n.value.id == "MRD":
                return ast.Name(id=n.attr, ctx=n.ctx)
            return n
    node = DropMRD().visit(node)
    return ast.unparse(node)


def check_run_session():
    orig = _find_func(ast.parse(_src(ORIG)), "run_session")
    copy = _find_func(ast.parse(_src(COPY)), "run_session_logged")
    a = normalize(orig)
    b = normalize(strip_logging(copy),
                  drop_args=("session_idx", "cycle", "trace_session_id"))
    if a == b:
        print("[2] run_session 결정 로직 0-diff : PASS")
        return True
    print("[2] run_session 결정 로직 0-diff : FAIL")
    import difflib
    for line in difflib.unified_diff(a.splitlines(), b.splitlines(),
                                     "original", "rawlog(stripped)", lineterm="", n=2):
        print("    " + line)
    return False


PROTECTED = [
    "ThunderAgent/scheduler/router.py",
    "ThunderAgent/backend/state.py",
    "ThunderAgent/profile/state.py",
    "scripts/mori_replay_driver_yunuikang.py",
    "scripts/trace_replay_driver_yunuikang.py",
    "scripts/mori_hicache_yunuikang.py",
    "scripts/mori_tierc_instrument_yunuikang.py",
    "scripts/sitecustomize.py",
    "scripts/prep_tracelab_mori_yunuikang.py",
    "scripts/_serve_sglang_7b_tp1_5090_mori_yunuikang.sh",
]


def check_git():
    out = subprocess.run(["git", "-C", REPO, "status", "--porcelain"],
                         capture_output=True, text=True).stdout
    modified = [l for l in out.splitlines() if l and not l.startswith("??")]
    if modified:
        print("[1] tracked 파일 무수정 : FAIL")
        for l in modified:
            print("    " + l)
        return False
    print(f"[1] tracked 파일 무수정 : PASS (tracked diff 0줄)")
    # 보호 대상이 실제로 존재하고 clean 한지 이중 확인
    missing = [p for p in PROTECTED if not os.path.exists(os.path.join(REPO, p))]
    if missing:
        print("    WARN: 보호 대상 중 없는 파일: " + ", ".join(missing))
    return True


if __name__ == "__main__":
    ok = check_git()
    ok = check_run_session() and ok
    print("\nRESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
