# Apt-Legal Agent — Codex 작업지시서

> **⚠️ 참고 (2026-04-15 갱신):** 본 문서는 별도 리포 `apt-legal-agent`(Vertical AI Agent)의 작업지시서이며, 본 리포(`kor-legal-mcp`)에는 **참고용**으로만 보관된다. Agent 측 도메인 지식(공동주택 운영규약, 분쟁 유형 등)은 Agent와 별도 RAG MCP 서버에서 처리하고, 본 MCP 서버는 범용 법령 조회만 담당한다.
>
> **현 운영 상태 (2026-04-15):** Vertical Agent는 아직 구현되지 않았으며, 현재는 **ChatGPT Enterprise CustomGPT `한국 법령 리서처`가 kor-legal-mcp를 직접 호출**하는 구성이 운영 중이다. 본 문서에 기술된 A2A/FastAPI/LiteLLM 스택은 Phase 2 확장 옵션이며, 본 리포 작업에 직접 영향을 주지 않는다. 또한 본 문서의 MCP tool 참조는 초기 6개 기준이므로, 최신 15개 tool 목록은 `AGENTS.md` 참조.

## 개요

공동주택 법률 자문 Vertical AI Agent를 개발한다.
사용자의 자연어 질문을 해석하여 분쟁 유형을 분류하고, Apt-Legal MCP 서버의 도구들을 오케스트레이션하여 법령·판례 근거 기반의 답변을 생성한다.
A2A(Agent-to-Agent) 프로토콜을 지원하여 ChatGPT Enterprise의 CustomGPT에서 호출 가능하며, AWS EKS에 배포한다.

---

## 1. 프로젝트 구조

```
apt-legal-agent/
├── pyproject.toml
├── Dockerfile
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── ingress.yaml
├── src/
│   └── apt_legal_agent/
│       ├── __init__.py
│       ├── app.py                 # FastAPI 앱 진입점
│       ├── a2a/
│       │   ├── __init__.py
│       │   ├── protocol.py        # A2A 프로토콜 구현
│       │   ├── agent_card.py       # Agent Card 정의
│       │   └── task_handler.py     # Task 수신 및 처리
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── orchestrator.py     # 메인 오케스트레이션 로직
│       │   ├── classifier.py       # 분쟁 유형 분류기
│       │   ├── planner.py          # MCP 호출 계획 수립
│       │   └── responder.py        # 최종 응답 생성
│       ├── mcp_client/
│       │   ├── __init__.py
│       │   └── client.py           # MCP 클라이언트 (Streamable HTTP)
│       ├── llm/
│       │   ├── __init__.py
│       │   └── gateway.py          # LiteLLM 게이트웨이
│       ├── models/
│       │   ├── __init__.py
│       │   ├── dispute_types.py    # 분쟁 유형 Enum 및 매핑
│       │   └── schemas.py          # 요청/응답 스키마
│       ├── prompts/
│       │   ├── __init__.py
│       │   ├── system.py           # 시스템 프롬프트
│       │   ├── classifier.py       # 분류기 프롬프트
│       │   └── responder.py        # 응답 생성 프롬프트
│       └── config.py               # 환경 변수 및 설정
├── tests/
│   ├── test_orchestrator.py
│   ├── test_classifier.py
│   ├── test_planner.py
│   ├── test_responder.py
│   ├── test_a2a.py
│   └── conftest.py
└── scripts/
    └── test_e2e.py                 # E2E 시연 스크립트
```

---

## 2. 의존성

```toml
# pyproject.toml
[project]
name = "apt-legal-agent"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn>=0.30.0",
    "httpx>=0.27.0",
    "mcp>=1.0.0",
    "litellm>=1.40.0",
    "pydantic>=2.0",
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

### 3.1 app.py — FastAPI 앱 진입점

```python
"""
FastAPI 앱 메인 모듈.

엔드포인트:

1. GET /
   - Agent 기본 정보 반환
   - {"name": "apt-legal-agent", "version": "1.0.0", "status": "running"}

2. GET /healthz
   - 헬스체크
   - MCP 서버 연결 상태 확인 (mcp_client 연결 테스트)
   - LLM API 연결 상태 확인 (litellm 테스트 호출)

3. GET /.well-known/agent.json
   - A2A Agent Card 반환 (agent_card.py에서 생성)

4. POST /a2a
   - A2A 프로토콜 메시지 수신
   - task_handler.py로 위임

5. POST /a2a/stream
   - A2A 스트리밍 응답 (SSE)
   - task 처리 중간 상태를 실시간 전송

라이프사이클:
- startup: MCP 클라이언트 초기화 (서버 연결 확인, 사용 가능한 Tool 목록 캐싱)
- shutdown: MCP 클라이언트 정리, 진행 중 Task 완료 대기
"""
```

### 3.2 a2a/protocol.py — A2A 프로토콜 구현

```python
"""
A2A(Agent-to-Agent) 프로토콜 핵심 구현.

A2A 메시지 타입:

1. tasks/send — 새 Task 생성 또는 기존 Task에 메시지 추가
   Request:
   {
     "jsonrpc": "2.0",
     "method": "tasks/send",
     "params": {
       "id": "task-uuid",
       "message": {
         "role": "user",
         "parts": [{"type": "text", "text": "사용자 질문"}]
       }
     }
   }

   Response:
   {
     "jsonrpc": "2.0",
     "result": {
       "id": "task-uuid",
       "status": {"state": "completed"},
       "artifacts": [
         {
           "parts": [{"type": "text", "text": "Agent 응답"}]
         }
       ]
     }
   }

2. tasks/get — Task 상태 조회
3. tasks/cancel — Task 취소

Task 상태 머신:
  submitted → working → completed
                      → failed
                      → canceled

구현 요구사항:
- JSON-RPC 2.0 형식 준수
- Task ID는 UUID v4 생성
- Task 상태를 인메모리 dict로 관리
- 에러 시 JSON-RPC error 객체 반환 (code, message, data)
- 스트리밍: SSE(Server-Sent Events)로 중간 상태 전송
"""
```

### 3.3 a2a/agent_card.py — Agent Card

```python
"""
A2A Agent Card 정의.

GET /.well-known/agent.json으로 반환되는 Agent 메타데이터.

{
  "name": "apt-legal-agent",
  "description": "공동주택 법률 자문 AI Agent. 아파트 단지 내 분쟁, 재건축, 입찰 등에 대한 법령·판례 근거 기반 답변을 제공합니다.",
  "url": "{AGENT_BASE_URL}",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "stateTransitionHistory": false
  },
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"],
  "skills": [
    {
      "id": "legal_consultation",
      "name": "법률 상담",
      "description": "공동주택 관련 법률 질의에 대해 법령·판례 근거 기반 답변을 제공합니다. 층간소음, 주차, 재건축, 관리비 등 다양한 분쟁 유형을 지원합니다.",
      "inputModes": ["text"],
      "outputModes": ["text"],
      "examples": [
        "층간소음 기준이 몇 데시벨이야?",
        "윗집 층간소음 때문에 법적 대응하고 싶은데 어떻게 해야 해?",
        "재건축 추진하려면 동의율이 얼마나 필요해?"
      ]
    }
  ]
}

AGENT_BASE_URL은 환경변수에서 읽어 동적으로 설정.
"""
```

### 3.4 a2a/task_handler.py — Task 처리

```python
"""
A2A Task 수신 및 오케스트레이터 연결.

동작 플로우:

1. tasks/send 수신
2. Task 생성 (상태: submitted)
3. 사용자 메시지에서 텍스트 추출
4. Task 상태를 working으로 전환
5. orchestrator.process(user_text) 호출
6. 결과를 A2A artifact 형식으로 변환
7. Task 상태를 completed로 전환
8. 응답 반환

스트리밍 모드:
- orchestrator의 각 단계 완료 시 SSE 이벤트 발행
- 이벤트 타입: status_update (상태 변경), artifact_update (중간 결과)
- 최종 완료 시 task_complete 이벤트

에러 처리:
- orchestrator 예외 → Task 상태 failed + 에러 메시지
- 타임아웃 (60초) → Task 상태 failed + 타임아웃 메시지
"""
```

### 3.5 agent/orchestrator.py — 메인 오케스트레이션

```python
"""
Agent 오케스트레이션 메인 로직.

이 모듈이 Agent의 핵심이다.
사용자 질문을 받아 분류 → 계획 → 실행 → 응답 생성의 전체 파이프라인을 관리한다.

class Orchestrator:

    async def process(self, user_message: str) -> AgentResponse:
        '''
        메인 처리 파이프라인.

        Step 1: 질의 분석 (classifier)
          - LLM을 사용하여 사용자 질문을 분석
          - 출력: DisputeClassification
            - dispute_type: DisputeType enum
            - keywords: list[str] — 핵심 키워드
            - intent: QueryIntent enum (LAW_CHECK, PROCEDURE_GUIDE, DISPUTE_RESOLUTION, COMPARISON)
            - confidence: float (0.0~1.0)

        Step 2: 호출 계획 수립 (planner)
          - 분류 결과를 기반으로 MCP Tool 호출 계획 생성
          - 출력: ExecutionPlan
            - steps: list[ToolCallStep]
              - tool_name: str
              - arguments: dict
              - priority: int (1=필수, 2=보조, 3=선택)
              - depends_on: list[int] (선행 step 인덱스)

        Step 3: MCP 도구 실행 (mcp_client)
          - 계획에 따라 MCP Tool 호출
          - priority 1 도구들은 asyncio.gather로 병렬 실행
          - priority 2 도구들은 priority 1 결과를 참고하여 실행 여부 결정
          - priority 3 도구들은 결과 보강이 필요한 경우에만 실행
          - 출력: list[ToolCallResult]

        Step 4: 응답 생성 (responder)
          - 모든 Tool 결과를 종합
          - LLM을 사용하여 최종 사용자 응답 생성
          - 출력: AgentResponse
            - answer: str — 메인 답변
            - legal_basis: list[LegalBasisItem] — 법적 근거 목록
            - next_steps: list[str] — 후속 조치 안내
            - disclaimer: str — 면책 문구 (고정)

        에러 처리:
          - classifier 실패 → GENERAL 유형으로 폴백, 범용 법령 검색
          - MCP Tool 전체 실패 → LLM 지식 기반 응답 + "법령 DB 조회 불가" 경고
          - MCP Tool 부분 실패 → 성공한 결과만으로 응답 생성 + 실패 도구 명시
          - responder 실패 → 원시 Tool 결과를 포맷팅하여 반환
        '''
```

### 3.6 agent/classifier.py — 분쟁 유형 분류기

```python
"""
사용자 질문을 분쟁 유형으로 분류하는 모듈.

LLM structured output을 사용하여 분류 결과를 생성한다.

class DisputeClassifier:

    async def classify(self, user_message: str) -> DisputeClassification:
        '''
        사용자 메시지를 분석하여 분쟁 유형, 키워드, 질의 의도를 분류.

        LLM 호출:
          model: gpt-4o
          temperature: 0.0 (결정적 출력)
          response_format: JSON 강제

        프롬프트 (prompts/classifier.py에서 로드):
          시스템: "당신은 공동주택 법률 분쟁 분류 전문가입니다. 사용자의 질문을 분석하여
                   분쟁 유형, 핵심 키워드, 질의 의도를 JSON으로 반환합니다."

          사용자 메시지 + 분류 스키마:
          {
            "user_message": "{message}",
            "classify_into": {
              "dispute_type": "NOISE|PARKING|PET|MGMT_FEE|DEFECT|RECON|REMODEL|BID|ELECTION|GENERAL",
              "keywords": ["키워드1", "키워드2"],
              "intent": "LAW_CHECK|PROCEDURE_GUIDE|DISPUTE_RESOLUTION|COMPARISON",
              "confidence": 0.0~1.0
            }
          }

        폴백 전략:
          - LLM 응답 파싱 실패 → 키워드 기반 규칙 매칭으로 폴백
          - 규칙 매칭: 메시지에 "소음" 포함 → NOISE, "주차" 포함 → PARKING 등
          - 어디에도 매칭되지 않으면 GENERAL + confidence 0.3
        '''

키워드 기반 규칙 매핑 (폴백용):

KEYWORD_TO_TYPE = {
    "소음|층간|윗집|아랫집|시끄": "NOISE",
    "주차|차량|주차장|이중주차": "PARKING",
    "반려|개|고양이|강아지|펫": "PET",
    "관리비|부과|장기수선|충당금": "MGMT_FEE",
    "하자|누수|균열|결로|곰팡이": "DEFECT",
    "재건축|안전진단|정비구역|조합": "RECON",
    "리모델링|증축|수직증축": "REMODEL",
    "입찰|낙찰|계약|관리업체|용역": "BID",
    "선거|대표|입주자대표|동대표": "ELECTION",
}
"""
```

### 3.7 agent/planner.py — MCP 호출 계획 수립

```python
"""
분류 결과를 기반으로 MCP Tool 호출 계획을 생성하는 모듈.

class ToolCallPlanner:

    def create_plan(self, classification: DisputeClassification) -> ExecutionPlan:
        '''
        분쟁 유형별 기본 호출 세트와 질의 의도에 따른 추가 호출을 조합.

        분쟁 유형별 기본 호출 매핑:

        NOISE:
          P1: search_law(query="층간소음 {keywords}")
          P1: search_precedent(query="층간소음 {keywords}")
          P2: search_interpretation(query="층간소음 관리규약")

        PARKING:
          P1: search_law(query="주차 {keywords}")
          P1: search_precedent(query="주차 분쟁 {keywords}")

        PET:
          P1: search_law(query="반려동물 공동주택 {keywords}")
          P2: search_interpretation(query="반려동물 사육")

        MGMT_FEE:
          P1: search_law(query="관리비 {keywords}")
          P1: search_law(query="장기수선충당금") — keywords에 "장기수선" 포함 시
          P2: search_precedent(query="관리비 {keywords}")

        DEFECT:
          P1: search_law(query="하자보수 {keywords}")
          P1: search_precedent(query="하자보수 손해배상 {keywords}")

        RECON:
          P1: search_law(query="재건축 {keywords}")
          P2: search_law(query="도시정비법 {keywords}")

        REMODEL:
          P1: search_law(query="리모델링 {keywords}")
          P2: search_law(query="주택법 리모델링")

        BID:
          P1: search_law(query="입찰 관리업체 {keywords}")
          P2: search_interpretation(query="입찰 {keywords}")

        ELECTION:
          P1: search_law(query="입주자대표회의 선거 {keywords}")
          P2: search_interpretation(query="동별대표 선출")

        GENERAL:
          P1: search_law(query="{keywords 전체}")
          P2: search_precedent(query="{keywords 전체}")

        질의 의도별 추가 호출:

        LAW_CHECK (법령 확인):
          → P1 결과에서 가장 관련성 높은 조문에 대해 get_law_article 추가 (P2)

        PROCEDURE_GUIDE (절차 안내):
          → P1 결과에서 절차 관련 조문들에 대해 get_law_article 복수 호출 (P2)

        DISPUTE_RESOLUTION (분쟁 대응):
          → search_precedent을 P1으로 격상 (아직 없으면 추가)
          → P1 판례 결과에서 관련성 높은 건에 get_precedent_detail (P2)

        COMPARISON (비교):
          → compare_laws 호출 추가 (P1)

        ExecutionPlan 구조:
        {
          "steps": [
            {"index": 0, "tool_name": "search_law", "arguments": {...}, "priority": 1, "depends_on": []},
            {"index": 1, "tool_name": "search_precedent", "arguments": {...}, "priority": 1, "depends_on": []},
            {"index": 2, "tool_name": "get_law_article", "arguments": {...}, "priority": 2, "depends_on": [0]},
          ]
        }

        depends_on은 선행 step의 결과를 참조해야 하는 경우에 설정.
        예: get_law_article의 law_name은 search_law 결과에서 추출해야 함 → depends_on: [0]
        '''
```

### 3.8 agent/responder.py — 최종 응답 생성

```python
"""
MCP Tool 결과를 종합하여 사용자 친화적 응답을 생성하는 모듈.

class ResponseGenerator:

    async def generate(
        self,
        user_message: str,
        classification: DisputeClassification,
        tool_results: list[ToolCallResult]
    ) -> AgentResponse:
        '''
        LLM을 사용하여 최종 응답을 생성.

        LLM 호출:
          model: gpt-4o
          temperature: 0.1 (약간의 자연스러움)
          max_tokens: 2000

        프롬프트 구성 (prompts/responder.py에서 로드):

        시스템 프롬프트:
        """
        당신은 공동주택(아파트) 법률 자문 전문 AI입니다.
        아래의 법령 및 판례 조회 결과를 바탕으로 사용자의 질문에 답변합니다.

        답변 작성 규칙:
        1. 비전문가도 이해할 수 있는 쉬운 언어를 사용합니다.
        2. 법령 조문을 인용할 때는 "공동주택관리법 제20조에 따르면..." 형식으로 근거를 명시합니다.
        3. 판례를 언급할 때는 판결 요지를 1-2문장으로 요약합니다.
        4. 단계별 대응 방법이 있는 경우 순서대로 안내합니다.
        5. 확실하지 않은 내용은 추측하지 않고, 전문가 상담을 권장합니다.
        6. 답변 말미에 반드시 면책 문구를 포함합니다.

        면책 문구: "※ 본 답변은 일반적인 법률 정보 제공 목적이며, 구체적 사안에 대해서는 법률 전문가 상담을 권장합니다."

        응답 JSON 형식:
        {
          "answer": "메인 답변 텍스트",
          "legal_basis": [
            {"type": "law|precedent|interpretation", "reference": "법령/판례 번호", "summary": "요약"}
          ],
          "next_steps": ["후속 조치 1", "후속 조치 2"],
          "disclaimer": "면책 문구"
        }
        """

        사용자 메시지:
        """
        [사용자 질문]
        {user_message}

        [분쟁 유형]
        {classification.dispute_type}

        [법령 조회 결과]
        {tool_results에서 search_law/get_law_article 결과 포맷팅}

        [판례 검색 결과]
        {tool_results에서 search_precedent/get_precedent_detail 결과 포맷팅}

        [행정해석 검색 결과]
        {tool_results에서 search_interpretation 결과 포맷팅}

        위 자료를 바탕으로 사용자 질문에 답변해 주세요.
        """

        응답 파싱:
        - LLM 응답을 JSON으로 파싱
        - 파싱 실패 시: 응답 텍스트 전체를 answer로, 나머지 필드는 빈 값
        - legal_basis가 비어있으면 tool_results에서 자동 추출
        - disclaimer가 누락되면 기본 면책 문구 추가

        Tool 결과 포맷팅 유틸:
        - _format_law_results(results) → 법령명 + 조문번호 + 내용 요약
        - _format_precedent_results(results) → 사건번호 + 법원 + 판결요지
        - _format_interpretation_results(results) → 출처 + 질의요지 + 회답요지
        '''
```

### 3.9 mcp_client/client.py — MCP 클라이언트

```python
"""
Apt-Legal MCP 서버와 통신하는 MCP 클라이언트.

Streamable HTTP transport를 사용하여 MCP 서버에 연결한다.

class AptLegalMCPClient:

    def __init__(self, server_url: str):
        '''
        MCP 클라이언트 초기화.
        server_url: MCP 서버의 /mcp 엔드포인트 URL
        '''

    async def connect(self) -> None:
        '''
        MCP 서버에 연결하고 초기화.
        - initialize 핸드셰이크
        - 사용 가능한 Tool 목록 조회 및 캐싱
        - 사용 가능한 Resource 목록 조회 및 캐싱
        연결 실패 시 재시도 (최대 3회, 지수 백오프)
        '''

    async def call_tool(self, tool_name: str, arguments: dict) -> ToolCallResult:
        '''
        MCP Tool 호출.
        - tool_name과 arguments를 MCP CallToolRequest로 변환
        - 응답의 content를 파싱하여 ToolCallResult로 변환
        - TextContent의 text 필드를 JSON 파싱 시도
        - 파싱 실패 시 원시 텍스트로 반환

        타임아웃: 30초
        에러 처리: MCP 에러 응답을 ToolCallResult.error에 저장
        '''

    async def call_tools_parallel(self, calls: list[ToolCall]) -> list[ToolCallResult]:
        '''
        여러 Tool을 병렬로 호출.
        asyncio.gather 사용, return_exceptions=True로 개별 실패 허용.
        실패한 호출은 ToolCallResult.error에 예외 메시지 저장.
        '''

    async def read_resource(self, uri: str) -> str:
        '''
        MCP Resource 읽기.
        URI 패턴에 따라 리소스 데이터 반환.
        '''

    async def disconnect(self) -> None:
        '''
        MCP 연결 정리.
        '''

ToolCallResult:
  tool_name: str
  arguments: dict
  result: dict | str | None  — 파싱된 결과 (JSON → dict, 아니면 원시 str)
  error: str | None  — 에러 메시지 (정상이면 None)
  duration_ms: int  — 호출 소요 시간
"""
```

### 3.10 llm/gateway.py — LLM 게이트웨이

```python
"""
LiteLLM을 통한 LLM 호출 게이트웨이.

class LLMGateway:

    async def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        response_format: dict | None = None
    ) -> str:
        '''
        LLM 채팅 완성 호출.

        litellm.acompletion 사용:
          model: 환경변수 LLM_MODEL (기본값 "gpt-4o")
          messages: [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
          ]

        response_format이 주어지면 JSON 모드 강제:
          response_format={"type": "json_object"}

        에러 처리:
          - RateLimitError → 5초 대기 후 1회 재시도
          - AuthenticationError → 즉시 예외 전파
          - 기타 → 로깅 후 예외 전파

        반환: 응답 텍스트 (choices[0].message.content)
        '''

    async def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0
    ) -> dict:
        '''
        JSON 응답을 강제하는 LLM 호출.
        chat()을 response_format={"type": "json_object"}로 호출.
        응답 텍스트를 JSON 파싱하여 dict 반환.
        파싱 실패 시 ValueError 예외.
        '''
"""
```

### 3.11 models/dispute_types.py — 분쟁 유형 정의

```python
"""
분쟁 유형 Enum 및 관련 매핑 정의.

class DisputeType(str, Enum):
    NOISE = "NOISE"               # 층간소음
    PARKING = "PARKING"           # 주차 분쟁
    PET = "PET"                   # 반려동물
    MGMT_FEE = "MGMT_FEE"       # 관리비
    DEFECT = "DEFECT"             # 하자보수
    RECON = "RECON"               # 재건축
    REMODEL = "REMODEL"           # 리모델링
    BID = "BID"                   # 입찰/계약
    ELECTION = "ELECTION"         # 대표회의 선거
    GENERAL = "GENERAL"           # 기타

class QueryIntent(str, Enum):
    LAW_CHECK = "LAW_CHECK"                     # 법령 확인
    PROCEDURE_GUIDE = "PROCEDURE_GUIDE"         # 절차 안내
    DISPUTE_RESOLUTION = "DISPUTE_RESOLUTION"   # 분쟁 대응 방법
    COMPARISON = "COMPARISON"                   # 법령/사례 비교

DISPUTE_TYPE_DESCRIPTIONS: dict[DisputeType, str] = {
    DisputeType.NOISE: "층간소음, 생활소음 관련 분쟁",
    DisputeType.PARKING: "주차장 이용, 주차 분쟁",
    ...
}

PRIMARY_LAWS: dict[DisputeType, list[str]] = {
    DisputeType.NOISE: ["공동주택관리법 제20조", "민법 제217조"],
    DisputeType.PARKING: ["공동주택관리법 제35조"],
    ...
}
"""
```

---

## 4. 프롬프트 상세

### 4.1 prompts/system.py

```python
AGENT_SYSTEM_PROMPT = """
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
- 도구 호출 없이 기억에 의존한 법령 인용을 하지 않습니다
"""
```

### 4.2 prompts/classifier.py

```python
CLASSIFIER_SYSTEM_PROMPT = """
당신은 공동주택 법률 분쟁 분류 전문가입니다.
사용자의 질문을 분석하여 아래 JSON 형식으로 분류 결과를 반환합니다.
반드시 JSON만 반환하고, 다른 텍스트는 포함하지 마세요.

분쟁 유형:
- NOISE: 층간소음, 생활소음
- PARKING: 주차장 이용, 주차 분쟁
- PET: 반려동물 사육, 소음
- MGMT_FEE: 관리비 부과, 장기수선충당금
- DEFECT: 하자보수, 누수, 결로
- RECON: 재건축, 안전진단, 정비구역
- REMODEL: 리모델링, 증축
- BID: 입찰, 관리업체 선정, 용역 계약
- ELECTION: 입주자대표회의 선거, 동대표
- GENERAL: 위에 해당하지 않는 기타 법률 질의

질의 의도:
- LAW_CHECK: 특정 법령 조항 확인
- PROCEDURE_GUIDE: 절차나 단계 안내
- DISPUTE_RESOLUTION: 분쟁 대응 방법 문의
- COMPARISON: 법령이나 사례 비교

응답 형식:
{
  "dispute_type": "유형코드",
  "keywords": ["키워드1", "키워드2", ...],
  "intent": "의도코드",
  "confidence": 0.0~1.0
}
"""

CLASSIFIER_USER_TEMPLATE = """
사용자 질문: {user_message}

위 질문을 분류해 주세요.
"""
```

### 4.3 prompts/responder.py

```python
RESPONDER_SYSTEM_PROMPT = """
당신은 공동주택(아파트) 법률 자문 전문 AI입니다.
아래의 법령 및 판례 조회 결과를 바탕으로 사용자의 질문에 답변합니다.

답변 작성 규칙:
1. 비전문가도 이해할 수 있는 쉬운 언어를 사용합니다
2. 법령 조문을 인용할 때는 "공동주택관리법 제20조에 따르면..." 형식으로 근거를 명시합니다
3. 판례를 언급할 때는 판결 요지를 1-2문장으로 요약합니다
4. 단계별 대응 방법이 있는 경우 순서대로 안내합니다
5. 확실하지 않은 내용은 추측하지 않고, 전문가 상담을 권장합니다

응답 JSON 형식:
{
  "answer": "메인 답변 텍스트",
  "legal_basis": [
    {"type": "law", "reference": "공동주택관리법 제20조", "summary": "조문 요약"},
    {"type": "precedent", "reference": "2020다12345", "summary": "판결 요지"}
  ],
  "next_steps": ["후속 조치 1", "후속 조치 2"],
  "disclaimer": "※ 본 답변은 일반적인 법률 정보 제공 목적이며, 구체적 사안에 대해서는 법률 전문가 상담을 권장합니다."
}

반드시 위 JSON 형식으로만 응답하세요.
"""

RESPONDER_USER_TEMPLATE = """
[사용자 질문]
{user_message}

[분쟁 유형]
{dispute_type} ({dispute_description})

[법령 조회 결과]
{law_results}

[판례 검색 결과]
{precedent_results}

[행정해석 검색 결과]
{interpretation_results}

위 자료를 바탕으로 사용자 질문에 답변해 주세요.
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

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "apt_legal_agent.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 5.2 k8s/deployment.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: apt-legal-agent
  labels:
    app: apt-legal-agent
spec:
  replicas: 1
  selector:
    matchLabels:
      app: apt-legal-agent
  template:
    metadata:
      labels:
        app: apt-legal-agent
    spec:
      containers:
        - name: apt-legal-agent
          image: apt-legal-agent:1.0.0
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: apt-legal-config
            - secretRef:
                name: apt-legal-secrets
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: 1000m
              memory: 1Gi
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 10
```

### 5.3 k8s/service.yaml

```yaml
apiVersion: v1
kind: Service
metadata:
  name: apt-legal-agent-svc
spec:
  type: ClusterIP
  selector:
    app: apt-legal-agent
  ports:
    - port: 8000
      targetPort: 8000
      protocol: TCP
```

### 5.4 k8s/ingress.yaml

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: apt-legal-agent-ingress
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/healthcheck-path: /healthz
spec:
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: apt-legal-agent-svc
                port:
                  number: 8000
```

---

## 6. 테스트 요건

### 6.1 단위 테스트

| 테스트 대상 | 테스트 케이스 | 검증 항목 |
|-------------|-------------|-----------|
| classifier | 층간소음 질문 | NOISE 분류, confidence > 0.8 |
| classifier | 재건축 질문 | RECON 분류 |
| classifier | 모호한 질문 | GENERAL 폴백, confidence < 0.5 |
| classifier | LLM 실패 시 | 키워드 규칙 폴백 동작 |
| planner | NOISE + DISPUTE_RESOLUTION | search_law + search_precedent P1, search_interpretation P2 |
| planner | RECON + PROCEDURE_GUIDE | search_law P1, get_law_article P2 |
| planner | GENERAL | search_law + search_precedent P1 |
| responder | 법령 + 판례 결과 제공 | 답변에 법적 근거 포함, 면책 문구 포함 |
| responder | 빈 Tool 결과 | LLM 지식 기반 응답 + 경고 |
| responder | JSON 파싱 실패 | 원시 텍스트 폴백 |
| orchestrator | 정상 E2E | classify → plan → execute → respond 전체 플로우 |
| orchestrator | MCP 연결 실패 | 에러 메시지 포함 응답 |
| a2a | tasks/send | Task 생성, completed 상태, artifact 포함 |
| a2a | tasks/get | 존재하는 Task 상태 반환 |
| a2a | 잘못된 JSON-RPC | 에러 응답 반환 |

### 6.2 통합 테스트

| 테스트 시나리오 | 검증 항목 |
|----------------|-----------|
| Agent Card 조회 | GET /.well-known/agent.json → 유효한 Agent Card |
| A2A E2E | tasks/send → completed → artifact에 법률 답변 포함 |
| MCP 연동 E2E | Agent → MCP 서버 Tool 호출 → 결과 수신 확인 |
| 시연 시나리오 1 | 층간소음 기준 질문 → 법령 조문 포함 응답 |
| 시연 시나리오 2 | 법적 대응 질문 → 법령 + 판례 + 단계별 안내 |
| 시연 시나리오 3 | 재건축 동의율 질문 → 단계별 요건 정리 응답 |

### 6.3 테스트 실행

```bash
# 단위 테스트 (MCP/LLM Mock)
pytest tests/ -v -m "not integration"

# 통합 테스트 (실제 MCP 서버 + LLM 필요)
MCP_SERVER_URL=http://localhost:8001/mcp LLM_API_KEY=xxx pytest tests/ -v -m integration

# E2E 시연 스크립트
python scripts/test_e2e.py --scenario all
```

---

## 7. ChatGPT Enterprise 연동

### 7.1 CustomGPT 설정

ChatGPT Enterprise에서 CustomGPT를 생성하여 Agent에 연동한다.

```
GPT 이름: 아파트 법률 자문 AI
설명: 공동주택 관련 법률 질의에 법령·판례 근거 기반 답변을 제공합니다.

Instructions:
  이 GPT는 공동주택 법률 자문 Agent에 연결되어 있습니다.
  사용자의 법률 질문을 Agent에 전달하고 결과를 표시합니다.
  Agent가 반환하는 법적 근거(legal_basis)와 후속 조치(next_steps)를
  사용자가 이해하기 쉽게 정리하여 표시합니다.

Actions:
  A2A 프로토콜을 사용하여 Agent의 /a2a 엔드포인트에 연결.
  OpenAPI 스키마를 기반으로 tasks/send 호출.
```

### 7.2 OpenAPI 스키마 (Actions용)

```yaml
openapi: 3.1.0
info:
  title: Apt-Legal Agent A2A
  version: 1.0.0
servers:
  - url: https://{eks-endpoint}
paths:
  /a2a:
    post:
      operationId: sendTask
      summary: 법률 질의 처리
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                jsonrpc:
                  type: string
                  enum: ["2.0"]
                method:
                  type: string
                  enum: ["tasks/send"]
                params:
                  type: object
                  properties:
                    id:
                      type: string
                    message:
                      type: object
                      properties:
                        role:
                          type: string
                          enum: ["user"]
                        parts:
                          type: array
                          items:
                            type: object
                            properties:
                              type:
                                type: string
                                enum: ["text"]
                              text:
                                type: string
      responses:
        '200':
          description: Task 처리 결과
```

---

## 8. 구현 시 주의사항

1. **A2A 프로토콜 호환성**: ChatGPT Enterprise의 CustomGPT Actions가 A2A를 직접 지원하지 않을 수 있음. 이 경우 /a2a 엔드포인트를 일반 REST API로 래핑하는 어댑터 레이어 추가 필요

2. **LLM 호출 비용 관리**: 매 질의당 LLM 2회 호출 (classifier + responder). temperature를 낮게 유지하고, max_tokens를 적절히 제한

3. **MCP 클라이언트 연결 관리**: 서버 시작 시 MCP 연결, 연결 끊김 시 자동 재연결 로직 구현. 연결 실패 시에도 Agent가 제한적으로 동작할 수 있도록 (LLM 지식 기반 폴백)

4. **응답 시간 목표**: 전체 파이프라인 10초 이내. classifier 2초 + MCP 호출 4초 + responder 3초 + 오버헤드 1초. MCP 병렬 호출과 캐시를 적극 활용

5. **면책 문구**: 모든 법률 관련 응답에 반드시 면책 문구 포함. responder가 누락하더라도 orchestrator에서 강제 추가

6. **로깅**: 각 단계별 소요 시간, MCP Tool 호출 내역, LLM 토큰 사용량을 구조화된 로그로 출력. EKS 환경에서 CloudWatch로 수집 가능하도록 JSON 로그 포맷 사용

7. **Task 메모리 관리**: 인메모리 Task 저장소는 최대 1000개 유지, LRU 방식으로 오래된 Task 제거. 영구 저장이 필요하면 향후 Redis/DynamoDB 도입
