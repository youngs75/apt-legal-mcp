# Kor-Legal MCP Server — Codex 작업지시서

> **⚠️ 범용화 노트 (2026-04-14):** 원래 `apt-legal-mcp`(공동주택 한정)로 작성되었으나, 현재는 `kor-legal-mcp`로 **도메인 무관 범용 한국 법령 MCP 서버**로 재정의되었다. 도메인 narrative는 historical context로 보존하되, 식별자/패키지명은 갱신된 상태다. 현 구조는 `AGENTS.md` 참조.

## 개요

한국 공동주택 관련 법령·판례·행정해석을 조회하는 MCP(Model Context Protocol) 서버를 개발한다.
국가법령정보센터 Open API를 1차 데이터 소스로 사용하며, 판례 데이터는 사전 수집된 JSON/SQLite를 활용한다.
MCP Python SDK 기반의 Streamable HTTP 서버로 구현하며, AWS EKS에 Docker 컨테이너로 배포한다.

---

## 1. 프로젝트 구조

```
kor-legal-mcp/
├── pyproject.toml
├── Dockerfile
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── configmap.yaml
├── src/
│   └── kor_legal_mcp/
│       ├── __init__.py
│       ├── server.py              # MCP 서버 진입점
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── search_law.py      # 법령 검색
│       │   ├── get_law_article.py  # 조문 조회
│       │   ├── search_precedent.py # 판례 검색
│       │   ├── get_precedent_detail.py  # 판례 상세
│       │   ├── search_interpretation.py # 행정해석 검색
│       │   └── compare_laws.py     # 법령 비교
│       ├── resources/
│       │   ├── __init__.py
│       │   └── templates.py        # ResourceTemplate 정의
│       ├── prompts/
│       │   ├── __init__.py
│       │   └── definitions.py      # Prompt 정의
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── law_api.py          # 국가법령정보센터 API 클라이언트
│       │   └── precedent_db.py     # 판례 DB 클라이언트
│       ├── cache/
│       │   ├── __init__.py
│       │   └── memory_cache.py     # TTL 기반 인메모리 캐시
│       ├── models/
│       │   ├── __init__.py
│       │   └── schemas.py          # Pydantic 입출력 스키마
│       └── config.py               # 환경 변수 및 설정
├── data/
│   ├── precedents.json             # 사전 수집 판례 데이터
│   └── seed_precedents.py          # 판례 DB 초기화 스크립트
├── tests/
│   ├── test_tools.py
│   ├── test_clients.py
│   ├── test_cache.py
│   └── conftest.py
└── scripts/
    └── run_stdio.py                # 로컬 stdio 모드 실행
```

---

## 2. 의존성

```toml
# pyproject.toml
[project]
name = "kor-legal-mcp"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = [
    "mcp>=1.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.0",
    "uvicorn>=0.30.0",
    "starlette>=0.38.0",
    "aiosqlite>=0.20.0",
    "lxml>=5.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-httpx>=0.30",
    "ruff>=0.5",
]
```

---

## 3. 핵심 구현 상세

### 3.1 server.py — MCP 서버 진입점

```python
"""
MCP 서버 메인 모듈.

기능:
1. MCP Server 인스턴스 생성 (name="kor-legal-mcp", version="1.0.0")
2. 모든 Tools 등록 (6개)
3. 모든 Resources 등록
4. 모든 Prompts 등록
5. 두 가지 transport 모드 지원:
   - stdio: 로컬 개발용 (scripts/run_stdio.py에서 호출)
   - Streamable HTTP: 원격 배포용 (/mcp 엔드포인트)
6. FastAPI/Starlette 앱으로 HTTP 엔드포인트 제공:
   - GET  /          → 서버 정보 JSON 반환
   - GET  /healthz   → 헬스체크 (법령 API 연결 상태 포함)
   - POST /mcp       → MCP Streamable HTTP 엔드포인트
"""
```

구현 요구사항:
- `mcp.server.Server` 인스턴스를 생성하고, 각 tools/ 모듈의 핸들러를 `@server.tool()` 데코레이터로 등록
- Starlette 앱 위에 `mcp.server.streamable_http.StreamableHTTPServerTransport`를 마운트
- `/healthz`는 법령 API에 간단한 테스트 요청을 보내 연결 상태를 확인. 실패 시에도 200을 반환하되 `"law_api": "unavailable"` 표시
- 서버 시작 시 `law_api.py`의 워밍업 함수를 호출하여 주요 법령 메타데이터를 캐시에 적재

### 3.2 clients/law_api.py — 국가법령정보센터 API 클라이언트

```python
"""
국가법령정보센터 Open API 클라이언트.

엔드포인트: http://www.law.go.kr/DRF/lawService.do
인증: 쿼리 파라미터 OC={API_KEY}
응답 형식: XML

구현할 메서드:

1. search_laws(query: str, max_results: int = 5) -> list[LawSearchResult]
   - API 호출: target=law&type=XML&query={query}&display={max_results}
   - XML 파싱하여 법령명, 법령일련번호, 시행일 추출
   - 캐시 적용 (query 기준 TTL 24h)

2. get_law_detail(mst: str) -> LawDetail
   - API 호출: target=law&MST={mst}&type=XML
   - 조문 전체 파싱 (조문번호, 조문제목, 조문내용, 항, 호)
   - 조문 구조를 계층적 dict로 변환
   - 캐시 적용 (mst 기준 TTL 7일)

3. get_law_article_by_number(law_name: str, article_number: str) -> ArticleDetail
   - 먼저 search_laws(law_name)으로 법령일련번호(MST) 획득
   - get_law_detail(mst)로 전체 조문 획득
   - article_number에 해당하는 조문만 필터링하여 반환
   - article_number 정규화: "제20조", "20조", "제20", "20" 모두 매칭

4. warmup() -> None
   - 주요 법령 6개의 메타데이터를 사전 캐싱:
     * 공동주택관리법
     * 공동주택관리법 시행령
     * 집합건물의 소유 및 관리에 관한 법률
     * 주택법
     * 도시 및 주거환경정비법
     * 민법 (제2편 물권, 제3편 채권 중 불법행위)
   - 서버 시작 시 비동기로 실행
   - 실패해도 서버 시작을 블로킹하지 않음 (로그 경고만 출력)

XML 파싱 주의사항:
- lxml 사용 (표준 xml.etree보다 인코딩 처리 안정적)
- 국가법령정보센터 XML은 EUC-KR 인코딩 응답이 올 수 있음 → httpx 응답의 encoding을 확인하고 적절히 디코딩
- XML 네임스페이스가 없는 경우가 많으므로 네임스페이스 없이 파싱
- 조문 내용에 HTML 엔티티(&amp; &lt; 등)가 포함될 수 있음 → 디코딩 처리
"""
```

### 3.3 clients/precedent_db.py — 판례 DB 클라이언트

```python
"""
사전 수집된 판례 데이터를 검색하는 클라이언트.

저장소: SQLite (aiosqlite)
파일 위치: 환경변수 PRECEDENT_DB_PATH (기본값: /data/precedents.db)

테이블 스키마:

CREATE TABLE precedents (
    case_number TEXT PRIMARY KEY,
    court TEXT NOT NULL,
    date TEXT NOT NULL,
    case_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    facts TEXT,
    reasoning TEXT,
    ruling TEXT,
    keywords TEXT NOT NULL,       -- JSON array
    related_laws TEXT NOT NULL    -- JSON array
);

CREATE VIRTUAL TABLE precedent_fts USING fts5(
    case_number, summary, facts, reasoning, keywords,
    content=precedents, content_rowid=rowid
);

구현할 메서드:

1. search(query: str, court_level: str | None, max_results: int) -> list[PrecedentSearchResult]
   - FTS5 전문 검색 사용
   - court_level 필터링 (선택)
   - BM25 스코어 기반 정렬
   - keywords JSON 배열과도 매칭

2. get_detail(case_number: str) -> PrecedentDetail | None
   - PRIMARY KEY 기반 단건 조회
   - keywords, related_laws는 JSON 파싱하여 list[str]로 반환

3. initialize(json_path: str) -> None
   - data/precedents.json에서 판례 데이터 로드
   - 테이블 생성 (IF NOT EXISTS)
   - FTS 인덱스 빌드
   - 서버 최초 실행 시 호출
"""
```

### 3.4 cache/memory_cache.py — 인메모리 캐시

```python
"""
TTL 기반 인메모리 캐시.

요구사항:
- asyncio 호환 (async get/set)
- TTL 만료 시 자동 제거 (lazy eviction)
- 최대 항목 수 제한 (기본 1000개, LRU 방식 eviction)
- 키: 문자열 (API 호출 파라미터의 해시)
- 값: 임의 Python 객체

구현:
- collections.OrderedDict 기반
- get 시 TTL 확인 → 만료면 제거 후 None 반환
- set 시 최대 항목 초과면 가장 오래된 항목 제거

캐시 키 생성 규칙:
- 함수명 + 정렬된 파라미터의 SHA256 해시
- 예: "search_laws:sha256(query=층간소음&max_results=5)"
"""
```

### 3.5 models/schemas.py — Pydantic 스키마

```python
"""
모든 입출력 스키마를 Pydantic v2 모델로 정의.

각 Tool별 Input/Output 모델:

1. SearchLawInput / SearchLawOutput
   - Input: query(str), law_name(str|None), max_results(int=5)
   - Output: results(list[LawSearchResultItem])
     - LawSearchResultItem: law_name, article_number, article_title, snippet, relevance_score

2. GetLawArticleInput / GetLawArticleOutput
   - Input: law_name(str), article_number(str), include_history(bool=False)
   - Output: law_name, article_number, article_title, full_text, enforcement_date, last_amended, amendment_history(list|None)

3. SearchPrecedentInput / SearchPrecedentOutput
   - Input: query(str), court_level(str|None), max_results(int=5)
   - Output: results(list[PrecedentSearchResultItem])
     - PrecedentSearchResultItem: case_number, court, date, summary, keywords(list[str])

4. GetPrecedentDetailInput / GetPrecedentDetailOutput
   - Input: case_number(str)
   - Output: case_number, court, date, case_type, summary, facts, reasoning, ruling, related_laws(list[str])

5. SearchInterpretationInput / SearchInterpretationOutput
   - Input: query(str), source(str|None), max_results(int=5)
   - Output: results(list[InterpretationResultItem])
     - InterpretationResultItem: title, source, date, question, answer, related_laws(list[str])

6. CompareLawsInput / CompareLawsOutput
   - Input: comparisons(list[ComparisonItem]), focus(str|None)
     - ComparisonItem: law_name(str), article_number(str)
   - Output: items(list[ComparisonResultItem]), comparison_note(str)

모든 모델에 적용:
- field validator로 입력값 검증 (빈 문자열 거부, max_results 범위 1~20)
- model_config에 json_schema_extra로 MCP tool description용 예제 포함
"""
```

### 3.6 tools/ — 각 Tool 구현

각 Tool 파일의 공통 구조:

```python
"""
Tool 핸들러 구현 패턴.

각 tool 파일은 다음 구조를 따른다:

1. Pydantic Input 모델로 입력값 검증
2. 캐시 확인 → 히트 시 즉시 반환
3. 외부 API/DB 호출 (law_api 또는 precedent_db)
4. 결과를 Output 모델로 변환
5. 캐시에 저장
6. MCP content 형식으로 반환 (TextContent)

에러 처리:
- 입력값 검증 실패 → McpError(INVALID_PARAMS, 구체적 메시지)
- API 호출 실패 → 캐시 데이터 반환 시도, 없으면 McpError(INTERNAL_ERROR, 메시지)
- 데이터 미발견 → 빈 결과 반환 + 유사 검색어 제안

MCP 반환 형식:
- 모든 Tool은 list[TextContent]를 반환
- TextContent.text에 JSON 직렬화된 결과를 담음
- JSON은 한국어 유지 (ensure_ascii=False)
"""
```

#### tools/search_law.py 구현 상세

```python
"""
search_law Tool.

MCP 등록:
  @server.tool()
  async def search_law(query: str, law_name: str | None = None, max_results: int = 5) -> list[TextContent]

동작:
1. query를 정규화 (앞뒤 공백 제거, 연속 공백 단일화)
2. law_name이 주어지면 "{law_name} {query}" 형태로 결합하여 검색
3. law_api.search_laws() 호출
4. 결과가 없으면:
   - query에서 주요 키워드 추출 (조사/어미 제거)
   - 재검색 1회 시도
   - 그래도 없으면 빈 결과 + "검색 결과가 없습니다. 다른 키워드를 시도해 주세요." 메시지
5. 결과를 relevance_score 내림차순 정렬
6. max_results만큼 잘라서 반환
"""
```

#### tools/search_precedent.py 구현 상세

```python
"""
search_precedent Tool.

MCP 등록:
  @server.tool()
  async def search_precedent(query: str, court_level: str | None = None, max_results: int = 5) -> list[TextContent]

동작:
1. precedent_db.search() 호출 (FTS5 검색)
2. court_level 값 정규화:
   - "대법원", "supreme" → "대법원"
   - "고등", "high" → "고등법원"
   - "지방", "district" → "지방법원"
3. 결과를 PrecedentSearchResultItem 목록으로 변환
4. JSON 직렬화하여 TextContent로 반환

주의사항:
- 판례 DB가 비어있거나 초기화되지 않은 경우 명확한 에러 메시지 반환
- FTS5 쿼리에 특수문자가 들어오면 이스케이프 처리
"""
```

### 3.7 resources/templates.py

```python
"""
MCP ResourceTemplate 정의.

등록할 리소스 템플릿:

1. kor-legal://law/{law_name}/article/{article_number}
   - URI 패턴 매칭으로 법령명과 조문번호 추출
   - get_law_article Tool과 동일한 로직 실행
   - 텍스트 형식으로 조문 전문 반환

2. kor-legal://precedent/{case_number}
   - 판례 상세 정보 반환
   - get_precedent_detail Tool과 동일한 로직

3. kor-legal://guide/dispute-types
   - 지원하는 분쟁 유형 목록 반환 (정적 데이터)
   - 각 유형별 주요 적용 법령 포함
"""
```

### 3.8 prompts/definitions.py

```python
"""
MCP Prompt 정의.

등록할 프롬프트:

1. dispute_resolution
   - 인자: dispute_type(str), description(str)
   - 시스템 메시지: 분쟁 유형별 법률 가이드 제공 프롬프트
   - 사용자 메시지 템플릿: "분쟁 유형: {dispute_type}\n상황 설명: {description}"

2. reconstruction_checklist
   - 인자: complex_name(str), current_stage(str)
   - 재건축/리모델링 절차 점검용
   - current_stage 값: "안전진단", "정비구역지정", "조합설립", "사업시행", "관리처분"

3. bid_compliance_check
   - 인자: bid_type(str), contract_amount(str)
   - 입찰 규정 점검용
   - bid_type 값: "관리업체선정", "공사발주", "용역계약"

4. management_fee_review
   - 인자: fee_category(str), dispute_detail(str)
   - 관리비 분쟁 검토용
   - fee_category 값: "일반관리비", "청소비", "경비비", "수선유지비", "장기수선충당금"
"""
```

---

## 4. 데이터 준비

### 4.1 판례 시드 데이터

`data/precedents.json` 파일에 공동주택 관련 주요 판례를 수집하여 적재한다.

수집 대상 분쟁 유형별 최소 판례 수:
- 층간소음: 15건
- 주차 분쟁: 10건
- 관리비 분쟁: 10건
- 하자보수: 10건
- 재건축/리모델링: 10건
- 대표회의 선거: 5건
- 반려동물: 5건
- 입찰/계약: 5건
- 기타: 10건

각 판례 데이터 형식:

```json
{
  "case_number": "2020다12345",
  "court": "대법원",
  "date": "2021-03-15",
  "case_type": "민사",
  "summary": "층간소음으로 인한 손해배상 책임이 인정된 사례. 피고는 야간 시간대에 반복적으로 소음을 발생시켜 원고의 수면권을 침해하였고...",
  "facts": "원고는 아파트 101동 301호에 거주하며, 피고는 401호에 거주한다. 원고는 2019년 1월부터 약 1년간 야간(22:00~06:00) 시간대에...",
  "reasoning": "공동주택관리법 제20조 및 민법 제217조에 따르면 이웃의 생활에 고통을 주는 소음을 발생시키는 행위는 위법하다. 본 건에서...",
  "ruling": "피고는 원고에게 금 500만원 및 이에 대한 지연손해금을 지급하라.",
  "keywords": ["층간소음", "손해배상", "불법행위", "수면권", "야간소음"],
  "related_laws": ["공동주택관리법 제20조", "민법 제750조", "민법 제217조"]
}
```

### 4.2 seed_precedents.py

```python
"""
판례 DB 초기화 스크립트.

실행: python data/seed_precedents.py

동작:
1. data/precedents.json 로드
2. SQLite DB 생성 (PRECEDENT_DB_PATH)
3. precedents 테이블 생성
4. FTS5 가상 테이블 생성
5. 데이터 삽입
6. FTS 인덱스 빌드
7. 삽입 건수 및 FTS 인덱스 상태 출력
"""
```

---

## 5. 배포 설정

### 5.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY src/ src/
COPY data/ data/

# 판례 DB 초기화
RUN python data/seed_precedents.py

EXPOSE 8001
CMD ["python", "-m", "uvicorn", "kor_legal_mcp.server:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 5.2 k8s/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kor-legal-mcp
  labels:
    app: kor-legal-mcp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: kor-legal-mcp
  template:
    metadata:
      labels:
        app: kor-legal-mcp
    spec:
      containers:
        - name: kor-legal-mcp
          image: kor-legal-mcp:1.0.0
          ports:
            - containerPort: 8001
          envFrom:
            - configMapRef:
                name: apt-legal-config
            - secretRef:
                name: apt-legal-secrets
          resources:
            requests:
              cpu: 250m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8001
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8001
            initialDelaySeconds: 5
            periodSeconds: 10
```

### 5.3 k8s/service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: kor-legal-mcp-svc
spec:
  type: ClusterIP
  selector:
    app: kor-legal-mcp
  ports:
    - port: 8001
      targetPort: 8001
      protocol: TCP
```

---

## 6. 테스트 요건

### 6.1 단위 테스트

| 테스트 대상 | 테스트 케이스 | 검증 항목 |
|-------------|-------------|-----------|
| search_law | 정상 키워드 검색 | 결과 반환, 스키마 준수 |
| search_law | 빈 쿼리 | INVALID_PARAMS 에러 |
| search_law | 결과 없는 키워드 | 빈 결과 + 안내 메시지 |
| get_law_article | 정상 법령+조문 | 조문 전문 반환 |
| get_law_article | 존재하지 않는 조문 | LAW_NOT_FOUND 에러 |
| get_law_article | 다양한 조문번호 포맷 | "제20조", "20조", "20" 모두 매칭 |
| search_precedent | 정상 검색 | FTS5 검색 결과 반환 |
| search_precedent | court_level 필터 | 해당 법원급만 반환 |
| get_precedent_detail | 존재하는 사건번호 | 상세 정보 반환 |
| get_precedent_detail | 미존재 사건번호 | None / 에러 메시지 |
| compare_laws | 2개 법령 비교 | 두 조문 모두 반환 |
| cache | TTL 만료 | 만료 후 None 반환 |
| cache | LRU eviction | 최대 항목 초과 시 제거 |

### 6.2 통합 테스트

| 테스트 시나리오 | 검증 항목 |
|----------------|-----------|
| MCP Streamable HTTP 연결 | 클라이언트가 /mcp에 연결 후 tool list 조회 가능 |
| Tool 호출 E2E | MCP 프로토콜로 search_law 호출 → 결과 수신 |
| 캐시 적중 | 동일 쿼리 2회 호출 시 2회차는 API 미호출 확인 |
| 헬스체크 | /healthz 200 응답 + 컴포넌트 상태 포함 |
| stdio 모드 | scripts/run_stdio.py 실행 후 stdin/stdout으로 MCP 통신 |

### 6.3 테스트 실행

```bash
# 단위 테스트
pytest tests/ -v

# 법령 API Mock 사용 (외부 API 의존 제거)
pytest tests/ -v -m "not integration"

# 통합 테스트 (실제 API 호출)
LAW_API_KEY=xxx pytest tests/ -v -m integration
```

---

## 7. 구현 시 주의사항

1. **국가법령정보센터 API 응답 인코딩**: EUC-KR 또는 UTF-8이 혼용됨. httpx 응답의 `charset` 헤더를 확인하고, 없으면 UTF-8을 기본으로 시도 후 실패 시 EUC-KR 시도

2. **조문번호 정규화**: 사용자 입력 "20조", "제20조", "제20조의2", "20-2" 등 다양한 형태를 통일된 포맷으로 정규화하는 유틸리티 함수 구현 필요

3. **법령 검색 결과 관련도**: 국가법령정보센터 API는 관련도 점수를 직접 제공하지 않으므로, 검색어와 조문 제목/내용의 키워드 매칭 비율로 자체 스코어링

4. **XML 파싱 안정성**: 법령 API 응답 XML의 구조가 법령 유형(법률, 시행령, 시행규칙)에 따라 다를 수 있음. 누락 필드에 대한 방어 코딩 필수

5. **판례 데이터 저작권**: 판례 원문은 국가 저작물로 자유이용 가능하나, 가공된 판례 요지는 출처 명시 필요

6. **캐시 키 충돌**: 서로 다른 Tool의 동일 파라미터가 같은 캐시 키를 생성하지 않도록 Tool 이름을 키 프리픽스에 포함

7. **에러 전파**: MCP 프로토콜 에러 코드 사용. 내부 예외는 로깅하되 사용자에게는 정제된 메시지만 반환

8. **동시 요청 처리**: asyncio 기반이므로 법령 API 병렬 호출 시 `asyncio.gather` 활용. 단, rate limit을 고려하여 `asyncio.Semaphore`로 동시 호출 수 제한 (최대 5개)
