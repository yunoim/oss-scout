# HANDOFF — oss-scout

다음 세션이 이 창을 이어받을 때 읽는 문서. 갱신 2026-10-03.

## 이 창의 역할
- 주제 발굴 허브. 제품 작업은 별도 창(스핀아웃은 인수 프롬프트 파일로 넘긴다).
- 2026-10-03 부터 **D6 신사업 TF 의 github 스카우터 담당** — 지시는 MLPC CEO 세션에서 온다.
  보고: `C:/Users/quite/wiki/hq/status/D6.md` 맨 아래 `## 스카우터(갱신 날짜)` 절, wiki 레포에 그 파일만 커밋·push.
  닉에게 직접 묻지 말고 D6.md 의 '닉 필요' 에 적는다.
- 운영 규칙(10/3 닉 지시, CEO 경유):
  - 결정 질문은 CEO 에게 보낸다 — 권장안 1개 + 한 줄 근거. CEO 가 결정·회신한다.
    닉 몫은 결제·계약 · 법무 판단 · 실명·본업 노출 · 계정·키 입력 · 시스템 설정 · 권한 막힘뿐이고 그것도 CEO 를 통해 모아서 묻는다.
  - 하위 에이전트는 필요하면 직접 쓴다(병렬 조사·읽기 전용 검수·정해진 목록 실행). 판단·설계·최종 검증은 메인,
    목록 실행·검수는 Sonnet, Haiku 는 파일·Notion 쓰기 금지. 완성된 작업 목록을 주고 결과는 전수 확인.
    커밋·push·외부 공개는 메인만. 새 창은 만들지 않는다(꼭 필요하면 CEO 에 먼저).
  - 겸직: MLPC 사업 계획 v2(10/3) — 범위 제한 없음. 단 실제 결제 개시는 세무 정상화 뒤.

## 상태
- 주간 실행: GitHub Actions, **월 08:17 KST**(9/30 정각에서 이동 — 정각은 4시간+ 밀렸다). 다음 10/5.
- 점수표 9/30 개편(`d342b84`, `1aded9c`): license 20→10(+10 market) · 미확인 ko 로케일 절반 · `llm` 단독 키워드 제거 ·
  devtool 은 enterprise 불가 · 개인 주식·퀀트 = narrow · 9router·WindsurfAPI known_traps · gpt-load `provider_tos` 플래그.
  **10/5 결과를 보기 전까지 점수표 동결.**
- 10/1 사람 검토: 상위 12개 중 스핀아웃 후보 없음. Notion `Rejected` — bagisto · hyperdx · TaxHacker · kaneo
  (사유는 Notion「나는 어떤 사람인가」업데이트 로그 10/1 — Notes 열은 매주 덮어써진다).
- CEO-10: `docs/candidate-lightrag.md` — 셋 중 LightRAG, 4주 실험(결제 없음). 착수 여부는 CEO 결정 대기.

## 다음 할 일 (10/5 이후)
1. 10/5 리포트 확인 — gpt-load 카드에 "공급사 약관 주의" 가 뜨는지, Notion Flags 에 `provider_tos` 옵션이 자동 생성되는지(실패하면 upsert 가 깨진 것).
2. "유료 상품이 실제로 보이는가" 신호 설계 — 원본 HTML 이 아니라 보이는 텍스트 기준(`/mo`·`$` 오탐 실측).
3. 검색 렌즈를 셀프서브 구독형(소상공인·개인 대상, 국내 결제·카카오 로그인 공백)으로 좁힐지 — 닉 결정.
4. 보류: 한국 수요 신호 가산(수집이 채점 뒤 상위 50) · `database` 토픽 enterprise 판정.

## 함정
- Bash 툴 heredoc 에서 `\\` 가 망가진다 — 정규식·YAML 은 Write/Edit 로.
- Windows 에서 파이썬 `open(...,'w')` 는 CRLF 로 쓴다 — git 이 정규화하지만 경고가 뜬다.
- `gh` 는 `GITHUB_TOKEN=` 를 비우고 호출(전역 규칙 3).
