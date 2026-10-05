# CEO-119 점수표 회귀 — '셀프서브 구독형' 렌즈 (2026-10-05)

결정(CEO, 10/5): 검색 렌즈를 **소상공인·개인 대상 셀프서브 구독형(국내 결제·카카오 로그인·알림톡 공백)** 으로 좁힌다. W42(10/12 월 08:17 정기 실행)부터 적용.

## 바꾼 것
- 가중치: activity 15→10 · community 10→5 · deploy 15→10 · market 20→15 · **selfserve 20 신설** (합 100)
- 구매자 폭: enterprise 6→2 · devtool 3→1 · consumer 2→3 · business 5→**6(최고)** — 영업 주도 기업·인프라를 낮추는 곳은 여기 한 군데다(별도 감점 없음)
- `selfserve`: 소상공인 카테고리 5 + 셀프 온보딩 신호(토픽·설명 saas/multi-tenant/workspace/teams/subscription/billing/white-label/signup/onboarding, 1개 3 · 2개+ 5)
- 한국 기회: 메시징 제품인데 카카오 언급 없음 → 알림톡 공백 +2 (분모에도 더함). `has_kr_login`(README 의 kakao/naver 언급)으로 근사라 느슨하다
- 새 모델 태그는 넣지 않았다(Notion multi-select 옵션 자동 생성 확인 전)

## 하지 않은 것
- 가격 페이지 판독('개인·소상공인이 낼 수 있는 단가') — HANDOFF 2번 별건. 지금은 구매자 폭 + 카테고리로 근사
- compose 서비스 수(무거운 스택) 판정 · 별도 이미지 EE 탐지 · 모노레포 로케일 경로 — W41 검토에서 찾은 감사 누락은 그대로

## 회귀 (단일 `score` 호출, 10/5 새벽 · NAVER 키 없음 · 앞 = main 코드, 뒤 = 이 변경)
대상: 10/1 기각 4 · W41 기각 5 · W41 관찰 2 · gpt-load · W41 상위권 나머지 5

| 레포 | 앞 | 뒤 | 차이 | 카테고리/구매자 | selfserve |
|---|---:|---:|---:|---|---:|
| [dittofeed/dittofeed](https://github.com/dittofeed/dittofeed) | 80 | 88 | +8 | notification/business | 20.0 |
| [emdash-cms/emdash](https://github.com/emdash-cms/emdash) | 85 | 80 | -5 | cms/business | 10.0 |
| [talivia-group/talivia](https://github.com/talivia-group/talivia) | 83 | 78 | -5 | analytics/business | 10.0 |
| [vas3k/TaxHacker](https://github.com/vas3k/TaxHacker) | 81 | 77 | -4 | invoice/business | 10.0 |
| [usekaneo/kaneo](https://github.com/usekaneo/kaneo) | 83 | 77 | -6 | internal-tools/business | 10.0 |
| [suitenumerique/docs](https://github.com/suitenumerique/docs) | 83 | 77 | -6 | cms/business | 10.0 |
| [Paymenter/Paymenter](https://github.com/Paymenter/Paymenter) | 82 | 77 | -5 | commerce/business | 10.0 |
| [bagisto/bagisto](https://github.com/bagisto/bagisto) | 90 | 75 | -15 | commerce/enterprise | 16.0 |
| [electerious/Ackee](https://github.com/electerious/Ackee) | 80 | 74 | -6 | analytics/business | 10.0 |
| [xerrors/Yuxi](https://github.com/xerrors/Yuxi) | 84 | 68 | -16 | llm-workflow/business | 0.0 |
| [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | 84 | 68 | -16 | llm-workflow/business | 0.0 |
| [mudler/LocalAI](https://github.com/mudler/LocalAI) | 82 | 66 | -16 | llm-workflow/business | 0.0 |
| [tbphp/gpt-load](https://github.com/tbphp/gpt-load) | 73 | 56 | -17 | devtool/devtool | 6.0 |
| [prest/prest](https://github.com/prest/prest) | 86 | 56 | -30 | llm-workflow/enterprise | 0.0 |
| [hyperdxio/hyperdx](https://github.com/hyperdxio/hyperdx) | 82 | 54 | -28 | monitoring/enterprise | 0.0 |
| [beenuar/AiSOC](https://github.com/beenuar/AiSOC) | 82 | 54 | -28 | llm-workflow/enterprise | 0.0 |
| [eosphoros-ai/DB-GPT](https://github.com/eosphoros-ai/DB-GPT) | 81 | 53 | -28 | llm-workflow/enterprise | 0.0 |

## 읽기
- **기업·인프라는 −16~−30**: prest −30 · hyperdx · AiSOC · DB-GPT −28 · LightRAG · Yuxi · LocalAI −16(llm-workflow 는 소상공인 카테고리 아님) · gpt-load −17. W41 기각 5개 중 기업·인프라 3개는 크게 내려갔다(AiSOC 54 · DB-GPT 53 · LocalAI 66). 10/1 기각 hyperdx 도 54.
- **dittofeed 80 → 88, 이 묶음 1위**: 소상공인 카테고리(notification)에 셀프 온보딩 신호 2개 이상이고, 알림톡 공백도 잡혔다. W41 관찰 판정과 일치한다.
- **결과가 바뀌는 것(CEO 판단 요청)**: 10/1 기각인 TaxHacker(77) · kaneo(77)는 소상공인 카테고리라 상대 순위가 오른다(절대 점수는 −4·−6). Notion Rejected 필터가 리포트에서는 계속 뺀다. 렌즈상 TaxHacker(소상공인 회계)를 다시 볼지는 CEO 판단.
- **렌즈가 못 거르는 것**: Paymenter(77) · Ackee(74) — 소상공인 카테고리라 점수가 남는다. W41 기각 사유(국내 시장 협소 · 유료화 빈자리 없음)는 점수표 신호가 아니라 사람 판단으로 남는다.
- bagisto 90 → 75(enterprise 로 분류돼 시장 −15).
