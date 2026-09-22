# OSS Scout

GitHub에서 **상업적 재사용이 가능한(MIT / Apache-2.0 / BSD / ISC) 오픈소스**를 매주 자동으로 발굴하고,
라이선스·의존성을 감사한 뒤 **수익화 점수(0~100)** 를 매겨 리포트하는 파이썬 파이프라인입니다.

- 실행: GitHub Actions, 매주 월요일 09:00 KST (`workflow_dispatch` 수동 실행 가능)
- 출력: `reports/YYYY-Www.md` 커밋 · Notion DB upsert · Gmail 주간 요약 메일
- 한국 시장 관점(한국어 미지원 · 국내 결제/소셜 로그인 부재 = 기회)을 점수에 반영
- 자동 포크·배포는 하지 않습니다. **최종 판단은 사람이 합니다.**

> ⚠️ **법적 고지** — 이 도구의 판정은 규칙 기반 자동 판정이며 법률 자문이 아닙니다.
> 판매·호스팅 전에 대상 프로젝트의 LICENSE · NOTICE · 상표(브랜드) 정책과 의존성 라이선스를 직접 확인하세요.

---

## 5분 셋업 (GitHub Actions)

1. 이 리포를 **fork** (또는 새 리포에 push)
2. `Settings → Secrets and variables → Actions` 에 등록

   | Secret | 필수 | 설명 |
   |---|---|---|
   | `GH_PAT` | 권장 | classic PAT (`public_repo`). 없으면 기본 `GITHUB_TOKEN` 사용 (core 1,000 req/h → 첫 실행이 느림) |
   | `NOTION_TOKEN` | 선택 | Notion internal integration 토큰 |
   | `NOTION_DATABASE_ID` **또는** `NOTION_PARENT_PAGE_ID` | 선택 | 기존 DB id, 또는 DB 를 자동 생성할 부모 페이지 id (integration 을 해당 페이지에 연결해야 함) |
   | `NCP_APIGW_KEY_ID` / `NCP_APIGW_KEY` | 선택 | **NAVER API HUB**(Naver Cloud Platform) 검색 API 키. 시장 규모 점수의 "한국 인지도" 에 쓰임. 없으면 중립 처리. 개발자센터(developers.naver.com) 검색 API 는 2026-07-31 신규 발급 종료, 2027-06-30 서비스 종료 → 기존 키만 `NAVER_CLIENT_ID/SECRET` 으로 |
   | `SMTP_USER` | 선택 | Gmail 주소 |
   | `SMTP_APP_PASSWORD` | 선택 | Google 계정 → 보안 → **앱 비밀번호** (2단계 인증 필요) |
   | `MAIL_TO` | 선택 | 수신 주소 (쉼표 구분 가능) |

   Notion·메일 시크릿이 없으면 해당 sink 는 **경고 후 skip** 됩니다 (실패하지 않음).
3. `Actions → OSS Scout weekly → Run workflow` 를 1회 실행 (`dry_run` 체크 시 커밋·sink 없이 리포트만 생성).
   이후 매주 월요일 자동 실행되어 `data/state.json` 과 `reports/` 가 커밋됩니다.

## 로컬 실행

```powershell
pip install -r requirements.txt
```

```powershell
Copy-Item .env.example .env
```

`.env` 에 `GITHUB_TOKEN` 만 채워도 dry-run 은 동작합니다. 비워두면 `gh auth login` 된 GitHub CLI 의 토큰(`gh auth token`)을 자동으로 씁니다.

```powershell
python -m scout.main run --dry-run --limit 30
```

```powershell
python -m scout.main audit n8n-io/n8n
```

```powershell
python -m scout.main score umami-software/umami
```

```powershell
python -m pytest -q
```

`uv` 사용 시 `uv pip install -r requirements.txt` 후 동일.

### CLI

| 명령 | 설명 |
|---|---|
| `run [--dry-run] [--limit N] [--no-notion] [--no-mail]` | 수집 → 감사 → 점수 → 리포트 → sink. `--dry-run` 은 `reports/` 만 쓰고 state·Notion·메일을 건너뜀 |
| `audit owner/repo` | 단일 리포 감사 결과 JSON |
| `score owner/repo` | 단일 리포 점수 분해 JSON |

## 파이프라인

```
discover ──▶ audit ──▶ score ──▶ report.md ──▶ state.json
 (Search API)  (LICENSE·README·deps.dev·ee/·i18n)        ├─▶ Notion DB upsert
                                                         └─▶ Gmail 요약
```

1. **discover** — `config.yaml` 의 쿼리를 `sort=stars` / `sort=updated` 로 각 2페이지씩 돌려 합집합.
   archived · fork · 90일 초과 미갱신 · awesome/tutorial/boilerplate 계열 · README 없음 제외.
   후보마다 루트 파일 목록 · 최근 릴리즈 · 컨트리뷰터 수(Link 헤더 추정) 수집.
2. **audit**
   - 루트 라이선스: `spdx_id` 가 허용 목록이면 ok, `NOASSERTION` 이면 LICENSE 원문 패턴 판정, copyleft/BSL/SSPL/Elastic/Sustainable Use 는 **제외**
   - 추가 조건 문구: LICENSE 원문에서 `multi-tenant`, `may not be used to provide`, `Additional Conditions` 등 탐지 → `restricted_terms` (점수 0).
     README 에서만 발견된 `multi-tenant` / `enterprise edition` 은 기능 설명일 수 있어 **`readme_terms` 소프트 플래그**로만 기록
   - `ee/ enterprise/ premium/ pro/ packages/ee apps/ee` 및 `LICENSE-EE` 류 파일 → `ee_dir` (-5), 그 안의 LICENSE 첫 200자 저장
   - 직접 의존성(package.json / pyproject / requirements / go.mod / Cargo.toml 중 첫 매니페스트, 상위 60개) → [deps.dev](https://deps.dev) 로 라이선스 조회. AGPL/GPL/SSPL/BUSL 단독 라이선스면 `copyleft_deps` (점수 0). `X OR MIT` 같은 듀얼은 통과
   - 상표: README 의 `trademark` / ™ / ® / `brand guidelines` → 정보성 플래그 (리브랜딩 알림)
   - `known_traps` 목록은 무조건 제외
3. **score** — 아래 표. 가중치는 `config.yaml → scoring.weights` (합 100 강제).
4. **demand** — 점수 상위 60개 리포의 이슈·PR 에서 `korean · 한국어 · kakao · naver · toss` 등을 검색해
   **한국 수요 신호**를 셉니다. 이슈 = 누군가 요청함(수요), PR = 누군가 이미 시도함. 점수에는 넣지 않고
   리포트 "한국 수요 신호 Top 10" 섹션 · 테이블 `신호` 열(`2i/1p`) · Notion `KR Signals` 로만 노출합니다.
   반자동 영업의 리드 소스입니다. 공개 이슈에 답글을 다는 것은 스팸 규제와 무관합니다.
   `python -m scout.main demand owner/repo` 로 단일 조회. `demand.enabled: false` 또는 `--no-demand` 로 끔.
5. **report** — 요약 · Top 15 · 신규 진입 · 급상승 · 한국 수요 신호 · 제외 목록 · 상세 카드(점수 분해·다음 액션).
6. **sinks** — Notion(`Status` 는 덮어쓰지 않음, `Rejected` 는 다음 주 Top 15 에서 제외) · Gmail.

### 점수 (기본 가중치)

| 항목 | 최대 | 산식 |
|---|---:|---|
| 라이선스 청결도 | 20 | ok 20 · unknown 8 · `restricted_terms`/`copyleft_deps` 0 · `ee_dir` −5 |
| 활성도 | 15 | push ≤14일 10 + 90일 내 릴리즈 5 |
| 인기·모멘텀 | 10 | log10(stars) 정규화 8 + 주간 star 증가율 7 (히스토리 없는 첫 주는 stars 만으로 환산) |
| 커뮤니티 건강 | 10 | 컨트리뷰터 ≥20 5 + open_issues/stars 비율 낮을수록 5 |
| 배포 용이성 | 15 | Dockerfile 5 + compose 5 + helm/k8s 또는 .env.example 3 + Go/Rust 단일 바이너리 2 |
| 카테고리 시장성 | 10 | analytics/crm/commerce/cms/booking/invoice/notification/monitoring/llm-workflow/internal-tools 15 · devtool/lib 5 · 기타 8 (10점으로 환산) |
| **시장 규모** | 10 | **구매자 폭** 0~6: 개인·크리에이터용(newsletter/blog/homelab…) 1 · 소비자 2 · 개발도구 3(pip/npm 패키지인데 Dockerfile·compose·UI 없으면 여기) · 모든 사업체 5 · 기업 인프라(observability/database/security…) 6. **네이버 언급 수**는 수집해 `KR Mentions` 로 보여주지만 가중치 0 (2026-W39 측정: 일반 단어 이름이 1~3만 건으로 부풀고 ClickHouse 150 · uptime-kuma 16 으로 과소. 검색어 보정 뒤 `awareness_points` 로 켬) |
| 한국 기회 | 10 | ko 로케일 없음 +4 · stripe 만 있고 toss/kakao 없음 +3 · 카카오/네이버 로그인 없음 +3 (README 에 로그인/OAuth 언급 또는 SaaS 계열 카테고리일 때만) |

보정: copyleft/제한 라이선스 · known_traps → **0점 + excluded**. 미확인 항목(license/contributors/releases/deps/korea) 3개 이상 → `confidence: low`.

추천 모델 태그: compose + SaaS 계열 → `managed-hosting` · cms/commerce/internal-tools → `si-onprem` · 한국 기회 ≥7 → `korean-localization` · devtool → `template-sale` · 루트에 `plugins/` `extensions/` 류 폴더 + stars ≥ 8k → `plugin-sale`(플러그인 마켓에 팔 수 있는 플랫폼).

검색은 두 층입니다. 제품 층(`stars 100..20000`, 직접 포크·호스팅 대상)과 플랫폼 층(`stars 20000..100000`, 플러그인·한국 결제 연동을 팔 대상). 플랫폼 층은 `plugin-sale` 태그와 함께 읽으세요. 생태계가 작은 플랫폼의 플러그인은 안 팔립니다(Paymenter 토스 플러그인: 6개월 구매 0 실측).

## 설정 위치 (`config.yaml`)

| 무엇을 바꾸나 | 키 |
|---|---|
| 검색 쿼리 · 정렬 · 페이지 수 | `discovery.queries`, `sorts`, `pages_per_query` |
| 주당 감사 상한 | `discovery.max_candidates` (기본 200, CLI `--limit` 우선) |
| 제외 토픽 / 이름 패턴 | `discovery.exclude_topics`, `exclude_name_patterns` |
| 허용·copyleft 라이선스, 제한 문구 | `audit.ok_licenses`, `copyleft_patterns`, `restricted_term_patterns` |
| 함정 목록 | `known_traps` |
| 가중치 · 세부 점수 | `scoring.weights`, `scoring.<항목>` |
| 카테고리 키워드/가중치 | `scoring.category.keywords`, `weights` |
| i18n 폴더 후보 · 한국어 마커 | `scoring.korea.i18n_dirs`, `korean_locale_markers` |
| 리포트 크기 | `report.top_n`, `mail_top_n`, `rising_n` |

## Notion DB 스키마

`Name`(title, owner/repo) · `URL` · `Score` · `License` · `Stars` · `Stars Δ7d` · `Category` · `Model`(multi) ·
`KR Opportunity` · `Flags`(multi: ee_dir, trademark, restricted_terms, copyleft_deps, unknown, readme_terms) ·
`Status`(New/Reviewing/Forked/Selling/Rejected — 사람이 바꾸며 도구는 덮어쓰지 않음) · `Last Seen` · `First Seen` · `Notes`.

`NOTION_PARENT_PAGE_ID` 만 주면 첫 실행에 DB 를 만들고 로그에 id 를 출력합니다. 이후 `NOTION_DATABASE_ID` 로 고정하세요.

## 한계 (알고 쓰기)

- 매니페스트는 **루트**만 봅니다. 모노레포(`src/backend/pyproject.toml` 등)는 `deps: 매니페스트 없음` 으로 나오며 confidence 에 반영됩니다.
- deps.dev 에 없는 패키지(사내 패키지, 일부 Go 모듈)는 `unknown_deps` 로 셉니다.
- 라이선스 원문 판정은 정규식입니다. `unknown` 은 감점일 뿐 제외가 아니므로 반드시 원문을 읽으세요.
- GitHub Search 는 결과 1,000개 상한·30 req/min 제한이 있어 쿼리당 최대 200개만 봅니다.

## 개발

```
scout/
  config.py        config.yaml + .env 로드 (pydantic 검증, 가중치 합 100 체크)
  github_client.py REST 래퍼: rate-limit 대기, 검색 30/min 스로틀, ETag 캐시(data/etag_cache.json), deps.dev
  discover.py      검색 → 사전 필터 → 보강
  audit.py         라이선스·제한 문구·ee·의존성·상표·i18n 신호
  score.py         점수 분해 · 모델 태그 · 다음 액션
  report.py        Markdown
  state.py         data/state.json (주차별 stars/score 히스토리, first/last seen, Notion status 미러)
  sinks/notion.py  Notion API 2025-09-03 (data_sources)
  sinks/mail.py    Gmail SMTP STARTTLS
  main.py          CLI
tests/             pytest + respx (외부 호출 전부 모킹)
```
