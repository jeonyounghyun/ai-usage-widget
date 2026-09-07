# AI Usage Widget 🐱

Claude Code / OpenAI Codex 사용량 한도(5시간·7일)를 화면에 **항상 떠 있는 작은 카드**로 보여주는 Windows 위젯입니다.
RunCat처럼 픽셀 고양이가 달리는데, 한도를 많이 쓸수록 빨리 달리고 100%가 되면 잠듭니다.

![preview](docs/preview.png)

작업표시줄 미니 모드 (더블클릭으로 전환):

![taskbar](docs/taskbar-mini.png)

캐릭터 스타일 (부드러운 고양이 / 도트 고양이 / 없음, 우클릭 메뉴에서 선택):

![characters](docs/characters.png)

도트 고양이 상태:

![cats](docs/cats.png)

## 특징

- **Claude 5h / 7d, GPT(Codex) 5h / 7d** 도넛 게이지 + 리셋까지 남은 시간
- Claude의 **모델 전용 주간 한도**(예: Fable only)는 작은 막대로 표시
- **알림**: 80% 돌파, 100% 소진, 한도 리셋 시 카드 배너 + **위젯과 같은 디자인의 알림 팝업**(오른쪽 아래, 고양이 포함) + 알림음. Windows 알림 센터 토스트는 옵션 (각각 끌 수 있음)
- **페이스 예측**: 이 속도면 리셋 전에 부족한지 여유인지 (옵션)
- **전체화면 앱 감지 시 자동 숨김** (같은 모니터에서만), 종료되면 복귀
- **클릭 통과 모드**: 다른 창이 활성일 땐 마우스가 위젯을 통과, 바탕화면이 활성이거나 Ctrl을 누른 동안만 조작
- **캐릭터 스타일 선택**: 부드러운 고양이(기본, 둥근 도형으로 그린 벡터) / 도트 고양이(RunCat풍 픽셀) / 없음(숫자만). 우클릭 → 캐릭터 스타일. 색은 브랜드에 맞춰 Claude는 코럴, GPT는 흑백 계열
- **작업표시줄 미니 모드**: 더블클릭하면 시계 왼쪽에 알약 모양(고양이 2마리 + 5h·7d %)으로 붙음. 좌우로 드래그해 자리를 정하면 기억. 다시 더블클릭하면 카드로 복귀
- **자동 업데이트**: 하루 한 번 GitHub 최신 릴리즈를 확인하고, 새 버전이면 팝업 → 클릭 한 번으로 내려받아 교체·재시작 (우클릭 메뉴에서 끄거나 즉시 확인 가능)
- 투명도 조절, 항상 위 토글, Windows 시작 시 자동 실행
- **적응형 폴링**: 사용률이 오르는 중이면 60초마다("1분 갱신" 표시), 멈춰 있으면 3~5분마다, 조회 실패면 2배씩 물러남
- 조회 실패 시 마지막 값을 그대로 유지하되 10분 넘으면 "N분 전 값"으로 표시, 1시간 넘으면 회색 처리
- 조회는 토큰 파일만 읽는 `--source oauth`로 제한. 브라우저 쿠키를 뒤지거나 `claude` CLI를 대신 실행하지 않아 다른 프로그램(Claude 데스크톱 등)과 파일 충돌이 없음
- 부팅 자동 실행 시(`--boot`) 첫 조회를 2분 늦춰 다른 앱들이 먼저 자리 잡게 함
- 카드 본체는 값이 바뀔 때만 다시 그려 CPU 사용 거의 없음 (~0.2%)

## 동작 원리

인증과 API 호출은 직접 하지 않고 [Win-CodexBar](https://github.com/nesszer/Win-CodexBar)의 CLI를 주기적으로(1~5분, 적응형) 실행해 JSON만 읽습니다.

```
codexbar-cli.exe usage -p both --json
```

그래서 토큰 갱신, 비공식 API 변경 대응은 Win-CodexBar가 맡고, 이 위젯은 그리기만 합니다.
Win-CodexBar 트레이 앱은 켜 둘 필요 없고, 설치만 되어 있으면 됩니다.

> 참고: ChatGPT 웹 채팅과 Gemini 채팅 한도는 조회 API가 없어 표시할 수 없습니다.
> Claude는 claude.ai 채팅과 Claude Code가 한도를 공유하므로 이 수치가 곧 전체 사용량입니다.

## 설치

전제: Windows 10/11, 그리고 이 PC에서 **Claude Code**(쓴다면 **Codex CLI**도)에 로그인되어 있을 것.
위젯은 그 로그인 정보를 읽어 한도를 조회합니다.

### 원클릭: `install.bat` 더블클릭

저장소를 내려받아(ZIP 또는 `git clone`) 폴더 안의 **`install.bat`** 을 더블클릭하면 끝입니다. Claude Code나 Codex를 쓰지 않는 사람도 됩니다. claude.ai 채팅은 Claude Code와 한도를 공유하므로 **로그인만** 해 두면 채팅 사용량이 보입니다.

설치 스크립트가 하는 일:

1. Python이 없으면 winget으로 설치, Pillow 설치
2. Win-CodexBar가 없으면 winget으로 설치
3. Claude Code가 없으면 설치하고, 로그인이 없으면 **로그인 화면을 띄움** (브라우저에서 구독 계정으로 로그인 → 터미널에 `/exit`)
4. "GPT 사용량도 볼까요?" 질문 → Y면 Node.js(없을 때)·Codex CLI 설치 후 로그인(브라우저 한 번), N이면 위젯에서 GPT를 숨김
5. Win-CodexBar 설정을 자동으로 맞춤: Claude 토큰 읽기 허용, 표시할 제공자, 트레이 앱 자동 실행·플로팅 바 끔
6. 바탕화면 바로가기 생성, 자동 실행 여부 질문, 위젯 실행

사람이 하는 건 브라우저 로그인(Claude 1회, GPT를 보면 1회 더)과 Y/N 답 두 번뿐입니다.

### 수동 설치

1. **Python 3.11+** 설치 (python.org). 설치 화면에서 *Add python.exe to PATH* 체크. tkinter는 기본 포함.
2. **Pillow** 설치
   ```
   pip install pillow
   ```
3. **Win-CodexBar** 설치 후 한 번 실행해서 설정
   ```
   winget install Finesssee.Win-CodexBar
   ```
   트레이 아이콘 우클릭 → 설정 → Providers → Claude → *Allow reading Claude Code's credentials* 체크.
   이후 트레이 앱은 꺼도 됩니다 (CLI만 있으면 위젯이 동작).
4. 이 저장소를 내려받기 (`git clone` 또는 ZIP). 필요한 파일은 `usage_widget.py`, `toast.ps1`, `toggle_widget.bat`.
5. 실행
   ```
   pythonw usage_widget.py
   ```
   좌상단에 카드가 뜨면 성공. 첫 조회는 5~10초 걸립니다.
6. (선택) `toggle_widget.bat`의 바로가기를 바탕화면에 만들면 더블클릭으로 켜고 끌 수 있고,
   위젯 우클릭 → *Windows 시작 시 자동 실행*으로 부팅 시 자동으로 뜹니다.

### Win-CodexBar 설정 안내

위젯은 Win-CodexBar가 만든 명령줄 도구(`codexbar-cli.exe`)로 사용량을 읽습니다. **`install.bat`이 아래 설정을 자동으로 처리**하므로(설정 파일을 직접 써 넣음) 보통은 손댈 일이 없습니다. 자동 설정이 실패했거나 CodexBar 업데이트로 설정이 초기화됐을 때만 아래를 따라 하세요. 트레이 앱은 켜 둘 필요가 없습니다.

1. **실행**: 시작 메뉴에서 CodexBar 실행 → 작업표시줄 시계 옆 트레이 아이콘이 생김
2. **설정 열기**: 트레이 아이콘 우클릭 → *Settings*(설정)
3. **Claude 읽기 허용** (필수): 상단 탭 **제공업체(Providers)** → *Claude* 항목 → **"Allow reading Claude Code's credentials"** 체크
   - 이 옵션이 꺼져 있으면 Claude 자리가 "–"이고 "조회 지연"만 뜹니다
   - 위젯은 여기서 허용한 토큰 파일(`~/.claude/.credentials.json`)만 읽고, 브라우저 쿠키나 `claude` 명령은 쓰지 않습니다
4. **GPT(Codex)**: 별도 설정 없음. Codex CLI에 로그인되어 있으면 자동으로 읽힙니다. Codex를 안 쓰면 위젯 우클릭 → *GPT(Codex) 표시* 해제
5. **쓰지 않는 제공자 끄기** (선택): 같은 탭에서 Gemini, Copilot, Cursor 등 체크 해제. 위젯에는 영향 없고 CodexBar 앱 안의 안내 문구만 사라집니다
6. **트레이 앱 종료 및 자동 실행 해제** (권장): 설정을 마쳤으면 트레이 아이콘 우클릭 → *Quit*. 부팅 때 다시 켜지지 않게 하려면 터미널에서
   ```
   "%LOCALAPPDATA%\Programs\CodexBar\codexbar-cli.exe" autostart --disable
   ```
   트레이 앱과 위젯이 동시에 조회하면 Anthropic 조회 API가 잠시 차단될 수 있어서, 위젯만 쓰는 편이 안정적입니다

> CodexBar를 업데이트하면 설정이 초기화되는 경우가 있습니다. 갑자기 Claude가 "조회 지연"만 뜨면 3번을 다시 확인하세요.

### 문제 해결

숫자가 안 뜨면 먼저 **`doctor.bat`** 을 더블클릭하세요. Python·Pillow·Win-CodexBar·로그인 파일을 순서대로 점검하고, 위젯과 같은 방식으로 실제 조회를 해 본 뒤 막힌 곳과 해결 방법을 한글로 알려줍니다.

#### 처음 설치 시 오류 메시지별 해결

| 어디서 | 메시지 | 뜻 / 해결 |
|---|---|---|
| Win-CodexBar, doctor | `OAuth error: Reading Claude Code's credentials is off. Enable "Allow reading Claude Code's credentials"…` | Claude 토큰 읽기 허용이 꺼짐. 트레이 아이콘 우클릭 → Settings → 제공업체 → Claude → 체크 |
| Win-CodexBar, doctor | `OAuth access token has expired. Re-authenticate to continue.` (401) | Claude 토큰 만료. 터미널에서 `claude` 한 번 실행하면 갱신됨 |
| Win-CodexBar, doctor | `Claude OAuth usage endpoint is rate limited. Retrying…` | 조회가 너무 잦아 잠시 차단. 5~10분 뒤 자동 회복. 트레이 앱이 켜져 있으면 종료 (위젯과 중복 조회) |
| Win-CodexBar, doctor | `Claude usage failed from all configured sources. Web: No cookies…; OAuth: …; CLI: Parse error…` | 세 경로 모두 실패. 핵심은 가운데 OAuth 부분의 문구 → 위 두 줄 중 해당하는 것 적용. Web/CLI 부분은 무시 |
| Win-CodexBar | `Chromium App-Bound Encryption (ABE) detected: all N cookies failed to decrypt` | 앱이 브라우저 쿠키를 읽으려다 실패한 안내. 위젯은 쿠키를 쓰지 않으므로 무시 |
| Win-CodexBar | `Provider not installed: Not logged in to Gemini. Run 'gemini'…` | Gemini CLI 미설치 안내. 개인 계정용 Gemini CLI는 2026-06에 종료됐으므로 설치하지 말고 제공업체에서 Gemini 체크 해제 |
| Win-CodexBar, doctor | Codex `Not logged in` / `auth.json` 없음 | Codex CLI 미로그인. `codex login` 실행. Codex를 안 쓰면 위젯 우클릭 → *GPT(Codex) 표시* 해제 |
| Win-CodexBar (Codex 페이지) | 상단 `Authentication required`, `Codex account not found.`, 계정 옆 `Ambient · No usage data` | Codex CLI 로그인이 없거나 만료. 터미널에서 `codex login` → 이 화면의 *Refresh usage*. `codex` 명령이 없으면 `npm install -g @openai/codex` 먼저. 안 쓰면 왼쪽 목록에서 Codex 체크 해제 |
| 터미널 | `'claude'은(는) 내부 또는 외부 명령… 아닙니다` / `not in your PATH` | Claude Code는 깔렸는데 PATH 미등록. 아래 한 줄 실행 후 터미널 재시작:<br>`[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";$env:USERPROFILE\.local\bin", "User")` |
| 터미널 (claude 로그인) | 로그인 방식 선택 화면 | **"Claude account with subscription"** 선택. API 키 방식으로 로그인하면 한도 개념이 없어 위젯에 숫자가 안 뜸 |
| 위젯 | Claude 자리 `–`, "Claude 조회 지연 (값 없음)" | 위 Claude 항목 중 하나. `doctor.bat`으로 어느 것인지 확인 |
| 위젯 | 숫자는 있는데 "N분 전 값" (주황) | 10분 넘게 조회 실패 중. 대개 rate limit → 기다리면 회복. 1시간 넘으면 회색으로 바뀜 |
| install.bat | `Python not found - installing via winget` 후 실패 | winget이 없는 PC. python.org에서 직접 설치 (Add to PATH 체크) 후 install.bat 재실행 |
| install.bat / 바로가기 | Windows "PC 보호" SmartScreen 경고 | 서명 없는 배치 파일이라 뜸. "추가 정보" → "실행" |

#### 증상별

| 증상 | 원인 / 해결 |
|---|---|
| "codexbar-cli.exe를 찾을 수 없습니다" | 3번 미설치 |
| Claude 자리가 "–", "조회 지연" | Win-CodexBar의 자격증명 허용이 안 됐거나(위 설정 안내 3번) Claude Code 미로그인. 터미널에서 `claude` 한 번 실행 |
| GPT 자리가 "–" | Codex CLI를 안 쓰면 정상. 우클릭 → *GPT(Codex) 표시* 체크 해제하면 Claude만 남고 카드가 절반 폭으로 줄어듦 |
| 글씨체가 다름 | Paperlogy, Pretendard 폰트가 없으면 맑은 고딕으로 대체. 같은 모양을 원하면 두 폰트 설치 |
| 위젯이 안 뜨는데 오류도 없음 | 폴더의 `widget.log` 확인 |

## 조작

| 동작 | 방법 |
|---|---|
| 이동 | 드래그 (위치 자동 저장) |
| 작업표시줄 미니 모드 전환 | 더블클릭 (또는 우클릭 메뉴) |
| 새로고침 / 종료 | 우상단 ↻ / ✕ |
| 옵션 | 우클릭 메뉴: Claude / GPT 표시 여부(한쪽만 남길 수 있음), 캐릭터 스타일, 투명도, 페이스 예측, 클릭 통과, 알림 소리, 항상 위, 전체화면 시 숨김, 시작 시 자동 실행 |
| 클릭 통과 중 조작 | 바탕화면을 클릭해 활성화하거나 Ctrl을 누른 채로 |

## 커스터마이즈

`usage_widget.py` 상단의 상수만 바꾸면 됩니다.

- 색: `CARD`, `C_OK`, `C_WARN`, `C_BAD`, `PROVIDERS`의 강조색·고양이 색
- 크기: `W`, `H`, `GAUGE`, `CAT_PX`
- 조회 주기: `REFRESH_SEC` (60초 이하로 내리면 Anthropic 조회 API가 일시 차단할 수 있음)
- 고양이 모양: `CAT_BODY`, `CAT_LEGS` 도트 배열
- 폰트: `font()`가 Paperlogy → Pretendard → 맑은 고딕 순으로 찾음

디버그: 환경변수 `WIDGET_SNAP=경로.png`를 주면 렌더 결과를 파일로 저장합니다. 오류는 `widget.log`에 남습니다.

## 한계

- Win-CodexBar CLI의 JSON 형식에 의존합니다. 형식이 바뀌면 "조회 지연"만 계속 뜹니다.
- Anthropic / OpenAI의 비공식 조회 엔드포인트가 바뀌면 Win-CodexBar 업데이트를 기다려야 합니다.
- Windows 전용 (Win32 API 사용).

## 라이선스

MIT
