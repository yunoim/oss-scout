# 설계안 — 가격 페이지 판독 (HANDOFF 2번 · CEO-119 후속)

갱신 2026-10-05 · 상태: **구현됨 v1(표시만) — CEO-157**

## 왜
CEO-119 셀프서브 렌즈는 '개인·소상공인이 낼 수 있는 단가' 를 **구매자 폭 + 카테고리로 근사**한다. 실제로 그 단가에 파는 사람이 있는지(= 셀프서브 구독 시장이 이미 검증됐는지)는 보지 않는다. 가격표를 직접 읽어 이 근사를 사실로 바꾼다.

## 실측 (10/5, 홈페이지 10개 · 보이는 텍스트 정규식 `통화 숫자 /mo|month|user|seat|yr`)
| 레포 | 홈페이지 | 가격 링크 | 홈에서 잡힌 가격 | 영업 문구 | 실제 |
|---|---|---|---|---|---|
| dittofeed | dittofeed.com | `/pricing` | $75/mo | contact sales | 클라우드 유료 + 영업 — 맞음 |
| talivia | talivia.com | `/#pricing` | $9.99/mo | — | 셀프서브 구독 — 맞음 |
| plausible(대조군) | plausible.io | `/#pricing` | $9 · $14 · $19 /mo | — | 셀프서브 구독 — 맞음 |
| TaxHacker | taxhacker.app | — | €10/mo | — | 셀프서브 구독 — 맞음 |
| kaneo | kaneo.app | `/pricing` | (홈엔 없음) | — | 가격 페이지 따로 — 2단계 필요 |
| **Paymenter** | paymenter.org | — | **$5/mo** | — | **오탐** — 제품이 만든 *가상 호스팅 상품* 예시 가격. Paymenter 자체는 무료 |
| emdash · Ackee | | — | — | — | 가격 없음(무료 오픈소스) — 맞음 |
| suitenumerique/docs · uptime-kuma | | — | — | — | **판독 불가** — JS 로 그리는 페이지(HTML 2KB 안팎) |

→ 스카우트 레포 9개(plausible 은 대조군이라 뺌) 중 **홈페이지만으로 맞은 것 5**(dittofeed · talivia · TaxHacker 는 가격, emdash · Ackee 는 가격 없음), **가격 페이지 2단계가 필요한 것 1**(kaneo), **오탐 1**(Paymenter: 상거래·호스팅 **제품의 데모 가격**), **판독 불가 2**(SPA). 오탐은 commerce 카테고리에서 구조적으로 나온다.

## 설계
**대상**: 점수 상위 N(=30, `pricing.max_repos`) 중 GitHub `homepage` 필드가 있는 레포만. 채점 뒤, 수요 신호(demand)와 같은 자리에서 돈다(외부 HTTP 라 상위만).

**수집** (레포당 최대 2회 GET, 각 10초, 리다이렉트 허용, 일반 UA, robots.txt 존중)
1. `homepage` 를 받는다. 가격 링크(`href` 에 `pric`) 가 있으면 그 페이지도 받는다 — **리다이렉트 뒤 최종 주소 기준, 같은 등록 도메인**일 때만(`docs.foo.com` → `foo.com/pricing` 은 따라감, `other.com` 은 안 따라감. dittofeed.com→www, DB-GPT 의 docs.dbgpt.cn 같은 경우 때문).
2. `<script>`·`<style>` 을 지운 **보이는 텍스트**만 본다(원본 HTML 의 `$`·`/mo` 오탐을 피한다 — HANDOFF 2번 원래 메모).

**판정** `pricing.tier`
| tier | 조건 |
|---|---|
| `selfserve` | 가격 문자열이 있고(`$|€|£|₩` + 숫자 + `/mo|month|user|seat`, `/yr|year` 는 12 로 나눠 월로) 최저가 ≤ `selfserve_max_usd`(=50/월) |
| `pricey` | 가격은 있는데 최저가 > 50 |
| `sales` | 가격 없음 + `contact sales|talk to sales|book a demo|request a quote` |
| `no_price` | 페이지는 읽혔는데 가격·영업 문구 둘 다 못 찾음(무료라는 뜻이 아니다 — `/plans`·`/cloud` 뒤에 숨은 가격도 여기 들어간다) |
| `unknown` | 홈페이지 없음 · 오류 · 보이는 텍스트 < 2KB(SPA) |

**오탐 방지**: **commerce** 카테고리는 **가격 링크 페이지에서 잡힌 가격만** 인정한다(홈의 가격은 제품이 만든 상점의 데모일 수 있다 — Paymenter). invoice 는 홈 가격을 인정한다(TaxHacker). 통화 환산은 고정 환율 표(설정값)로 대략만.

**점수 반영** (`selfserve` 축 안에서, 합 100 유지)
- `selfserve` +3: 남이 이미 소상공인 단가로 팔고 있다 = 시장 검증 · `sales` −3(영업 주도) · `no_price`/`unknown`/`pricey` 0
- 원점수 상한은 지금 10 → 13 으로 늘려 비율 환산(가중치 20 그대로). **가격 신호는 상위 30 에만 있으므로** 30위 밖과의 공정성 문제가 있다 — 그래서 가점·감점을 작게(±3/13 ≈ ±4.6점) 둔다.
- **v1 표시**: 리포트 카드 한 줄 + Notion 기존 `Notes` 텍스트 끝에 `가격: <tier> <최저가> <URL>` — **스키마 변경 없음**. (`ensure_database` 는 빠진 속성을 추가해 주지만, `upsert` 는 행마다 예외 처리가 없어 한 번 실패하면 그 주 Notion 동기화 전체가 멈춘다 — 새 속성은 점수 반영 단계에서)

## 테스트 10건 (네트워크 없이 — 보이는 텍스트·HTML 픽스처)
| # | 입력 | 기대 |
|---|---|---|
| 1 | talivia 홈 텍스트(`$9.99/mo`) | `selfserve`, 최저 9.99 |
| 2 | plausible 홈(`$9 /mo`·`$14`·`$19`, 공백 섞임) | `selfserve`, 최저 9 |
| 3 | TaxHacker 홈(`€10/mo`, **invoice** 카테고리, 가격 링크 없음) | `selfserve`, 환산 약 11 USD — invoice 는 홈 가격 인정 |
| 4 | dittofeed 가격 페이지(`$75/mo` + contact sales) | `pricey`(가격이 있으면 영업 문구보다 가격 우선) |
| 5 | 가격 없음 + `Book a demo` | `sales` |
| 6 | Paymenter 홈(`$5/mo`, commerce 카테고리, 가격 링크 없음) | `no_price` — commerce 는 홈 가격 무시 |
| 7 | commerce 인데 가격 링크 페이지에 `$29/mo` | `selfserve` |
| 8 | SPA 셸(HTML 2KB, `<div id="root">`) | `unknown` |
| 9 | 가격 링크 도메인: ⓐ `docs.foo.com` 홈 → `https://foo.com/pricing` ⓑ `https://other.com/pricing` | ⓐ 따라감 ⓑ 안 따라감(홈만으로 판정) |
| 10 | `<script>` 안에만 `"$12/mo"` 가 있고 보이는 텍스트엔 없음 | `no_price`(원본 HTML 오탐 방지) |

픽스처는 실제 페이지를 본뜬 **짧은 발췌**만 레포에 넣는다(긁은 페이지 통째로 넣지 않는다).

## 하지 않을 것 (이번 범위 밖)
- JS 렌더링(헤드리스 브라우저) — SPA 는 `unknown` 으로 둔다. 무거운 작업 슬롯을 쓰게 되고 Actions 시간도 는다
- 가격표의 플랜 구조(좌석·사용량) 정밀 파싱 · 연간/월간 할인 계산 · 실시간 환율
- 상위 30 밖 레포의 가격 수집
- 국내 경쟁 서비스 가격 비교(별건 — '국내 공백' 을 가격으로 재는 일)

## 위험
- 남의 사이트를 주 1회 30곳 GET — 부담은 작지만 robots·UA 를 지킨다. Actions IP 차단 시 `unknown` 으로 떨어질 뿐 실행은 실패하지 않게
- 가격 문구는 바뀐다 — 매주 다시 읽으므로 상태로 저장하지 않는다(리포트·Notion 에 그 주 값만)
- 회귀: 위 실측 10개를 픽스처(저장한 보이는 텍스트)로 테스트에 넣는다 — Paymenter 오탐이 commerce 규칙으로 막히는지가 핵심

## 승인 받을 것 (CEO)
1. 점수 반영 크기(±3 / 원점수 13) — 아니면 **v1 은 표시만, 점수 반영은 2주 관찰 뒤**(권장: 표시만 먼저. 상위 30 에만 있는 신호라 순위를 흔들기 전에 정확도부터 본다)
2. `selfserve_max_usd` = 50/월
3. 대상 상위 30

## 구현 결과 (CEO-157, 2026-10-05)
CEO 승인: ① v1 표시만(2주 관찰 뒤 점수 반영) ② 50달러/월 ③ 상위 30 + 조건: robots.txt 가 막으면 `unknown`, 식별 UA · 재시도 없음 · 레포당 페이지 요청 2회를 코드 상수로 고정.
- 구현: `scout/pricing.py` · 리포트 카드 '가격(표시만, 점수 무관)' 한 줄 · Notion `Notes` 끝 `| 가격: …` (스키마 변경 없음) · `--no-pricing` 로 끈다
- 코드 리뷰·보안 리뷰에서 더한 것: 리다이렉트를 직접 따라가며 **매 홉 robots.txt 확인**(최대 3홉) · **공개 주소만**(http/https, 포트 80/443, 사설·루프백·링크로컬·예약 IP 거부 — homepage 는 임의 레포 메타데이터이고 Actions 에서 돈다) · 본문 **2MB 에서 자름**
- 테스트 17건(설계 10 + 연간 환산 + 네트워크 정책 + 리다이렉트 robots 2 + 비공개 주소 + 크기 상한 + homepage 없음)

### 실측 9개 재판독 (10/5 실네트워크, 구현 코드)
| 레포 | 카테고리 | 홈페이지 | 판정 | 최저 $/월 | 근거 페이지 | 요청 | 설계 때 실측과 |
|---|---|---|---|---:|---|---:|---|
| dittofeed | notification | dittofeed.com | `pricey` | 75 | www.dittofeed.com/pricing | 2 | 같음(영업 문구보다 가격 우선) |
| talivia | analytics | talivia.com | `selfserve` | 9.99 | talivia.com | 2 | 같음 |
| TaxHacker | invoice | taxhacker.app | `selfserve` | 11 (€10) | taxhacker.app | 1 | 같음 |
| kaneo | internal-tools | kaneo.app | `selfserve` | 3.33 ($40/년) | kaneo.app/pricing | 2 | **2단계로 해결** |
| Paymenter | commerce | paymenter.org | `no_price` | — | — | 1 | **오탐 제거**(홈의 $5/mo 는 데모 상점) |
| emdash | cms | emdashcms.com | `no_price` | — | — | 1 | 같음 |
| Ackee | analytics | ackee.electerious.com | `no_price` | — | — | 1 | 같음 |
| suitenumerique/docs | cms | docs.la-suite.eu | `no_price` | — | — | 1 | **판독 가능해짐**(레포 homepage 가 SPA 주소에서 바뀜) |
| uptime-kuma | monitoring | uptime.kuma.pet | `unknown` | — | — | 1 | 같음(JS 렌더링) |
