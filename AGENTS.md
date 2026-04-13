# Repository Guidelines

## 프로젝트 개요
`apt-legal-mcp` — 한국 공동주택 법률 자문 Vertical AI Agent(A2A 지원)가 호출하는 MCP(Model Context Protocol) 서버.
국가법령정보센터 Open API와 사전 수집된 판례 DB를 기반으로 법령 조문, 판례, 행정해석 조회 도구를 제공하며,
ChatGPT Enterprise CustomGPT → Legal Vertical Agent → 본 MCP 서버의 파이프라인에서 하위 데이터 레이어 역할을 한다.

## 리포지토리 구조

```
apt-legal-mcp/
├── AGENTS.md                        # 이 파일 — AI/기여자 작업 규칙
├── docs/                            # 기획 및 작업지시 문서
│   ├── 01_implementation_plan.md    # 전체 구현 계획서
│   ├── 02_mcp_server_codex_spec.md  # MCP 서버 작업지시서 (본 리포 범위)
│   └── 03_vertical_agent_codex_spec.md  # Vertical Agent 작업지시서 (참고용, 별도 리포)
└── (구현 예정) src/apt_legal_mcp/, data/, tests/, k8s/, Dockerfile, pyproject.toml
```

기준 문서는 항상 `AGENTS.md`이며, 세부 스펙은 `docs/` 하위 문서를 참조한다.
본 리포의 개발 범위는 **MCP 서버(`apt-legal-mcp`)에 한정**되며, Vertical Agent는 별도 리포에서 관리된다.

## 커뮤니케이션 규칙
- 사용자와의 모든 소통은 한국어로 진행한다.
- 코드 주석은 영어를 기본으로 하되, 사용자 facing 메시지(에러·안내·도구 응답)는 한국어를 사용한다.
- MCP Tool의 JSON 응답은 `ensure_ascii=False`로 한국어를 그대로 유지한다.

## 세션 파일 명명 규칙
세션 기록은 `.ai/sessions/session-YYYY-MM-DD-NNNN.md` 형식을 사용한다.

- `YYYY-MM-DD`: 세션 당일 날짜
- `NNNN`: 같은 날짜 내 순번 (`0001`부터 시작)
- 같은 날짜 파일이 있으면 가장 큰 번호에 `+1`을 적용한다.

## Resume 규칙
사용자가 `resume` 또는 `이어서`라고 요청하면 가장 최근 세션 파일을 찾아 이어서 작업한다.

- `.ai/sessions/`에서 명명 규칙에 맞는 파일만 후보로 본다.
- 가장 최신 날짜를 우선, 같은 날짜면 가장 큰 순번을 선택한다.
- 초기 컨텍스트에 파일이 없어 보여도 실제 파일 시스템을 다시 확인한다.
- 샌드박스 제한으로 조회/읽기가 실패하면 `.ai/sessions/` 확인과 대상 파일 읽기에 필요한 최소 범위에서 권한 상승을 요청한 뒤 즉시 재시도한다.
- 선택한 세션 파일은 전체를 읽고, 사용자에게 이전 작업 내용과 다음 할 일을 한국어로 간단히 브리핑한다.

## Handoff 규칙
새 세션 파일은 사용자가 명시적으로 종료를 요청한 경우에만 생성한다. 허용 트리거 예: `handoff`, `정리해줘`, `세션 저장`, `종료하자`, `세션 종료`.

- 저장 위치는 항상 `.ai/sessions/`.
- 기존 `session-*.md` 파일은 절대 수정하지 않는다.
- 자동 저장이나 단계별 저장은 하지 않는다.
- 새 파일에는 프로젝트 개요, 최근 작업 내역, 현재 상태, 다음 단계, 중요 참고사항을 포함한다.
- 저장 후 사용자에게 생성된 파일 경로를 알린다.

## 디렉토리별 AGENTS.md 관리 원칙
주요 디렉토리(`src/apt_legal_mcp/tools/`, `clients/`, `data/`, `k8s/` 등)에는 `AGENTS.md`를 유지해 구조를 빠르게 파악하도록 돕는다.

### 필수 포함 섹션
- **Purpose** — 이 디렉토리가 무엇을 하는지 1-2문장
- **Key Files** — 주요 파일과 역할 (테이블)
- **For AI Agents** — 이 디렉토리에서 작업할 때 알아야 할 규칙/패턴

### 관리 규칙
- 새 디렉토리를 만들면 `AGENTS.md`도 함께 생성한다.
- `<!-- Parent: ../AGENTS.md -->` 주석으로 상위 문서를 참조한다.

## 핵심 아키텍처

### 파이프라인 내 위치
```
ChatGPT Enterprise CustomGPT
   ↓ (A2A)
Legal Vertical Agent (별도 리포)
   ↓ (MCP Streamable HTTP)
apt-legal-mcp  ← 본 리포
   ↓ (REST)
국가법령정보센터 Open API, 판례 DB(SQLite FTS5)
```

### 제공 MCP Tools (6종)
| Tool | 용도 |
|------|------|
| `search_law` | 키워드 기반 법령 조문 검색 |
| `get_law_article` | 특정 조문 전문 조회 |
| `search_precedent` | 판례 검색 (FTS5) |
| `get_precedent_detail` | 판례 상세 조회 |
| `search_interpretation` | 행정해석·유권해석 검색 |
| `compare_laws` | 복수 조문 비교 조회 |

세부 입출력 스키마·에러 코드·캐싱 전략은 `docs/02_mcp_server_codex_spec.md` 참조.

### Resources / Prompts
- Resource URI: `apt-legal://law/{law_name}/article/{article_number}`, `apt-legal://precedent/{case_number}`, `apt-legal://guide/dispute-types`
- Prompts: `dispute_resolution`, `reconstruction_checklist`, `bid_compliance_check`, `management_fee_review`

## 기술 스택
- **언어**: Python 3.12+
- **MCP**: `mcp` Python SDK + Starlette Streamable HTTP transport
- **HTTP 클라이언트**: `httpx` (국가법령정보센터 API, 비동기)
- **XML 파싱**: `lxml` (EUC-KR/UTF-8 혼용 응답 대응)
- **데이터**: SQLite + FTS5 (`aiosqlite`) — 판례 전문 검색
- **스키마**: Pydantic v2
- **캐시**: TTL 기반 인메모리 (법령 메타 24h, 조문 전문 7d)
- **배포**: Docker → AWS EKS
- **테스트**: pytest, pytest-asyncio, pytest-httpx

## 개발 및 검증 규칙

### 로컬 개발
```bash
# 설치 (구현 후)
pip install -e ".[dev]"

# stdio 모드 실행 (로컬 MCP 클라이언트 연동용)
python scripts/run_stdio.py

# Streamable HTTP 서버 실행
uvicorn apt_legal_mcp.server:app --host 0.0.0.0 --port 8001
```

### 판례 DB 시드
```bash
python data/seed_precedents.py
```

### 테스트
```bash
# 단위 테스트 (외부 API Mock)
pytest tests/ -v -m "not integration"

# 통합 테스트 (실제 법령 API 호출)
LAW_API_KEY=xxx pytest tests/ -v -m integration
```

### Docker / k8s
```bash
docker build -t apt-legal-mcp:1.0.0 .
kubectl apply -f k8s/
```

## 환경 변수
```bash
LAW_API_KEY=              # 국가법령정보센터 API 키 (필수)
LAW_API_BASE_URL=http://www.law.go.kr/DRF/lawService.do
PRECEDENT_DB_PATH=/data/precedents.db
CACHE_TTL_HOURS=24
SERVER_PORT=8001
```

## 구현 시 유의사항 (요약)
- **법령 API 인코딩**: EUC-KR/UTF-8 혼용 → 응답 헤더 확인 후 폴백 디코딩.
- **조문번호 정규화**: `"제20조"`, `"20조"`, `"제20조의2"`, `"20-2"` 등 다양한 입력을 통일 포맷으로.
- **자체 relevance 스코어링**: 법령 API는 관련도를 제공하지 않으므로 키워드 매칭 비율로 자체 산정.
- **동시 호출 제한**: `asyncio.Semaphore`로 법령 API 병렬 호출 최대 5개.
- **캐시 키**: Tool 이름을 프리픽스에 포함해 충돌 방지 (`search_law:sha256(...)`).
- **에러 전파**: 내부 예외는 로깅만, 사용자에게는 MCP 에러 코드(`INVALID_PARAMS`, `INTERNAL_ERROR`)로 정제된 메시지 반환.
- **면책 범위**: 본 서버는 법률 정보 조회 도구만 제공한다. 법률 자문성 문장 생성은 상위 Agent 책임이며, Tool 응답에는 원문/요약만 담는다.

## 커밋 규칙
Conventional Commits 사용: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
`.env`, `*.db`, `data/precedents.db`, `.claude/`, `.ai/sessions/` 런타임 산출물은 커밋하지 않는다.
