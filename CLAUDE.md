# distserving — 작업 규칙

## 발표덱(PPT/슬라이드) 제작

발표덱을 만들거나 고쳐 달라는 요청을 받으면, **작업을 시작하기 전에
`docs/DECK_STYLE_yunuikang.md`를 읽고 그 규격을 그대로 따른다.** 새 양식을 임의로 만들지 않는다.

특히 자주 놓치는 것:
- 이 머신에 **`pptx` 스킬이 없다.** 사용자가 지정해도 없다는 사실을 먼저 보고하고,
  하우스 툴체인(`scripts/decklib_yunuikang.py` + python-pptx)으로 진행한다.
- 덱은 손으로 만들지 않고 **빌더 스크립트**(`scripts/build_*_deck_yunuikang.py`)로 생성한다.
- 수치는 `logs/*.md`/JSON에서 추출해 쓰고, **없으면 지어내지 말고 `TBD`**.
- 문장마다 **[측정]/[추론]/[추정]/[논문-인용]** 라벨.
- **전 슬라이드에 쉬운 한국어 발표자 노트** 필수.
- 렌더러가 없으므로 `python3 scripts/deck_qa_yunuikang.py <덱>` → **"실질 문제: 0"** 까지 맞춘다.
  그림은 Read 툴로 직접 열어 눈으로 확인한다.

## 산출물 규칙

- 모든 산출물 파일명에 **`_yunuikang`** 접미사. 날짜 접두사는 `YYYY-MM-DD_`.
- 주요 보고는 채팅과 **`logs/YYYY-MM-DD_<주제>_yunuikang.md`** 에 함께 남긴다.
- 계획은 `plans/`, 덱은 `slides/`, 그림은 `figures/`, 규격 문서는 `docs/`.
- **시각은 KST로 보고한다** (머신이 UTC이므로 +9시간).

## 변경 범위

- **커밋은 사용자가 명시적으로 요청할 때만** 한다.
- baseline(`scheduler/router.py`, `backend/state.py`, `profile/state.py`), 원본 트레이스,
  기존 실험 스크립트는 **수정하지 않는다.** 필요하면 새 파일을 만든다.
