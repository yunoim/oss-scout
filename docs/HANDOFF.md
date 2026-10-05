# HANDOFF — oss-scout

다음 세션이 이 창을 이어받을 때 읽는 문서. **완전 갱신 2026-10-05 10:10**(창 보관 전, CEO 지시). 다음 창은 **10/12(월) 아침**에 연다.

## 이 창의 역할
- 주제 발굴 허브 = **D6 신사업 TF 의 github 스카우터**. 지시는 CEO 세션에서 온다. 제품 작업은 별도 창(스핀아웃은 인수 프롬프트 파일로).
- **보고**: 일이 끝나거나 막히면 즉시 CEO 세션 **'MLPC CEO 마스터 에이전트'**(IM-Desktop, 10/5 02:10 부터 2대 창 local_11975e65 — 이름으로 보내면 닿는다)에
  SendMessage 로 `CEO-n 완료|막힘 · 커밋 <해시> · 다음 제안 <한 줄>`. 같은 내용을 mlpc-hq(`D:\dev\mlpc-hq`, 브랜치 **master**)의
  `hq/status/D6.md` 맨 아래 `## 스카우터(날짜)` 절 + `hq/orders/YYYY-MM.md` 해당 행에 적고 그 파일들만 커밋·push.
- **컨텍스트 교체 규칙**(hq/README.md): 70% 넘으면 이 문서를 완전 갱신 → CEO 에 `[교체 필요]`.
- 운영 규칙(10/3 닉, CEO 경유): 결정 질문은 CEO 에게 권장안 1개 + 한 줄 근거. 닉에게 직접 묻지 않는다.
  하위 에이전트는 1개까지(판단·검증은 메인, 목록 실행·검수는 Sonnet, Haiku 쓰기 금지). 커밋·push·외부 공개는 메인만.
- 시각은 PowerShell `Get-Date` 로 확인한다(10/4 밤 CEO 가 PM 메시지 시각을 믿다가 틀렸다).

## 현재 상태 (10/5 10:10)
| 무엇 | 상태 | 어디 |
|---|---|---|
| 주간 실행 | GitHub Actions 월 08:17 KST(예약은 몇 시간씩 밀린다 — W40 은 13:14, W41 은 09:07 까지 안 돌아 수동 실행) | `.github/workflows/scout.yml` |
| W41(10/5) | 공식 = 수동 정식 실행 `f79b1a2`. 사람 검토: **스핀아웃 후보 0 · 관찰 2(dittofeed · emdash)** | `reports/2026-W41.md` · `docs/reviews/2026-W41.md`(끝에 공식 대조 절) |
| 점수표 | **CEO-119 셀프서브 구독형 렌즈** main `789f342` — `selfserve` 20 신설, 구매자 폭 business 6 최고 · enterprise 2 · devtool 1, 알림톡 공백 +2. **W42 부터 적용** | `config.yaml` · `scout/score.py` · 회귀 `docs/reviews/ceo-119-regression.md` |
| Notion Rejected 필터 | 대소문자 섞인 이름을 놓치던 버그 수정 `337e6be`(W41 에는 Rejected TaxHacker 가 9위로 실렸다) | `scout/sinks/notion.py` |
| 가격 판독 | **CEO-157 v1 main `b0bd1d4`·`8a6eb3b` — 표시만(점수 무관)**. 상위 30 의 homepage·가격 페이지 → `selfserve`(≤$50/월) · `pricey` · `sales` · `no_price` · `unknown`. 리포트 카드 '가격(표시만, 점수 무관)' 줄 · Notion `Notes` 끝 `| 가격: …`. `--no-pricing` 으로 끈다 | `scout/pricing.py` · 설계·실측 `docs/design/pricing-signal.md` |
| 가격 판독 네트워크 규칙(코드 상수, CEO 조건) | 식별 UA · 재시도 없음 · 레포당 페이지 2회 · robots.txt 존중(막히면 unknown) · 리다이렉트 홉마다 robots 재확인(최대 3) · 공개 주소만(사설·메타데이터 IP 차단, 연결 뒤 상대 IP 재확인) · 본문 2MB | `scout/pricing.py` 상단 |
| 테스트 | 86 통과(main). Actions 가 실행 전에 돌린다 — **빨간 테스트 = 그 주 리포트 없음** | `tests/` |
| 세션 cron·백그라운드 | **없음**(10/5 10:10 확인). W41 늦은 예약 실행 감시는 10/5 ~11:40 까지만 돌다 끝난다 — 그 뒤 W41 예약 실행이 돌면 새 점수표로 W41 을 덮으니, 10/12 창에서 `gh run list` 에 10/5 schedule 실행이 있는지 한 번 본다 | |
| LightRAG | **종결**(CEO-16 −70%p, CEO-77 사후 +3.3%p < +10%p). 기록만 남김 | `experiments/lightrag-w1/results.md` · `docs/candidate-lightrag.md` |

## 10/12(월) W42 — 할 일 순서
1. **실행 확인**: 09:00 쯤 `gh run list --repo yunoim/oss-scout --limit 3`(GITHUB_TOKEN·GH_TOKEN 비우고). 10/12 schedule 실행이 없으면 **CEO 에 묻고** `gh workflow run scout.yml` 로 정식 실행(W41 때 CEO 승인 선례).
   늦은 예약 실행이 뒤에 또 오면 같은 주 중복(메일 2통·state 재기록)이니 `gh run cancel`. **수동 실행은 그 주 월요일에만** — 다른 요일에 돌리면 주 라벨이 같아 그 주 리포트를 덮는다(10/8 수동 실행 금지가 이 이유).
2. `git pull` → `reports/2026-W42.md`. 새 렌즈 첫 주다 — 상위 15 가 기업·인프라에서 소상공인 쪽으로 옮겨 왔는지 한 줄로 본다.
3. **재판정 3건**(CEO 10/5 결정): TaxHacker(소상공인 회계, 가격 판독 €10/월) · kaneo(가격 판독 $3.33/월) · kanboard — 새 렌즈 점수·가격 줄을 보고 '관찰' 로 올릴지 권장안을 CEO 에 보낸다. Rejected 해제(Notion Status 변경)는 CEO 결정 뒤에만.
4. **관찰 2건 갱신**: dittofeed(알림톡·국내 SMS 연동 요청이 이슈·디스커션에 있는가, 어떤 기능이 비공개 EE 인가) · emdash(`packages/marketplace` 에서 유료 플러그인을 팔 수 있는가).
5. **가격 판독 정확도 표 1주차**: W42 상위 30 의 가격 줄을 사람이 실제 가격 페이지와 대조 → `docs/reviews/2026-W42-pricing.md` 에 레포 · 판정 · 실제 · 맞음/틀림/판독불가 표. 지표 = 판독 가능 비율, 판독된 것 중 정확도, `selfserve` 오탐 수.
6. 사람 검토 `docs/reviews/2026-W42.md`(W41 형식: 결론 한 줄 → 판정 표 → 기존 판정 유지 → 새 신호). D6.md·orders 갱신 → CEO 보고.

## 점수 반영 결정 절차 (가격 판독, W43 = 10/19 뒤)
- W42·W43 두 주의 정확도 표를 합쳐 CEO 에 권장안 1개로 보낸다. 내 기준안(사전 등록 — 결과 보기 전에 정해 둔다):
  **판독된 것 중 정확도 ≥ 85% 이고 `selfserve` 오탐 ≤ 1건/주** 이면 반영 권장 — `selfserve` 축 원점수에 `selfserve` +3 · `sales` −3(설계안 그대로, 원점수 상한 10 → 13).
  미달이면 표시 유지 + 틀린 유형(SPA·데모 가격·연간/좌석 단가 혼동 등)별 고칠 것 목록.
- 반영하면 Notion 에 `Pricing` select 속성을 새로 만드는 일도 같이 결정(`ensure_database` 가 빠진 속성을 추가하지만, `upsert` 는 행마다 예외 처리가 없어 한 번 실패하면 그 주 Notion 동기화 전체가 멈춘다 — dry-run 으로 먼저 확인).
- 점수표를 바꾸면 회귀표(`docs/reviews/ceo-119-regression.md` 형식)를 다시 만들고, **그 주 예약 실행이 끝난 뒤에** main 에 넣는다.

## 쌓인 메모 (결정 대기 · 보류)
- 감사가 놓친 것 2건(점수표 손볼 때): 오픈코어 EE 가 **별도 이미지로만** 있는 경우(dittofeed `docker-compose.ee.yaml` → 비공개 `packages/ee`) · 모노레포 로케일 경로(emdash 는 한국어가 병합됐는데 "ko 없음").
- 보류: 한국 수요 신호 가산(수집이 채점 뒤 상위 50) · `database` 토픽 enterprise 판정 · 국내 경쟁 서비스 가격 비교.
- 신규 진입 중 별 수만 개인 개발자 도구·스킬 모음(archify · humanizer)이 토픽 때문에 잡힌다 — 3주 연속이면 `exclude_topics` 후보.

## 실행법
- 테스트: `D:\dev\oss-scout\.venv\Scripts\python.exe -m pytest -q`(WindowsApps 파이썬엔 pydantic 이 없다 — 레포 `.venv` 를 쓴다).
- 단일 레포: `.venv\Scripts\python.exe -m scout.main score owner/repo` · `audit owner/repo` · `demand owner/repo`.
- **사전 스냅샷**(공식 실행 전에 보고 싶을 때): 레포를 스크래치 폴더로 복사 → `scout.main.iso_week` 만 `"<그 주>"` 로 바꾼 래퍼로 `run --dry-run --no-notion --no-mail`.
  ⚠️ 레포 안에서 그냥 dry-run 하면 **그 주 `reports/<주>.md` 를 덮는다**(주 라벨 = 실행 시각). `reports/`·`data/` 는 Actions 만 커밋한다 — 사람 검토는 `docs/reviews/`.
- 코드 변경: `git worktree add D:\work\oss-scout -b <브랜치>` → 테스트 → code-review → main. `D:\dev\oss-scout` 는 main 전용.
  (10/5 정리 때 `D:\work\oss-scout` 빈 폴더가 사용 중이라 남았다 — 다시 worktree 를 만들 때 이미 있다고 나오면 지우고 만든다.)
- 로컬엔 NAVER 키가 없다(인지도 가중치 0 이라 점수 차이 없음). GitHub 토큰은 `gh auth token` 자동 사용.

## 함정
- Bash 툴 heredoc 에서 `\\`·`\n` 이 망가진다 — 정규식·이스케이프가 든 코드는 Write/Edit 로.
- Windows 에서 파이썬 `open(...,'w')` 는 CRLF — git 이 정규화하지만 경고가 뜬다. mlpc-hq 의 status·orders 는 CRLF 파일이다(줄 끝을 건드리지 않는다).
- `gh` 는 `GITHUB_TOKEN=`·`GH_TOKEN=` 를 비우고 호출(전역 규칙 3). `gh api` 첫 인자에 선행 슬래시 금지.
- Notion 은 읽기만(쓰기는 Actions 의 sink 몫). Rejected 판단은 Notion Status 가 정본.
- LightRAG 실험 기록(이 기기 Ollama 설정 포함)은 `experiments/lightrag-w1/` 와 git 이력(`b2e6e98`·`eeeba36`)에 있다 — 다시 할 일 없음.
