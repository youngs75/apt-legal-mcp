# 공동주택 법률 자문 AI 시스템 — 전체 구현 계획서

## 1. 프로젝트 개요

### 1.1 Use Case 명

공동주택 법률 자문 및 분쟁 대응 지원 MCP (범용 → 아파트 단지 적용)

### 1.2 서비스 개요

아파트 단지 내 일상 분쟁부터 재건축·입찰까지, 입주민의 법률 질의에 근거 기반 답변을 제공하는 MCP 기반 시스템이다.

공동주택 생활에서 발생하는 층간소음, 주차, 반려동물, 관리비, 하자보수 등의 분쟁 상황과 재건축·리모델링, 관리업체 입찰 등 의사결정 상황에서, 비전문가인 입주민이 관련 법률 근거를 즉시 확인하기 어렵다는 문제를 해소하는 것을 목표로 한다.

사용자의 자연어 질문을 기반으로 분쟁 유형을 분류하고, 적용 가능한 법률(공동주택관리법, 집합건물법, 주택법, 민법 등)의 조문, 관련 판례, 행정해석을 자동으로 조회하여 단계적으로 안내한다.

법령 조회만으로 충분하지 않은 경우, 해당 단지의 관리규약, 입주민 FAQ, 과거 유사 분쟁 사례 등 단지 특화 지식 기반을 활용하여 맥락에 맞는 답변을 제공하거나, 입주자대표회의·관리사무소·외부 법률 자문 등 후속 조치로 연결하여 실질적 문제 해결까지 이어지도록 지원한다.

본 과제에서는 이러한 범용 구조를 기반으로 카카오톡 단체 채팅방 환경에 적용하여, 실제 아파트 단지 내 법률 질의 응답 및 분쟁 대응 시나리오에서의 활용 가능성을 검증한다.

### 1.3 사용자

- 아파트 단지 입주민(세대주, 세입자)
- 입주자대표회의 임원
- 관리사무소 직원
- 선거관리위원회 위원
- 이를 활용하는 Legal Vertical AI Agent

### 1.4 목표

- 공동주택관리법, 집합건물법, 주택법, 민법 등 관련 법령을 표준화된 방식으로 검색·조회
- 분쟁 유형별 적용 가능한 법률 근거를 자동 매칭
- 재건축·리모델링 절차에 대한 단계별 법적 요건 조회
- 관리업체 선정, 공사 발주 등 입찰 관련 규정을 Agent가 도구 형태로 호출
- MCP 서버를 통한 Streamable HTTP 배포 및 A2A 연동 아키텍처 검증
- ChatGPT Enterprise CustomGPT를 통한 playground 시연

---

## 2. 시스템 아키텍처

### 2.1 전체 구성

```
[ChatGPT Enterprise / CustomGPT]
         ↓ (A2A Protocol)
[Apt-Legal Agent]          ← AWS EKS Pod
  - 분쟁 유형 분류
  - 적용 법령 판별
  - MCP 호출 오케스트레이션
  - 최종 응답 생성
         ↓ (MCP Streamable HTTP)
[Apt-Legal MCP Server]           ← AWS EKS Pod
  - search_law
  - get_law_article
  - search_precedent
  - get_precedent_detail
  - search_interpretation
  - compare_laws
         ↓ (REST API)
[국가법령정보센터 Open API]
[대법원 판례 DB / 전처리 데이터]
```

### 2.2 컴포넌트 목록

| 컴포넌트 | 역할 | 배포 위치 |
|----------|------|-----------|
| ChatGPT Enterprise CustomGPT | 사용자 인터페이스, 시연 playground | OpenAI 호스팅 |
| Apt-Legal Agent | A2A 호스트, 질의 해석, 오케스트레이션, 응답 생성 | EKS Pod |
| Apt-Legal MCP Server | 법령/판례/행정해석 조회 도구 제공 | EKS Pod |
| 국가법령정보센터 Open API | 법령 조문 원본 데이터 | 외부 API |
| 판례 데이터 스토어 | 전처리된 판례 데이터 (JSON/SQLite) | EKS PV 또는 S3 |

### 2.3 기술 스택

| 영역 | 기술 |
|------|------|
| 언어 | Python 3.12+ |
| MCP 서버 | mcp (Python SDK), Streamable HTTP transport |
| Agent 프레임워크 | FastAPI + A2A Protocol |
| LLM 호출 | LiteLLM (gpt-4o via OpenAI API) |
| 컨테이너 | Docker |
| 오케스트레이션 | Kubernetes (AWS EKS) |
| 외부 API | 국가법령정보센터 Open API (law.go.kr) |
| 판례 저장 | SQLite (EKS PV) 또는 S3 JSON |
| 캐싱 | 인메모리 캐시 (TTL 24h) |

---

## 3. MCP 서버 상세 설계

### 3.1 서버 식별 정보

```json
{
  "name": "apt-legal-mcp",
  "version": "1.0.0",
  "description": "한국 공동주택 관련 법령·판례·행정해석 조회 MCP 서버"
}
```

### 3.2 Tools 정의

#### 3.2.1 search_law

키워드 기반 관련 법령 조문 검색.

```
Input:
  - query: string (필수) — 검색 키워드 (예: "층간소음", "재건축 동의율")
  - law_name: string (선택) — 특정 법령명으로 한정 (예: "공동주택관리법")
  - max_results: integer (선택, 기본값 5) — 최대 반환 건수

Output:
  - results: array of object
    - law_name: string — 법령명
    - article_number: string — 조문 번호 (예: "제20조")
    - article_title: string — 조문 제목
    - snippet: string — 조문 요약 또는 매칭 부분 발췌
    - relevance_score: float — 검색 관련도 (0.0~1.0)
```

#### 3.2.2 get_law_article

특정 법률의 조·항·호 단위 조문 전문 조회.

```
Input:
  - law_name: string (필수) — 법령명 (예: "공동주택관리법")
  - article_number: string (필수) — 조문 번호 (예: "제20조")
  - include_history: boolean (선택, 기본값 false) — 개정 이력 포함 여부

Output:
  - law_name: string
  - article_number: string
  - article_title: string
  - full_text: string — 조문 전문 (항·호 포함)
  - enforcement_date: string — 시행일
  - last_amended: string — 최근 개정일
  - amendment_history: array (include_history=true인 경우)
```

#### 3.2.3 search_precedent

분쟁 유형 키워드 기반 관련 판례 검색.

```
Input:
  - query: string (필수) — 검색 키워드 (예: "층간소음 손해배상")
  - court_level: string (선택) — 법원급 필터 ("대법원", "고등법원", "지방법원")
  - max_results: integer (선택, 기본값 5)

Output:
  - results: array of object
    - case_number: string — 사건번호 (예: "2020다12345")
    - court: string — 판결 법원
    - date: string — 판결일
    - summary: string — 판결 요지 (200자 이내)
    - keywords: array of string — 핵심 키워드
```

#### 3.2.4 get_precedent_detail

판례 상세 정보 조회.

```
Input:
  - case_number: string (필수) — 사건번호

Output:
  - case_number: string
  - court: string
  - date: string
  - case_type: string — 사건 유형 (민사, 행정 등)
  - summary: string — 판결 요지
  - facts: string — 사실관계 요약
  - reasoning: string — 판단 근거 요약
  - ruling: string — 주문 요약
  - related_laws: array of string — 적용 법령 목록
```

#### 3.2.5 search_interpretation

행정해석·유권해석 검색.

```
Input:
  - query: string (필수) — 검색 키워드
  - source: string (선택) — 출처 필터 ("국토교통부", "중앙공동주택관리지원센터", "법제처")
  - max_results: integer (선택, 기본값 5)

Output:
  - results: array of object
    - title: string — 해석 제목
    - source: string — 출처 기관
    - date: string — 발행일
    - question: string — 질의 요지
    - answer: string — 회답 요지
    - related_laws: array of string — 관련 법령
```

#### 3.2.6 compare_laws

두 개 이상의 법령 조문을 비교 조회.

```
Input:
  - comparisons: array of object
    - law_name: string
    - article_number: string
  - focus: string (선택) — 비교 관점 (예: "벌칙", "절차", "요건")

Output:
  - items: array of object
    - law_name: string
    - article_number: string
    - article_title: string
    - full_text: string
  - comparison_note: string — 비교 시 유의사항
```

### 3.3 Resources 정의

```
ResourceTemplate:
  - apt-legal://law/{law_name}/article/{article_number}
    → 특정 조문 전문 반환
  - apt-legal://precedent/{case_number}
    → 특정 판례 상세 반환
  - apt-legal://guide/dispute-types
    → 지원 분쟁 유형 목록 반환
```

### 3.4 Prompts 정의

| Prompt 이름 | 용도 | 필수 인자 |
|-------------|------|-----------|
| dispute_resolution | 일상 분쟁(층간소음, 주차 등) 법률 가이드 | dispute_type, description |
| reconstruction_checklist | 재건축·리모델링 절차 점검 | complex_name, current_stage |
| bid_compliance_check | 관리업체 입찰 규정 점검 | bid_type, contract_amount |
| management_fee_review | 관리비 분쟁 검토 | fee_category, dispute_detail |

### 3.5 외부 API 연동

#### 3.5.1 국가법령정보센터 Open API

- 엔드포인트: `http://www.law.go.kr/DRF/lawService.do`
- 인증: API Key (쿼리 파라미터 `OC`)
- 주요 호출:
  - 법령 검색: `target=law&type=XML&query={검색어}`
  - 조문 조회: `target=law&MST={법령일련번호}&type=XML`
  - 법령 목록: `target=law&type=XML&display=20&page=1`
- Rate Limit: 분당 100회 (추정, 공식 문서 확인 필요)
- 캐싱 전략: 법령 메타데이터 24시간 TTL, 조문 전문 7일 TTL

#### 3.5.2 판례 데이터

- 1차 접근: 대법원 종합법률정보(glaw.scourt.go.kr) 공개 데이터 활용
- 대안: 공동주택 관련 주요 판례 100건을 사전 수집하여 JSON/SQLite로 적재
- 데이터 스키마:

```json
{
  "case_number": "2020다12345",
  "court": "대법원",
  "date": "2021-03-15",
  "case_type": "민사",
  "summary": "...",
  "facts": "...",
  "reasoning": "...",
  "ruling": "...",
  "keywords": ["층간소음", "손해배상", "불법행위"],
  "related_laws": ["민법 제750조", "공동주택관리법 제20조"]
}
```

### 3.6 엔드포인트

| 경로 | 메서드 | 용도 |
|------|--------|------|
| `/` | GET | 서버 정보 반환 |
| `/healthz` | GET | 헬스체크 |
| `/mcp` | POST | MCP Streamable HTTP 엔드포인트 |

### 3.7 에러 처리

| 에러 코드 | 상황 | 처리 |
|-----------|------|------|
| LAW_API_TIMEOUT | 법령 API 응답 지연 | 캐시 데이터 반환 + 경고 메시지 |
| LAW_NOT_FOUND | 법령/조문 미발견 | 유사 검색어 제안 반환 |
| PRECEDENT_NOT_FOUND | 판례 미발견 | 키워드 재검색 안내 |
| RATE_LIMIT_EXCEEDED | API 호출 한도 초과 | 캐시 우선 반환 + 재시도 큐 |
| INVALID_INPUT | 입력값 검증 실패 | 구체적 검증 오류 메시지 |

---

## 4. Vertical Agent 상세 설계

### 4.1 Agent 역할

Apt-Legal Agent는 사용자의 자연어 질문을 해석하고, 적절한 MCP 도구를 호출하며, 결과를 종합하여 비전문가가 이해할 수 있는 법률 답변을 생성한다.

### 4.2 A2A 인터페이스

Agent는 A2A(Agent-to-Agent) 프로토콜을 지원하여 ChatGPT Enterprise CustomGPT에서 호출 가능해야 한다.

```
A2A Agent Card:
  name: "apt-legal-agent"
  description: "공동주택 법률 자문 AI Agent"
  url: "https://{eks-endpoint}/a2a"
  version: "1.0.0"
  capabilities:
    streaming: true
    pushNotifications: false
  skills:
    - id: "legal_consultation"
      name: "법률 상담"
      description: "공동주택 관련 법률 질의에 대해 법령·판례 근거 기반 답변 제공"
      inputModes: ["text"]
      outputModes: ["text"]
```

### 4.3 분쟁 유형 분류 체계

Agent가 사용자 질문을 아래 분쟁 유형으로 분류한다:

| 유형 코드 | 분쟁 유형 | 주요 적용 법령 |
|-----------|----------|---------------|
| NOISE | 층간소음 | 공동주택관리법 제20조, 민법 제217조 |
| PARKING | 주차 분쟁 | 공동주택관리법 제35조, 도로교통법 |
| PET | 반려동물 | 공동주택관리법 제18조, 동물보호법 |
| MGMT_FEE | 관리비 | 공동주택관리법 제23조 |
| DEFECT | 하자보수 | 공동주택관리법 제36조, 민법 제667조 |
| RECON | 재건축 | 도시정비법, 주택법 |
| REMODEL | 리모델링 | 주택법 제66조 |
| BID | 입찰/계약 | 공동주택관리법 제25조 |
| ELECTION | 대표회의 선거 | 공동주택관리법 제14조 |
| GENERAL | 기타 법률 질의 | 질의 내용에 따라 동적 판별 |

### 4.4 오케스트레이션 플로우

```
1. 사용자 메시지 수신 (A2A)
2. 질의 분석
   - 분쟁 유형 분류 (LLM structured output)
   - 핵심 키워드 추출
   - 질의 의도 판별 (법령 확인 / 절차 안내 / 분쟁 대응 방법)
3. MCP 도구 호출 계획 수립
   - 분쟁 유형별 기본 호출 세트 결정
   - 예: NOISE → search_law("층간소음") + search_precedent("층간소음 손해배상")
4. MCP 도구 병렬 호출
   - search_law → 관련 법령 조문 검색
   - search_precedent → 관련 판례 검색
   - search_interpretation → 행정해석 검색 (필요시)
5. 결과 수신 및 추가 조회 판단
   - 검색 결과에서 특정 조문이 중요하면 get_law_article 추가 호출
   - 특정 판례가 관련성 높으면 get_precedent_detail 추가 호출
6. 응답 생성 (LLM)
   - 비전문가용 평이한 언어로 작성
   - 법령 조문 근거 명시
   - 판례 결과 요약 포함
   - 후속 조치 안내 (필요시)
7. A2A 응답 반환
```

### 4.5 응답 구조

```json
{
  "answer": "층간소음에 대한 법적 대응은 다음과 같습니다...",
  "legal_basis": [
    {
      "type": "law",
      "reference": "공동주택관리법 제20조",
      "summary": "입주자등은 공동주택에서 소음·진동 등으로..."
    },
    {
      "type": "precedent",
      "reference": "2020다12345",
      "summary": "대법원은 층간소음으로 인한 손해배상 책임을..."
    }
  ],
  "next_steps": [
    "관리사무소에 서면 민원 접수",
    "환경분쟁조정위원회 조정 신청",
    "민사 소송 (손해배상 청구)"
  ],
  "disclaimer": "본 답변은 일반적인 법률 정보 제공 목적이며, 구체적 사안에 대해서는 법률 전문가 상담을 권장합니다."
}
```

### 4.6 프롬프트 전략

#### System Prompt (Agent)

```
당신은 공동주택(아파트) 법률 자문 전문 AI입니다.

역할:
- 입주민의 법률 질문을 이해하고 관련 법령·판례를 조회합니다
- 비전문가가 이해할 수 있는 쉬운 언어로 답변합니다
- 반드시 법적 근거(법령 조문, 판례)를 명시합니다
- 확실하지 않은 내용은 추측하지 않고 전문가 상담을 권장합니다

제약:
- 법률 자문이 아닌 법률 정보 제공임을 명확히 합니다
- 모든 답변 말미에 면책 문구를 포함합니다
- 개인정보나 특정 단지 정보를 저장하지 않습니다
- 형사 사건 관련 질문은 경찰/검찰 안내로 전환합니다

도구 사용 원칙:
- 법령 근거가 필요하면 반드시 search_law → get_law_article 순서로 조회합니다
- 유사 사례가 도움이 되면 search_precedent를 호출합니다
- 행정해석이 있는 영역이면 search_interpretation도 병행합니다
- 도구 호출 없이 기억에 의존한 법령 인용을 하지 않습니다
```

---

## 5. 배포 구성

### 5.1 Docker 이미지

```
apt-legal-mcp:1.0.0        — MCP 서버
apt-legal-agent:1.0.0 — Vertical Agent
```

### 5.2 Kubernetes 리소스

| 리소스 | 이름 | 설명 |
|--------|------|------|
| Deployment | apt-legal-mcp | MCP 서버 Pod (replicas: 1) |
| Deployment | apt-legal-agent | Agent Pod (replicas: 1) |
| Service | apt-legal-mcp-svc | ClusterIP, 포트 8001 |
| Service | apt-legal-agent-svc | ClusterIP, 포트 8000 |
| Ingress | apt-legal-agent-ingress | ALB, 외부 노출 (/a2a) |
| ConfigMap | apt-legal-config | 법령 API 키, 모델 설정 |
| Secret | apt-legal-secrets | API 키, LLM API 키 |

### 5.3 네트워크 토폴로지

```
Internet
  ↓
ALB (AWS EKS Ingress)
  ↓
apt-legal-agent-svc:8000    ← 외부 노출 (A2A endpoint)
  ↓ (클러스터 내부)
apt-legal-mcp-svc:8001   ← 내부 전용 (MCP endpoint)
  ↓ (외부 호출)
law.go.kr API            ← 국가법령정보센터
```

### 5.4 환경 변수

```bash
# MCP 서버
LAW_API_KEY=           # 국가법령정보센터 API 키
LAW_API_BASE_URL=http://www.law.go.kr/DRF/lawService.do
PRECEDENT_DB_PATH=/data/precedents.db
CACHE_TTL_HOURS=24
SERVER_PORT=8001

# Agent
MCP_SERVER_URL=http://apt-legal-mcp-svc:8001/mcp
LLM_API_KEY=           # OpenAI API 키
LLM_MODEL=gpt-4o
LLM_TEMPERATURE=0.1
AGENT_PORT=8000
A2A_AGENT_NAME=apt-legal-agent
```

---

## 6. 시연 계획

### 6.1 시연 환경

ChatGPT Enterprise → CustomGPT (A2A 연동) → Apt-Legal Agent (EKS) → Apt-Legal MCP Server (EKS)

### 6.2 시연 시나리오

#### 시나리오 1: 단순 법령 조회

```
사용자: "공동주택에서 층간소음 기준이 몇 데시벨이야?"

Agent 동작:
  1. 분쟁 유형: NOISE
  2. search_law("층간소음 기준 데시벨") 호출
  3. get_law_article("공동주택관리법", "제20조") 호출
  4. 법령 조문 기반 답변 생성

기대 응답:
  - 공동주택관리법 제20조 및 시행령 관련 조항 안내
  - 주간/야간 소음 기준 수치 안내
  - 환경부 고시 연계 정보
```

#### 시나리오 2: 복합 분쟁 대응

```
사용자: "윗집 층간소음이 너무 심한데 법적으로 어떻게 대응할 수 있나요?"

Agent 동작:
  1. 분쟁 유형: NOISE, 의도: 분쟁 대응 방법
  2. search_law("층간소음") 호출
  3. search_precedent("층간소음 손해배상") 호출
  4. search_interpretation("층간소음 관리규약") 호출
  5. 법령 + 판례 + 해석 종합 응답 생성

기대 응답:
  - 관련 법령 근거 제시
  - 유사 판례 결과 요약
  - 단계별 대응 방법 (관리사무소 민원 → 환경분쟁조정 → 민사소송)
  - 면책 문구
```

#### 시나리오 3: 재건축 절차 안내

```
사용자: "재건축 추진하려면 동의율이 얼마나 필요해?"

Agent 동작:
  1. 분쟁 유형: RECON
  2. search_law("재건축 동의율") 호출
  3. get_law_article("도시및주거환경정비법", "제35조") 호출
  4. 절차별 요건 정리 응답 생성

기대 응답:
  - 안전진단 → 정비구역 지정 → 조합 설립 → 사업시행 단계별 동의율
  - 최근 법 개정 사항 반영
  - 주의사항 안내
```

---

## 7. 일정 계획

| 주차 | 작업 | 산출물 |
|------|------|--------|
| 1주차 | MCP 서버 개발 (Tools 구현, 법령 API 연동) | apt-legal-mcp 서버 |
| 1주차 | 판례 데이터 사전 수집 및 적재 | precedents.db |
| 2주차 | Vertical Agent 개발 (A2A, 오케스트레이션) | apt-legal-agent |
| 2주차 | EKS 배포 및 ChatGPT Enterprise 연동 | 배포 완료 |
| 3주차 | 시연 시나리오 테스트 및 튜닝 | 시연 영상/문서 |
| 3주차 | 최종 문서 정리 및 발표 준비 | 최종 보고서 |

---

## 8. 확장 로드맵

| 단계 | 내용 |
|------|------|
| Phase 2 | 카카오톡 봇 연동 (Webhook → Agent) |
| Phase 2 | 단지별 관리규약 RAG Layer 추가 |
| Phase 3 | 입주민 FAQ 자동 생성 및 갱신 |
| Phase 3 | 관리사무소용 대시보드 (질의 통계, 빈발 분쟁 유형) |
| Phase 4 | 다세대주택, 오피스텔 등 타 공동주택 유형으로 확장 |
