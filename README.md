# AI Usage Widget 🐱

Claude Code / OpenAI Codex 사용량 한도(5시간·7일)를 화면에 **항상 떠 있는 작은 카드**로 보여주는 Windows 위젯입니다.
RunCat처럼 픽셀 고양이가 달리는데, 한도를 많이 쓸수록 빨리 달리고 100%가 되면 잠듭니다.

![preview](docs/preview.png)

## 특징

- **Claude 5h / 7d, GPT(Codex) 5h / 7d** 도넛 게이지 + 리셋까지 남은 시간
- Claude의 **모델 전용 주간 한도**(예: Fable only)는 작은 막대로 표시
- **알림**: 80% 돌파, 100% 소진, 한도 리셋 시 카드 배너 + **Windows 알림 센터 토스트** + 알림음 (각각 끌 수 있음)
- **페이스 예측**: 이 속도면 리셋 전에 부족한지 여유인지 (옵션)
- **전체화면 앱 감지 시 자동 숨김** (같은 모니터에서만), 종료되면 복귀
- **클릭 통과 모드**: 다른 창이 활성일 땐 마우스가 위젯을 통과, 바탕화면이 활성이거나 Ctrl을 누른 동안만 조작
- 투명도 조절, 항상 위 토글, Windows 시작 시 자동 실행
- 조회 실패 시 마지막 값을 그대로 유지 (1시간 넘게 실패해야 회색 처리), 자동 백오프
- 카드 본체는 값이 바뀔 때만 다시 그려 CPU 사용 거의 없음 (~0.2%)

## 동작 원리

인증과 API 호출은 직접 하지 않고 [Win-CodexBar](https://github.com/nesszer/Win-CodexBar)의 CLI를 3분마다 실행해 JSON만 읽습니다.

```
codexbar-cli.exe usage -p both --json
```

그래서 토큰 갱신, 비공식 API 변경 대응은 Win-CodexBar가 맡고, 이 위젯은 그리기만 합니다.
Win-CodexBar 트레이 앱은 켜 둘 필요 없고, 설치만 되어 있으면 됩니다.

> 참고: ChatGPT 웹 채팅과 Gemini 채팅 한도는 조회 API가 없어 표시할 수 없습니다.
> Claude는 claude.ai 채팅과 Claude Code가 한도를 공유하므로 이 수치가 곧 전체 사용량입니다.

## 설치

1. **Python 3.11+** 와 **Pillow**
   ```
   pip install pillow
   ```
2. **Win-CodexBar** 설치 후 한 번 실행해서 설정
   ```
   winget install Finesssee.Win-CodexBar
   ```
   설정 → Providers → Claude → *Allow reading Claude Code's credentials* 체크.
   Claude Code와 Codex CLI에 로그인되어 있어야 합니다.
3. 이 저장소를 내려받고 실행
   ```
   pythonw usage_widget.py
   ```

`toggle_widget.bat`을 바탕화면 바로가기로 만들어 두면 더블클릭 한 번으로 켜고 끌 수 있습니다.

## 조작

| 동작 | 방법 |
|---|---|
| 이동 | 드래그 (위치 자동 저장) |
| 새로고침 / 종료 | 우상단 ↻ / ✕ |
| 옵션 | 우클릭 메뉴: 투명도, 페이스 예측, 클릭 통과, 알림 소리, 항상 위, 전체화면 시 숨김, 시작 시 자동 실행 |
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
