# AI Usage Widget 🐱

**Claude와 GPT를 얼마나 썼는지** 화면 한구석에 항상 떠 있는 작은 카드로 보여주는 Windows 위젯입니다.

- **보이는 것**: claude.ai 채팅 + Claude Code 사용량(둘이 한도를 공유), GPT의 Codex·ChatGPT Work 사용량
- **안 보이는 것**: ChatGPT 일반 채팅 한도, Gemini 채팅 한도 (조회할 방법이 공개되어 있지 않음)
- Claude Code나 Codex를 **쓰지 않아도** 됩니다. 로그인만 해 두면 채팅 사용량이 보입니다.

![preview](docs/preview.png)

작업표시줄 미니 모드 (더블클릭으로 전환):

![taskbar](docs/taskbar-mini.png)

캐릭터 스타일 (우클릭 메뉴에서 선택):

![characters](docs/characters.png)

## 설치

1. 오른쪽 **Releases**에서 최신 ZIP을 받아 압축을 풉니다.
2. 폴더 안의 **`install.bat`** 을 더블클릭합니다.
   - 파란색 "Windows의 PC 보호" 경고가 뜨면 **추가 정보 → 실행**
   - 설치 중 "이 앱이 디바이스를 변경하도록 허용하시겠어요?" 창이 뜨면 **예**
3. 화면 안내대로 따라갑니다. 사람이 하는 건 다음뿐입니다.
   - **Claude 로그인** (브라우저 1회): 검은 화면에서 "Claude account with subscription" 선택 → 브라우저 로그인 → 검은 화면에 `/exit` 입력
   - **"Codex나 ChatGPT Work를 쓰시나요?"** → 쓰면 Y(브라우저 로그인 1회 더), 채팅만 쓰면 N
   - **"Windows 켤 때 자동 실행?"** → Y/N

끝나면 화면 왼쪽 위에 카드가 뜹니다. ZIP을 다운로드 폴더에서 풀었다면 설치 스크립트가 파일을 `%LOCALAPPDATA%\Programs\ai-usage-widget`로 옮겨 두니, 다운로드 폴더를 지워도 괜찮습니다.

설치 스크립트가 자동으로 하는 일: Python·Pillow 설치, Win-CodexBar 설치와 설정(Claude 읽기 허용, 트레이 앱 자동 실행 끄기), Claude Code 설치, (Y일 때) Node.js·Codex CLI 설치, 바탕화면 바로가기.

## 화면 읽는 법

마우스를 올리면 각 요소 설명이 뜹니다. 요약:

| 표시 | 뜻 |
|---|---|
| **5시간** 도넛 | 최근 5시간 동안 쓴 비율. 100%가 되면 표시된 시각에 0%로 리셋 |
| **7일** 도넛 | 최근 7일 동안 쓴 비율. 5시간 창과 별도 |
| 도넛 색 | 초록 50% 미만 · 노랑 50~80% · 빨강 80% 이상 |
| **Fable 주간** 막대 | Claude의 Fable 모델 전용 주간 한도. 7일 전체보다 먼저 차는 경우가 많음 |
| 도넛 아래 "N시간 후" | 리셋까지 남은 시간. "다음 사용 시 시작"은 새 창이 아직 열리지 않았다는 뜻 |
| 여유 / 빠듯 / 부족 예상 | (옵션) 지금 속도면 리셋 전에 한도가 남을지 |
| 우상단 "갱신 HH:MM" | 마지막 조회 시각. "· 1분 갱신"은 사용량이 오르는 중이라 자주 조회한다는 뜻 |
| "N분 전 값" (주황) | 10분 넘게 조회에 실패해 옛 값을 보여주는 중. 1시간 넘으면 회색 |
| "조회 실패 · doctor.bat 실행" | 한 번도 값을 못 받음 → `doctor.bat` |
| "재로그인 필요 · install.bat 다시 실행" | 로그인이 만료됨 → `install.bat` 다시 실행하면 로그인 화면만 다시 뜸 |
| 고양이 | 5시간 사용률이 높을수록 빨리 달리고, 100%면 잠듦 |
| 미니 모드 "5h 23% · 7d 41%" | 5시간 · 7일 사용률 |

## 조작

| 동작 | 방법 |
|---|---|
| 이동 | 드래그 (위치 자동 저장) |
| 작업표시줄 미니 모드 | 더블클릭 (다시 더블클릭하면 카드로). 미니 상태에서 좌우 드래그로 자리 조정 |
| 새로고침 / 종료 | 우상단 ↻ / ✕ (✕는 완전 종료. 다시 켜려면 바탕화면 바로가기) |
| 켜기 / 끄기 | 바탕화면 "AI 사용량 위젯" 더블클릭 (토글) |
| 설정 | 우클릭 메뉴 |

우클릭 메뉴:

- **캐릭터 스타일**: 부드러운 고양이(기본) / 도트 고양이 / 없음
- **Claude 표시 / GPT 표시**: 한쪽만 남길 수 있음 (카드가 절반 폭으로)
- **작업표시줄 미니 모드**
- **투명도**: 100 / 85 / 70 / 55%
- **소진 예측 표시**: 도넛 아래에 여유/빠듯/부족 예상 표시
- **알림 (80% · 100% · 리셋)**: 화면 팝업(고양이 카드) / 소리(100% 소진·리셋 때만) / Windows 알림 센터. 80% 경고와 리셋 알림은 5시간 창만, 100% 소진은 5시간·7일 모두
- **클릭 통과 모드**: 다른 창이 활성일 땐 마우스가 위젯을 통과. 바탕화면을 클릭하거나 Ctrl을 누른 채로만 조작 가능. 켤 때 확인창이 뜸
- **항상 위에 표시**, **전체화면 앱 실행 시 숨김**(같은 모니터에서 영상·게임·발표 중 자동 숨김), **Windows 시작 시 자동 실행**
- **새 버전 자동 확인** (하루 1회) / **지금 업데이트 확인**: 새 버전이면 팝업 → 클릭 → 확인 창 → 자동 교체·재시작

## 문제 해결

숫자가 안 뜨면 먼저 **`doctor.bat`** 을 더블클릭하세요. Python·Win-CodexBar·로그인 파일을 점검하고 실제 조회까지 해 본 뒤, 막힌 곳과 해결 방법을 알려줍니다 (오류 원문은 영어, 해결책은 한글).

| 어디서 | 메시지 | 뜻 / 해결 |
|---|---|---|
| doctor, CodexBar | `Reading Claude Code's credentials is off` | CodexBar의 Claude 읽기 허용이 꺼짐. `install.bat` 다시 실행(자동 설정) 또는 아래 "CodexBar 수동 설정" |
| doctor, CodexBar | `OAuth access token has expired` / `Re-authenticate` | Claude 로그인 만료. `install.bat` 다시 실행하면 로그인 화면만 다시 뜸 |
| doctor, CodexBar | `usage endpoint is rate limited` | 조회가 너무 잦아 잠시 차단. 5~10분 뒤 자동 회복. CodexBar 트레이 앱이 켜져 있으면 종료 |
| doctor, CodexBar | `Claude usage failed from all configured sources. Web: …; OAuth: …; CLI: …` | 가운데 OAuth 부분 문구로 위 두 줄 중 해당 항목 적용. Web/CLI 부분은 무시 |
| CodexBar | `App-Bound Encryption … cookies failed to decrypt` | 브라우저 쿠키 안내. 위젯은 쿠키를 쓰지 않으므로 무시 |
| CodexBar | `Not logged in to Gemini` | Gemini는 지원 안 함. CodexBar 제공업체에서 Gemini 체크 해제 |
| doctor, CodexBar | Codex `Not logged in` / `Authentication required` / `Codex account not found` | Codex 로그인 없음. 터미널에서 `codex login`. 안 쓰면 위젯 우클릭 → GPT 표시 해제 |
| 터미널 | `'claude'은(는) 내부 또는 외부 명령… 아닙니다` | Claude Code는 깔렸는데 경로 미등록. `install.bat` 다시 실행하면 등록됨 |
| 로그인 화면 | 로그인 방식 선택 | **"Claude account with subscription"** 선택. API 키 방식은 한도가 없어 숫자가 안 뜸 |
| 위젯 | Claude 자리 `–` | 위 Claude 항목 중 하나. `doctor.bat`으로 확인 |
| 위젯 | GPT 자리 `–` | Codex를 안 쓰면 정상. 우클릭 → GPT 표시 해제 |
| 설치 | Python 설치 실패 | winget이 없는 PC. python.org에서 설치(Add to PATH 체크) 후 `install.bat` 재실행 |
| 아무 반응 없음 | | 폴더의 `widget.log` 확인. 위젯이 사라졌다면 전체화면 앱 때문에 숨은 것일 수 있음 (앱을 닫으면 복귀) |

### CodexBar 수동 설정 (자동 설정이 실패했을 때만)

위젯은 [Win-CodexBar](https://github.com/nesszer/Win-CodexBar)의 명령줄 도구로 사용량을 읽습니다. `install.bat`이 설정을 자동으로 써 넣지만, 실패했거나 CodexBar 업데이트로 초기화됐다면:

1. 시작 메뉴에서 CodexBar 실행 → 작업표시줄 시계 옆 트레이 아이콘 우클릭 → **Settings**
2. 상단 **제공업체(Providers)** → **Claude** → **"Allow reading Claude Code's credentials"** 체크
3. 쓰지 않는 제공자(Gemini, Copilot 등)는 체크 해제 (선택)
4. 트레이 아이콘 우클릭 → **Quit**. 트레이 앱과 위젯이 동시에 조회하면 차단될 수 있어 위젯만 쓰는 편이 안정적입니다

## 동작 원리

- 위젯은 인증을 직접 하지 않습니다. Win-CodexBar의 `codexbar-cli.exe usage --source oauth`를 주기적으로 실행해 결과(JSON)만 읽습니다. 토큰 파일(`~/.claude/.credentials.json`, `~/.codex/auth.json`)만 읽고, 브라우저 쿠키나 `claude` 명령은 건드리지 않습니다.
- 조회 주기는 사용량이 오르는 중이면 1분, 멈춰 있으면 3~5분, 실패하면 2배씩 물러납니다. 부팅 자동 실행이면 첫 조회를 2분 늦춥니다.
- 카드는 값이 바뀔 때만 다시 그려 CPU를 거의 쓰지 않습니다.
- 하루 한 번 GitHub Releases를 확인해 새 버전이면 알려줍니다.

## 커스터마이즈

`usage_widget.py` 상단의 상수를 바꾸면 됩니다. 색(`CARD`, `C_OK`, `C_WARN`, `C_BAD`, `PROVIDERS_ALL`), 크기(`W`, `H`, `GAUGE`), 조회 주기(`REFRESH_*`), 고양이 도트(`CAT_BODY`, `CAT_LEGS`), 툴팁 문구(`TIPS`). 폰트는 Paperlogy → Pretendard → 맑은 고딕 순으로 찾습니다.

디버그: 환경변수 `WIDGET_SNAP=경로.png`로 렌더 결과 저장. 오류는 `widget.log`.

## 한계

- Win-CodexBar CLI의 출력 형식과 Anthropic·OpenAI의 비공식 조회 방식에 의존합니다. 바뀌면 Win-CodexBar 업데이트를 기다려야 합니다.
- Windows 전용.

## 라이선스

MIT
