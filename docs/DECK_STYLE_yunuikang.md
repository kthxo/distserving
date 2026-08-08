# 발표덱 제작 가이드 (yunuikang house style)

> **이 문서의 용도**: 새 세션에서 "PPT 만들어줘"를 받았을 때 **이 문서를 먼저 읽고 그대로 따른다.**
> 여기 적힌 규칙은 기존 덱 5개(`slides/*.pptx`)에서 실제로 쓰인 것이고, 그 과정에서 겪은
> 실패 사례까지 포함한다. 취향이 아니라 **재현 규격**이다.
>
> 최종 갱신: 2026-08-05 · 근거 덱: `slides/2026-08-04_MORI_code-verification_yunuikang.pptx` (24장)

---

## 0. 먼저 알아야 할 것

- **`pptx` 스킬은 이 머신에 없다.** `Skill: Unknown skill: pptx`가 뜬다 (`~/.claude/skills/` 비어 있음).
  사용자가 "pptx 스킬을 쓰라"고 해도 **없다는 사실을 보고**하고 아래 하우스 툴체인으로 진행한다.
- **툴체인**: `python-pptx` (1.0.2) + 하우스 라이브러리 **`scripts/decklib_yunuikang.py`**.
  덱마다 `scripts/build_<이름>_deck_yunuikang.py` 빌더를 새로 쓰고, decklib을 import 한다.
- **덱은 손으로 만들지 않는다.** 항상 **빌더 스크립트**로 만든다 —
  수치가 바뀌면 스크립트를 고쳐 재생성한다. `.pptx`를 직접 편집하지 않는다.
- **LibreOffice가 없다** → 렌더링 확인 불가. 그래서 **기하 검사기(§8)로 대신**한다. 이건 선택이 아니다.

---

## 1. 캔버스 · 팔레트 (decklib 상수 — 바꾸지 않는다)

```
슬라이드   16:9 · 13.333 × 7.5 in
좌우 여백  0.42 in  (본문 폭 12.5 in)
```

| 이름 | 값 | 용도 |
|---|---|---|
| `INK` | `#1A1A2E` | 본문·제목·상단 밴드 |
| `BLUE` | `#2E5EAA` | TA+O / 베이스라인 / 긍정 |
| `RED` | `#C0392B` | MORI / 스래싱 / 경고 |
| `GREEN` | `#1E7D4F` | PASS · 개선 |
| `AMBER` | `#B87A1E` | 주의 · 중간값 |
| `GRAY` | `#6B6B7B` | 각주 · 축 라벨 |
| `LT` | `#F2F4F8` | 옅은 배경 |
| `PANEL` | `#F4F6FA` | 구역 패널 배경 (빌더에서 정의) |
| `PURPLE` | `#6E4B9E` | 세 번째 계열 (빌더에서 정의) |

이 4색(`#6E4B9E, #B87A1E, #2E5EAA, #C0392B`)은 **CVD 검증을 통과한 조합**이다
(최악 쌍 ΔE 18.8). 계열을 늘려야 하면 임의로 추가하지 말고 dataviz 스킬의 validator를 돌린다.

---

## 2. 슬라이드 해부 — 모든 슬라이드가 같은 뼈대

```
┌────────────────────────────────────────────┐
│▬▬▬▬▬▬▬▬▬▬ INK 밴드 (y=0, h=0.11) ▬▬▬▬▬▬▬▬▬│
│  제목            y=0.28  size 27  bold     │
│  한 줄 takeaway  y=1.12  size 15  bold+ital│
│                                            │
│  ← 본문 영역  y 1.60 ~ 7.00 →              │
│                                            │
│  각주 footer    y=7.06  size 8.5  GRAY     │
└────────────────────────────────────────────┘
```

빌더마다 아래 3개 헬퍼를 상단에 정의한다 (복붙해서 쓴다):

```python
def slide(title, takeaway=None, tw_color=BLUE):
    s = _blank(prs)
    band(s, 0.0, 0.11, INK)
    add_title(s, title)
    if takeaway:
        add_takeaway(s, takeaway, color=tw_color)
    return s

def zone(s, n, label, x, y, w, h, color):
    """번호칩 + 제목 + 배경 패널 = 구역 하나."""
    p = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    p.fill.solid(); p.fill.fore_color.rgb = PANEL
    p.line.color.rgb = RGBColor(0xDD, 0xE1, 0xE8); p.line.width = Pt(0.75)
    p.shadow.inherit = False
    chip(s, f"{n}  {label}", x + 0.12, y + 0.10, min(w - 0.24, 4.5), color, size=10.5, h=0.30)
    return p

def footer(s, txt):
    add_text(s, txt, 0.42, 7.06, 12.5, 0.3, size=8.5, color=GRAY)
```

**표지**: 전면 `INK` 밴드 + 제목 44pt WHITE + 부제 19pt `#9FB6D8` + 짧은 BLUE 밑줄(h=0.035).

---

## 3. ★ 검증 슬라이드의 3구역 패턴 (핵심 양식)

"우리 코드가 맞는지 확인했다"류 슬라이드는 **반드시 같은 세 구역**으로 만든다.
보는 사람이 슬라이드마다 어디를 볼지 다시 배우지 않아도 된다.

| 구역 | 칩 색 | 내용 |
|---|---|---|
| **①** | `PURPLE` | **논문/명세가 이렇게 규정한다** — 인용 또는 규칙 문장 |
| **②** | `AMBER` | **그래서 이런 실험을 설계했다** — 픽스처, 심어둔 함정, 대안 정책 |
| **③** | `GREEN`(통과) / `RED`(실패) | **측정된 결과와 판정** — 숫자 + PASS/FAIL |

이 패턴의 핵심은 ②의 **"심어둔 함정"**이다 — *"이 규칙을 틀리게 구현했다면 반드시 다른 답이
나오도록 픽스처를 짰다"*를 명시한다. 이게 없으면 "통과했다"는 말에 정보가 없다.

---

## 4. 내용 규칙 — 숫자와 라벨

### 4.1 숫자는 로그에서만 온다

- **로그가 진실이다.** 슬라이드의 모든 수치는 `logs/*.md` 또는 분석기 JSON에서 **직접 추출**한다.
- 추출은 스크립트로 한다 (`scripts/extract_*_numbers_yunuikang.py` → `scratch/.../deck_numbers.json`),
  빌더는 그 JSON만 읽는다. **빌더에 수치 하드코딩 금지.**
- **로그에 없는 값은 지어내지 않는다. `TBD`로 둔다.** 이건 협상 대상이 아니다.
- 덱을 만든 뒤 **수치가 실제로 로그에 존재하는지 대조 검증**한다(간단한 grep 스크립트로 충분).

### 4.2 출처 라벨을 문장마다 붙인다

| 라벨 | 뜻 |
|---|---|
| **[측정]** | 이 환경에서 직접 관측·확인한 값 |
| **[추론]** | 측정에서 끌어낸 해석 |
| **[추정]** | 계산·외삽·가정 |
| **[논문-인용]** | 논문/외부 문서 근거 |

경계가 애매하면 **약한 쪽**을 쓴다. `[측정→추론]`처럼 붙여 써도 된다.

### 4.3 정직성

- 예측이 빗나갔으면 **빗나간 슬라이드를 만든다.** 지우지 않는다.
- 사전 등록한 판정 기준을 결과 보고 바꾸지 않는다. 관측이 등록한 분기를 벗어났으면
  **"3번째 패턴"이라고 명시**한다.
- n·반복 횟수·변동폭을 각주에 적는다. `n=1`이면 그렇게 쓴다.

---

## 5. 그림 vs 표 — 무엇을 언제

| 내용 | 형태 |
|---|---|
| **개념·구조·인과** | **다이어그램** (matplotlib patches로 직접 그림) |
| **측정 데이터** | **표** 또는 **선/막대 그래프** |
| 한 개의 헤드라인 숫자 | 큰 글씨 스탯 타일 (20pt bold + 라벨 10pt + 해석 10pt) |

그림은 `figures/<이름>_yunuikang.png`에 **별도 플롯 스크립트**로 만들고
(`scripts/plot_*_yunuikang.py`), 덱은 `add_figure(s, "<이름>", x, y, max_w, max_h)`로 넣는다.
`add_figure`는 종횡비를 지키며 박스 안에 맞춰 중앙 정렬한다.

### 5.1 matplotlib 규칙

```python
plt.rcParams["font.family"] = "Noto Sans CJK KR"     # 한글 필수
plt.rcParams["axes.unicode_minus"] = False
```

- **이중 축(dual-axis) 절대 금지.** 단위가 다르면 **패널을 나눈다.**
- 계열 2개 이상이면 **범례 + 직접 라벨** 둘 다. 모든 점에 숫자 붙이지 않는다(선택적으로).
- 위/아래 라벨 오프셋은 **그 x에서 누가 더 높은지로 결정**한다 — 안 그러면 교차 지점에서 겹친다.
- 축 스타일: top/right spine 제거, 나머지는 `#DDE1E8`, y 그리드만, `set_axisbelow(True)`.
- 마커는 `markeredgecolor="white", markeredgewidth=1.2`로 겹침 구분.
- 덱용은 **단일 패널 축약본을 따로** 만든다 (3패널을 슬라이드에 넣으면 글자가 안 보인다).
  파일명 `*_deck_yunuikang.png`.
- **그린 뒤 반드시 Read 툴로 이미지를 열어 눈으로 확인한다.** 경고 없이도 겹친다.

---

## 6. 발표자 노트 — 전 슬라이드 필수

- **모든 슬라이드에 노트를 단다.** 예외 없음.
- **쉬운 한국어 구어체**로 쓴다. 슬라이드를 못 봐도 이해되게.
  - "이 슬라이드가 보여주는 건 …입니다", "맨 위 세 숫자만 보시면 됩니다"
- 표에서 **오해할 수 있는 지점을 짚어준다**
  (예: "TA+O의 축출 숫자는 다른 사건을 센 거라 두 시스템 비교는 의미가 없습니다").
- **한계도 노트에 말한다** — "셀마다 한 번씩만 돌렸습니다", "메커니즘은 아직 모릅니다".
- 전문용어는 처음 나올 때 한 번 풀어준다 (fit = GPU에 동시에 올라가는 프로그램 수).

---

## 7. ⚠️ 반드시 아는 함정 (전부 실제로 당한 것)

| # | 함정 | 대응 |
|---|---|---|
| 1 | **`**굵게**` 마크다운이 그대로 찍힘** | decklib에 파서가 없었다 → `_md_runs`/`_set_md_text`로 해결됨(2026-08-05). **decklib 최신본을 쓰면 자동 처리**. 직접 `text_frame.text = ...`를 쓰면 다시 깨진다 — 반드시 `add_text`/`add_table` 헬퍼 경유 |
| 2 | **표가 선언한 높이보다 커진다** | python-pptx의 `h`는 최소값일 뿐, PowerPoint가 내용에 맞춰 늘린다. 아래 요소와 **0.3 in 이상** 띄운다 |
| 3 | **`col_widths` 합이 `w`를 덮어쓴다** | 표 실제 폭 = `sum(col_widths)`. `w`는 무시된다. 우측 경계 계산은 합으로 한다 |
| 4 | **제목이 2줄이 되면 takeaway와 겹친다** | 제목은 27pt에서 한 줄(≈12.6 in)을 넘기지 않게 짧게. 넘치면 문장을 줄인다 |
| 5 | **긴 각주가 footer(y=7.06)를 침범** | 본문 마지막 요소는 `y+h ≤ 7.00` |
| 6 | **범례가 데이터 위에 앉는다** | `loc`을 데이터 비어 있는 사분면으로. 안 되면 x축 눈금 라벨에 정보를 넣는다(`"r=2\nWaiting 11건"`) |
| 7 | **여러 덱이 decklib을 공유** | decklib을 고치면 **다른 덱 빌더도 돌려 회귀 확인**. 단, 빌더 중 일부는 옛 세션의 스크래치 경로에 의존해 실패한다(정상 — 저장 전에 죽으므로 기존 덱은 안전) |

---

## 8. 레이아웃 QA — 렌더러가 없으므로 필수

```bash
python3 scripts/deck_qa_yunuikang.py slides/<파일>.pptx
```

**"실질 문제: 0"이 나올 때까지 고친다.** 이 검사기는 선언된 박스가 아니라
**렌더링될 텍스트 실제 범위를 추정**해서(한글 1.0em / 라틴 0.52em, 자동 줄바꿈 반영)
겹침과 화면 넘침을 잡는다.

추가로 확인할 것:
```bash
# 리터럴 ** 가 남아 있지 않은지
python3 -c "
from pptx import Presentation
p=Presentation('slides/<파일>.pptx')
n=sum('**' in s.text_frame.text for sl in p.slides for s in sl.shapes if s.has_text_frame)
m=[i for i,sl in enumerate(p.slides,1) if not sl.notes_slide.notes_text_frame.text.strip()]
print('리터럴 ** :', n, '· 노트 없는 슬라이드:', m or '없음')"
```

---

## 9. 파일 명명

| 종류 | 형식 |
|---|---|
| 덱 | `slides/YYYY-MM-DD_<주제>_yunuikang.pptx` |
| 빌더 | `scripts/build_<주제>_deck_yunuikang.py` |
| 그림 | `figures/<주제>_yunuikang.png` · 덱용 축약 `..._deck_yunuikang.png` |
| 수치 추출 | `scripts/extract_<주제>_numbers_yunuikang.py` → `scratch/.../deck_numbers.json` |

**모든 산출물에 `_yunuikang` 접미사.** 커밋은 사용자가 명시적으로 요청할 때만.

---

## 10. 제작 체크리스트

- [ ] 로그/JSON에서 수치 추출 스크립트 작성 → 빌더는 JSON만 읽는가
- [ ] 슬라이드마다 제목 + 한 줄 takeaway가 있는가
- [ ] 검증류 슬라이드가 ①논문 → ②실험설계(함정 포함) → ③측정+판정 3구역인가
- [ ] 모든 수치에 [측정]/[추론]/[추정]/[논문-인용] 라벨이 붙었는가
- [ ] 로그에 없는 값을 지어내지 않았는가 (없으면 TBD)
- [ ] 개념은 다이어그램, 데이터는 표/그래프인가
- [ ] 그림을 Read 툴로 열어 눈으로 확인했는가 (이중 축 없음, 라벨 안 겹침)
- [ ] **전 슬라이드에 쉬운 한국어 발표자 노트**가 있는가
- [ ] 한계·n수·변동폭을 명시했는가
- [ ] `deck_qa_yunuikang.py` → **실질 문제: 0**
- [ ] 리터럴 `**` 0개
