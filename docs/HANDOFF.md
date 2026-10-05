# HANDOFF — oss-scout

다음 세션이 이 창을 이어받을 때 읽는 문서. 갱신 2026-10-05.

## 이 창의 역할
- 주제 발굴 허브. 제품 작업은 별도 창(스핀아웃은 인수 프롬프트 파일로 넘긴다).
- 2026-10-03 부터 **D6 신사업 TF 의 github 스카우터 담당** — 지시는 MLPC CEO 세션에서 온다.
  보고: wiki(mlpc-hq) `hq/status/D6.md` 맨 아래 `## 스카우터(갱신 날짜)` 절 + `hq/orders/YYYY-MM.md` 의 해당 행, 그 파일들만 커밋·push.
  경로는 단말마다 다르다 — 노트북 `C:/Users/quite/wiki`, IM-Desktop `D:\dev\mlpc-hq`.
  CEO 세션은 10/4 18:50 부터 **IM-Desktop** 의 'MLPC CEO 마스터 에이전트'(local_ef1c9bf5) — 같은 기기라 SendMessage 가 바로 닿는다.
  (10/4 낮의 "데스크톱에서 CEO 가 안 보인다" 는 CEO 가 노트북에 있던 때 얘기다.)
  닉에게 직접 묻지 않는다 — 아래 운영 규칙대로 CEO 경유.
- 운영 규칙(10/3 닉 지시, CEO 경유):
  - 결정 질문은 CEO 에게 보낸다 — 권장안 1개 + 한 줄 근거. CEO 가 결정·회신한다.
    닉 몫은 결제·계약 · 법무 판단 · 실명·본업 노출 · 계정·키 입력 · 시스템 설정 · 권한 막힘뿐이고 그것도 CEO 를 통해 모아서 묻는다.
  - 하위 에이전트는 필요하면 직접 쓴다(병렬 조사·읽기 전용 검수·정해진 목록 실행). 판단·설계·최종 검증은 메인,
    목록 실행·검수는 Sonnet, Haiku 는 파일·Notion 쓰기 금지. 완성된 작업 목록을 주고 결과는 전수 확인.
    커밋·push·외부 공개는 메인만. 새 창은 만들지 않는다(꼭 필요하면 CEO 에 먼저).
  - 겸직: MLPC 사업 계획 v2(10/3) — 범위 제한 없음. 단 실제 결제 개시는 세무 정상화 뒤.
  - **보고(10/3 닉 지시, 모든 지시에 적용)**: 일이 끝나거나 막히면 즉시 CEO 세션('MLPC CEO 마스터 에이전트')에
    SendMessage 로 `CEO-n 완료|막힘 · 커밋 <해시> · 다음 제안 <한 줄>`. '답신 불필요' 는 이 규칙으로 대체됐다.

## 상태
- 주간 실행: GitHub Actions, **월 08:17 KST**(9/30 정각에서 이동 — 정각은 4시간+ 밀렸다). 다음 10/5.
- 점수표 9/30 개편(`d342b84`, `1aded9c`): license 20→10(+10 market) · 미확인 ko 로케일 절반 · `llm` 단독 키워드 제거 ·
  devtool 은 enterprise 불가 · 개인 주식·퀀트 = narrow · 9router·WindsurfAPI known_traps · gpt-load `provider_tos` 플래그.
  **10/5 결과를 보기 전까지 점수표 동결.**
- 10/1 사람 검토: 상위 12개 중 스핀아웃 후보 없음. Notion `Rejected` — bagisto · hyperdx · TaxHacker · kaneo
  (사유는 Notion「나는 어떤 사람인가」업데이트 로그 10/1 — Notes 열은 매주 덮어써진다).
- CEO-10: `docs/candidate-lightrag.md` — 셋 중 LightRAG, 4주 실험(결제 없음). CEO-16 으로 1주차만 착수.
- **CEO-16 완료(2026-10-04, IM-Desktop)**: `experiments/lightrag-w1/results.md` — **못 넘음.** naive 22/30(73%) · mix 1/30(3%) · hybrid 1/30 · 무검색 1/30, mix − naive = **−70%p**.
  색인은 이 기기에서 처음부터 다시 만들었다(노트북 3/7 은 폐기). 조건·통계는 `index_stats.md`(results.md 뒤에 자동으로 붙는다).
  ⚠️ 핵심 발견: 사전 등록 예산 5,000 토큰에서 **mix 의 최종 컨텍스트에 텍스트 청크가 0개**(그래프 컨텍스트가 예산을 다 씀) → mix 답 = hybrid 답 30/30 동일.
  즉 결과는 "8B·예산 5,000 조건에서 LightRAG 기본 모드는 그래프 전용으로 퇴화한다" 로 읽어야 한다. 예산을 늘린 재실험은 사전 등록 밖 — CEO 결정 사항.
  채점: Sonnet 블라인드(`grading/grades_sonnet.jsonl`) vs 메인 독립(`grades_main.jsonl`) 120건 대조, 불일치 2건, 최종은 메인(`grades.jsonl`).
- **CEO-16·CEO-77 모두 CEO 확인됨(10/4 저녁, 닉 전달) → LightRAG 종결, 계획대로 복귀.** 다음 행동은 아래 '다음 할 일' 1번(10/5 08:17 주간 리포트 확인).
- **CEO-77 사후 추가 1회(2026-10-04, 사전 등록 밖) — 결론 같음, LightRAG 접음.** mix 에 청크가 들어가는 조건(개체·관계 상한 600/600, 예산 5,000·num_ctx 8,192 유지)으로 mix 만 재질의:
  **mix 23/30 vs naive 22/30 = +3.3%p**(Sonnet 집계 +1.7%p) — 기준 +10%p 미달. 즉 청크를 넣어 주면 mix 는 naive 와 같은 수준이 되지만 그래프가 더해 주는 것은 없다.
  CEO 지시의 '예산 12,000' 은 num_ctx 16,384 가 8GB VRAM 에서 80~89% GPU 로 떨어져(q8_0 KV+FA 로도) GPU 조건과 양립하지 않아 쓰지 못했다 — results.md '사후 추가' 절에 조건·근거.
  스크립트: `query_post.py`(env 로 설정 덮어쓰기) · `blind_post.py` · `score_post.py`(results.md 에 절 추가). 교훈 2개: Ollama 서버를 죽일 때 `llama-server` 고아 프로세스가 VRAM 을 잡고 남는다(같이 죽일 것) · 서버 env(FA·KV 타입)는 앱 재시작으로만 바뀐다.
  **이 기기(IM-Desktop) 실행법**: `night.ps1 -Now -MinFree 5.0` 을 `MLPC_OWNER='D6 스카우터 desktop'` · `MLPC_OLLAMA_PRIVATE=1` · `MLPC_MAX_LLAMA_GB=16` 환경변수와 함께 띄운다
  (한글 인자를 powershell.exe 명령줄로 넘기면 깨져 `-Deadline` 에 들어간다 — env 로만). Ollama 0.35 앱은 모델 경로를 **앱 설정 DB**(`%LOCALAPPDATA%\Ollama\db.sqlite` settings.models)에서 읽고 사용자 env `OLLAMA_MODELS` 는 무시한다 — 10/4 에 D:\ollama\models 로 고쳤다.
  llama-server 호스트 RAM 은 qwen3+bge-m3 러너 합으로 8GB 까지 올라간다(mmap 꺼짐) — 노트북용 3GB 상한은 이 기기에 맞지 않는다.

- **CEO-96(10/5 00:30, IM-Desktop) — W41 사람 검토 `docs/reviews/2026-W41.md`.** 08:17 공식 실행 전에 로컬 dry-run 스냅샷으로 했다.
  결론: 스핀아웃 후보 0, 관찰 2(dittofeed — 카카오 알림톡·국내 SMS 채널 공백 / emdash — 플러그인 장터 각도), 새 상위권 5개는 기각.
  gpt-load 는 개편 뒤 73점(devtool)이라 상위 15 밖이고, `provider_tos` 는 감사 결과에 붙는다.
  **스냅샷 방법**(다음에도 쓸 수 있다): 레포를 스크래치 폴더로 복사한 뒤 `scout.main.iso_week` 만 `"<다음 주>"` 로 바꿔 `run --dry-run --no-notion --no-mail`, `.venv` 파이썬으로 돌린다.
  ⚠️ 일요일 밤에 레포 안에서 그냥 dry-run 하면 **이번 주 리포트 파일(`reports/<이번 주>.md`)을 덮어쓴다**(주 라벨 = 실행 시각). `reports/`·`data/` 는 Actions 가 08:17 에 커밋하니 사람이 커밋하지 않는다 — 검토는 `docs/reviews/`.
  로컬엔 NAVER 키가 없어 시장 점수가 '미조회'(중립)이고 Notion Rejected 필터도 안 걸린다. 콜드 캐시라 API 5,999회에 18분 걸렸다.

- **CEO-119(10/5 09:40 main 병합 `789f342`, 브랜치·worktree 정리됨)** — 렌즈 = 소상공인·개인 대상 셀프서브 구독형(국내 결제·카카오 로그인·알림톡 공백).
  `selfserve` 20 신설, 구매자 폭 business 최고·enterprise 2·devtool 1, 알림톡 공백 +2. 회귀 `docs/reviews/ceo-119-regression.md`. W42(**10/12 월** 08:17)부터 적용.
  CEO 결정(10/5): TaxHacker·kaneo 는 Rejected 유지, **W42 리포트에서 새 렌즈로 재판정**해 '관찰' 로 올릴지 정한다 · Paymenter·Ackee 기각 유지(시장 협소는 사람 판단) · **10/8 수동 실행 금지**(W41 라벨로 기록돼 공식 W41 을 덮는다).

## 다음 할 일 (10/5 이후)
1. ~~10/5 공식 리포트 확인~~ **완료(10/5 09:33)** — 08:17 예약이 09:07 까지 안 돌아 CEO 지시로 수동 정식 실행(run 37246244304 → `f79b1a2`). 점수는 스냅샷과 같고, Notion `provider_tos` 옵션 자동 생성·gpt-load 행 확인. ⚠️ Notion Rejected 필터가 대소문자 섞인 이름(vas3k/TaxHacker)을 놓치던 버그를 찾아 고쳤다(337e6be). 대조는 `docs/reviews/2026-W41.md` 끝 절. 늦게 도는 W41 예약 실행이 있으면 새 점수표로 W41 을 덮으니 취소한다(10/5 백그라운드 감시를 걸어 둠).
1-1. 관찰 2건 다음 주 확인: dittofeed 에 알림톡·국내 SMS 연동 요청이 실제로 있는지와 어떤 기능이 비공개 EE 로 빠졌는지, emdash 장터(`packages/marketplace`)에서 유료 플러그인을 팔 수 있는지.
1-2. 점수표 동결이 풀리면: 감사가 놓친 2건 — 오픈코어 EE 가 별도 이미지로만 있는 경우(compose 에 `-ee` 이미지), 모노레포 로케일 경로.
2. ~~가격 페이지 판독~~ **v1 완료(CEO-157, 10/5 — 표시만, 2주 관찰 뒤 점수 반영 여부 CEO 결정)** `docs/design/pricing-signal.md`. W42·W43 리포트에서 판정 정확도를 표로 확인할 것. 원래 메모: 지금의 "소상공인 단가" 근사(구매자 폭+카테고리)를 실제 가격표 읽기로 바꾼다. "유료 상품이 실제로 보이는가" 신호 설계 — 원본 HTML 이 아니라 보이는 텍스트 기준(`/mo`·`$` 오탐 실측).
3. 검색 렌즈를 셀프서브 구독형(소상공인·개인 대상, 국내 결제·카카오 로그인 공백)으로 좁힐지 — CEO 결정(권장안 붙여 요청).
4. 보류: 한국 수요 신호 가산(수집이 채점 뒤 상위 50) · `database` 토픽 enterprise 판정.

## 함정
- Bash 툴 heredoc 에서 `\\` 가 망가진다 — 정규식·YAML 은 Write/Edit 로.
- Windows 에서 파이썬 `open(...,'w')` 는 CRLF 로 쓴다 — git 이 정규화하지만 경고가 뜬다.
- `gh` 는 `GITHUB_TOKEN=` 를 비우고 호출(전역 규칙 3).
