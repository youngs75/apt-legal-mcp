# Repository Guidelines

## 프로젝트 개요
`kor-legal-mcp` — 한국 법령·판례·행정해석을 조회하는 **범용 MCP(Model Context Protocol) 서버**.
국가법령정보센터(law.go.kr) Open API를 1차 데이터 소스로 사용하며, 도메인에 종속되지 않은 6개 Tool을 제공한다.
도메인 특화 자산(예: 공동주택 운영규약, 지자체 조례)은 별도 MCP 서버(`apt-domain-mcp` 등)와 상위 Vertical AI Agent에서 조합한다.

## 파이프라인 내 위치
```
ChatGPT Enterprise CustomGPT
       ↓ (A2A)
Vertical AI Agent (예: apt-legal-agent)
       ↓ (MCP Streamable HTTP)
   ┌───┴────────────────────────┐
   ↓                            ↓
kor-legal-mcp  ← 본 리포      apt-domain-mcp (별도 리포, 예정)
   ↓                            ↓
law.go.kr Open API         Milvus + PostgreSQL (RAG)
```

본 리포의 개발 범위는 **법령/판례/행정해석 범용 조회**에 한정된다.
도메인 RAG, 운영규약, 조례 등은 본 서버의 책임이 아니다.

## 리포지토리 구조
```
kor-legal-mcp/
├── AGENTS.md                        # 이 파일
├── Dockerfile                       # uv 기반 멀티스테이지 빌드
├── pyproject.toml / uv.lock
├── src/kor_legal_mcp/
│   ├── server.py                    # FastMCP + Starlette app
│   ├── config.py                    # Settings (env)
│   ├── cache/memory_cache.py        # TTL 인메모리 캐시
│   ├── clients/
│   │   ├── law_api.py               # law.go.kr 비동기 클라이언트
│   │   └── article_number.py        # 조문번호 정규화
│   ├── models/schemas.py            # Pydantic v2 IO 스키마
│   ├── tools/                       # 6개 MCP Tool
│   ├── prompts/definitions.py       # (도메인 무관 템플릿만)
│   └── resources/                   # Resource handler
├── tests/
├── scripts/
│   ├── run_stdio.py                 # stdio 모드 실행
│   └── verify_law_api.py            # OC 인증/필드 검증 스크립트
└── docs/                            # 기획/스펙 문서
```

## 커뮤니케이션 규칙
- 사용자와의 모든 소통은 한국어로 진행한다.
- 코드 주석은 영어를 기본으로 하되, 사용자 facing 메시지(에러·안내·도구 응답)는 한국어를 사용한다.
- MCP Tool의 JSON 응답은 `ensure_ascii=False`로 한국어 원문을 유지한다.

## Memory Sync

사용자는 여러 머신(사내 VDI + 집 WSL2)에서 이 리포를 작업하므로, Claude의 장기 기억은 **별도 private GitHub repo**(`~/.claude/global-memory/`, GitHub: `youngs75/claude-global-memory`)로 동기화됩니다. 마스터 규칙은 `~/.claude/CLAUDE.md`에 있습니다.

- **본 프로젝트가 참조할 글로벌 메모리 파일:**
  - `~/.claude/global-memory/apt-family.md` — 3-repo 구조·문서 허브·합성 데이터 원칙
  - `~/.claude/global-memory/portal-infra.md` — VDI egress 제한, 포털 수동 배포, endpoint 등록, LiteLLM Bedrock `json_object` 미지원, Web IDE 위임 패턴
- **세션 시작 시:** 위 파일들을 읽고(필요 시 `cd ~/.claude/global-memory && git pull --rebase -q` 선행) 적용
- **장기 기억 승격:** 프로젝트 로컬 auto memory(`~/.claude/projects/.../memory/`)는 scratch로만 사용. 다른 머신에서도 필요한 것, 프로젝트 철학·방향·경계, 여러 세션 재사용 교훈은 즉시 위 파일들 중 맞는 곳으로 승격
- **세션 종료 또는 `sync memory` 지시 시:** `cd ~/.claude/global-memory && git add -A && git commit -m "..." && git push`
- **금지:** 프로젝트 로컬 auto memory에만 중요한 장기 기억을 남기지 말 것 — 다른 머신에서 유실됩니다

## 세션 파일 명명 규칙
세션 기록은 `.ai/sessions/session-YYYY-MM-DD-NNNN.md` 형식을 사용한다.

- `YYYY-MM-DD`: 세션 당일 날짜
- `NNNN`: 같은 날짜 내 순번 (`0001`부터 시작)
- 같은 날짜 파일이 있으면 가장 큰 번호에 `+1`을 적용한다.

## Resume 규칙
사용자가 `resume` 또는 `이어서`라고 요청하면 가장 최근 세션 파일을 찾아 이어서 작업한다.

- `.ai/sessions/`에서 명명 규칙에 맞는 파일만 후보로 본다.
- 가장 최신 날짜를 우선, 같은 날짜면 가장 큰 순번을 선택한다.
- 선택한 세션 파일은 전체를 읽고, 사용자에게 이전 작업 내용과 다음 할 일을 한국어로 간단히 브리핑한다.

## Handoff 규칙
새 세션 파일은 사용자가 명시적으로 종료를 요청한 경우에만 생성한다.
허용 트리거 예: `handoff`, `정리해줘`, `세션 저장`, `종료하자`, `세션 종료`.

- 저장 위치는 항상 `.ai/sessions/`.
- 기존 `session-*.md` 파일은 절대 수정하지 않는다.
- 자동/단계별 저장은 하지 않는다.
- 새 파일에는 프로젝트 개요, 최근 작업 내역, 현재 상태, 다음 단계, 중요 참고사항을 포함한다.

## 제공 MCP Tools (15종)
| Tool | 용도 | law.go.kr target |
|------|------|------|
| `search_law` | 키워드 기반 법령 조문 검색 | `law` |
| `get_law_article` | 특정 조문 전문 조회 | `law` |
| `search_precedent` | 판례 검색 (본문검색, `search=2`) | `prec` |
| `get_precedent_detail` | 판례 상세 조회 | `prec` |
| `compare_laws` | 복수 조문 비교 조회 | `law` |
| `search_interpretation` | 법령해석례(법제처·부처 유권해석) 검색 | `expc` |
| `get_interpretation_detail` | 법령해석례 상세(질의요지·회답·이유) | `expc` |
| `search_constitutional_decision` | 헌법재판소 결정례 검색 | `detc` |
| `get_constitutional_decision_detail` | 헌재 결정례 상세(판시사항·결정요지·전문) | `detc` |
| `search_admrule` | 행정규칙(훈령·예규·고시) 검색 | `admrul` |
| `get_admrule_detail` | 행정규칙 상세(조문 전체) | `admrul` |
| `search_ordinance` | 자치법규(조례·규칙) 검색 — `region` 필터 지원 | `ordin` |
| `get_ordinance_detail` | 자치법규 상세(조문 전체) | `ordin` |
| `search_treaty` | 조약(양자·다자) 검색 | `trty` |
| `get_treaty_detail` | 조약 상세(조약문 본문 포함) | `trty` |

> `search_ordinance`의 `region` 파라미터는 **일반 조회**용 지자체명 부분 일치 필터일 뿐이며, 특정 단지/지역 RAG는 여전히 `apt-domain-mcp`의 책임 영역이다.

세부 입출력 스키마·에러 코드·캐싱 전략은 `docs/02_mcp_server_codex_spec.md` 참조.
(문서의 옛 명칭 `apt-legal-mcp`는 점진적으로 교체 예정)

## Resources / Prompts
- Resource URI:
  - `kor-legal://law/{law_name}/article/{article_number}`
  - `kor-legal://precedent/{case_number}`
- Prompts: 도메인 무관 템플릿만 본 리포에 둔다. 도메인 특화 프롬프트는 상위 Vertical Agent에서 관리한다.

## 기술 스택
- **언어**: Python 3.12+
- **MCP**: `mcp` Python SDK + Starlette Streamable HTTP transport
- **HTTP 클라이언트**: `httpx` (비동기)
- **XML 파싱**: `lxml` (EUC-KR/UTF-8 혼용 응답 대응)
- **스키마**: Pydantic v2
- **캐시**: TTL 기반 인메모리 (법령 메타 24h, 조문 전문 7d)
- **패키지 매니저**: `uv` (lockfile 기반)
- **배포**: Docker → AWS EKS (Samsung SDS CoE 포털)
- **테스트**: pytest, pytest-asyncio, pytest-httpx

### 포털 환경에서 활용 가능한 인프라
Samsung SDS CoE 포털은 **PostgreSQL** 및 **Milvus(Vector DB)**를 별도 서비스로 제공한다.
본 서버 자체는 인메모리 캐시만 사용하지만, 다음 확장에 활용을 염두에 둔다:
- **PostgreSQL**: L2 영속 캐시 (Pod 재시작 후에도 law.go.kr 응답 재활용), 인제스트 메타 저장소
- **Milvus**: 법령 조문 임베딩 → 의미 기반 검색, 판례 유사 사례 RAG
- 도메인 특화 RAG 서버(`apt-domain-mcp`)도 동일하게 PostgreSQL + Milvus를 사용해 단지 운영규약·지자체 조례를 처리한다.

## 개발 및 검증 규칙

### 로컬 개발 (Windows VDI / PowerShell)
```powershell
# 설치
uv sync --extra dev      # 또는: python -m venv .venv ; .\.venv\Scripts\pip install -e ".[dev]"

# stdio 모드
.\.venv\Scripts\python scripts\run_stdio.py

# Streamable HTTP 서버
.\.venv\Scripts\python -m uvicorn kor_legal_mcp.server:app --host 0.0.0.0 --port 8001

# OC 인증/필드 검증
.\.venv\Scripts\python scripts\verify_law_api.py
```

### 테스트
```powershell
.\.venv\Scripts\pytest tests\ -v -m "not integration"
$env:LAW_API_KEY="..."; .\.venv\Scripts\pytest tests\ -v -m integration
```

### Docker / k8s
로컬 VDI는 WSL2 미지원으로 Docker 실행 불가. **포털 Web IDE에서 빌드/배포**한다.
```bash
docker build -t kor-legal-mcp:1.0.0 .
```

## 환경 변수
```bash
LAW_API_KEY=               # law.go.kr OC 값 (가입 ID, 예: apt-legal-agent)
LAW_API_SEARCH_URL=http://www.law.go.kr/DRF/lawSearch.do
LAW_API_SERVICE_URL=http://www.law.go.kr/DRF/lawService.do
CACHE_TTL_HOURS=24
CACHE_MAX_ITEMS=1000
SERVER_PORT=8001
LAW_API_TIMEOUT_SECONDS=15
LAW_API_MAX_CONCURRENCY=5
```

> **OC 값 안내**: law.go.kr Open API는 별도 토큰 발급 없이 가입 시 등록한 ID(또는 이메일 ID 부분)를 `OC` 파라미터로 사용한다. 본 프로젝트는 `apt-legal-agent`로 등록되어 있다.

## 구현 시 유의사항
- **검색 vs 상세 엔드포인트 분리**: `lawSearch.do`(검색) / `lawService.do`(상세). 두 URL을 환경변수로 분리 관리.
- **판례 본문검색**: `search_precedents`는 `search=2`(본문검색)를 항상 포함한다. 기본값(`section=evtNm`, 사건명만)은 누락이 많다.
- **법령 API 인코딩**: 응답은 대부분 UTF-8이지만 EUC-KR 폴백을 유지한다.
- **조문번호 정규화**: `"제20조"`, `"20조"`, `"제20조의2"`, `"20-2"` 등 다양한 입력을 통일 포맷으로.
- **자체 relevance 스코어링**: 법령 API는 관련도를 제공하지 않으므로 키워드 매칭 비율로 자체 산정.
- **동시 호출 제한**: `asyncio.Semaphore`로 법령 API 병렬 호출 최대 5개.
- **캐시 키**: Tool 이름을 프리픽스에 포함해 충돌 방지 (`search_law:sha256(...)`).
- **에러 전파**: 내부 예외는 로깅만, 사용자에게는 MCP 에러 코드(`INVALID_PARAMS`, `INTERNAL_ERROR`)로 정제된 메시지 반환.
- **면책 범위**: 본 서버는 법률 정보 조회 도구만 제공한다. 법률 자문성 문장 생성은 상위 Agent 책임이며, Tool 응답에는 원문/요약만 담는다.
- **도메인 비종속**: 본 서버에 특정 도메인(공동주택 등)에 한정된 키워드/리소스/프롬프트를 추가하지 않는다. 그런 자산이 필요하면 상위 Agent 또는 별도 MCP 서버에 둔다.

## 커밋 규칙
Conventional Commits 사용: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
`.env`, `*.db`, `data/precedents.db`, `.claude/`, `.ai/sessions/` 등 런타임 산출물은 커밋하지 않는다.
