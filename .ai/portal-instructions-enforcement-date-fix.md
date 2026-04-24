# Web IDE 작업 지시서 — kor-legal-mcp `enforcement_date` propagate fix

**대상:** 포털 Web IDE 의 Claude Code (이 리포 단독 작업)
**관련 commit:** `3c606a4` (이미 VDI 에서 작성 + 로컬 commit 완료)
**선행 조건:** 사용자가 VDI 에서 GitHub 에 push 한 후 이 지시서 적용 (`git pull` 로 받기)
**상위 설계 문서:** `apt-legal-agent/docs/sufficiency_loop_design.md` §8 (외부 의존 — kor-legal-mcp P0 fix)

---

## 0. 한 줄 요약

`get_law_article` 응답의 `enforcement_date` / `last_amended` 가 항상 `None` 이던 P0 버그를 고친다. `search_law` 결과에도 같은 두 필드를 추가해 다운스트림 (`apt-legal-agent` sufficiency loop) 이 시행일자 기반 결정론 citation 검증을 활성화할 수 있게 한다.

---

## 1. 변경 내용 (commit `3c606a4` 안에 모두 포함됨)

### 코드 변경 4 파일
- `src/kor_legal_mcp/clients/law_api.py`
  - `Article` dataclass 에 optional `enforcement_date: str | None`, `last_amended: str | None` 추가.
  - `LawApiClient.get_article` 가 `_best_law_match` 의 hit 에서 두 필드를 article 에 inject (조문 단위 XML 이 시행일자를 일관되게 노출하지 않으므로 search hit 값을 사후 attach).
- `src/kor_legal_mcp/models/schemas.py`
  - `LawSearchResultItem` 에 두 optional 필드 추가.
- `src/kor_legal_mcp/tools/get_law_article.py`
  - 하드코딩 `enforcement_date=None / last_amended=None` 을 article 객체의 값으로 교체.
- `src/kor_legal_mcp/tools/search_law.py`
  - `LawSearchResultItem` 생성 3 위치 모두에서 `hit.enforcement_date` / `hit.last_amended` 전달.

### 테스트 추가 1 파일
- `tests/test_law_metadata.py` — 4 케이스
  1. `search_law_propagates_enforcement_date` — happy path
  2. `search_law_no_articles_path_carries_metadata` — fallback 경로도 메타 운반
  3. `get_law_article_returns_enforcement_date` — handler 가 article 값 사용
  4. `get_law_article_metadata_is_optional` — 날짜 없을 때 None 반환

---

## 2. Web IDE 에서 할 작업

### 2.1 코드 동기화
```bash
git pull --rebase
git log --oneline -3   # 3c606a4 가 보이는지 확인
```

### 2.2 테스트 재실행 (회귀 점검)
```bash
PYTHONPATH=src python -m pytest tests/ --tb=short
```
기대 결과: **25 passed**.

### 2.3 실제 API smoke (포털 환경에서만 가능 — VDI 에서는 OC 키 미발급으로 검증 불가)
```python
# Web IDE 에서 한 번 실행해 응답에 enforcement_date 가 들어오는지 확인
import asyncio
from kor_legal_mcp.clients.law_api import LawApiClient

async def check():
    async with LawApiClient() as api:
        article = await api.get_article("공동주택관리법", "제65조")
        print(f"enforcement_date={article.enforcement_date}")
        print(f"last_amended={article.last_amended}")

asyncio.run(check())
```
기대 결과: 두 값 모두 `None` 이 아닌 실제 날짜 (예: `"20240217"`). `None` 이면 law.go.kr 응답에 `시행일자` 가 빠진 것이므로 본 fix 와 무관 (그 법령의 데이터 자체 누락).

### 2.4 포털 배포
기존 패턴 그대로 (이 리포는 FastMCP + Starlette streamable HTTP). 별도 설정 변경 없음.

---

## 3. 영향 범위 (호환성)

- **응답 schema 는 additive 변경**: 기존 호출자가 두 필드를 무시하면 동작 동일. 추가만 했고 제거/변경 없음.
- **캐시 무효화 필요**: `get_law_article` / `search_law` 의 캐시 키에 변경 없음. 이미 캐시된 응답에는 새 필드가 없을 수 있음 (cache TTL 만료까지). 즉시 활성화하려면 Web IDE 에서 캐시 strip 또는 재시작.
- **다운스트림 효과**: apt-legal-agent 가 0.1.8 + sufficiency loop 배포되면, 답변 citation 의 `effective_date` 가 채워져 결정론 게이트가 시행일자 검증을 수행. 이 fix 없이는 그 검증이 항상 `None` 으로 무력화.

---

## 4. 알려진 비-변경

- **MST (법령일련번호)** 는 응답에 노출하지 않음. Track B P1 항목이지만 본 fix 범위 외 — 별도 PR 후보.
- **개정이력 (`amendment_history`)** 도 별도 — 현재 모든 `GetLawArticleOutput.amendment_history` 는 `None`.

---

## 5. 검토 요청 시 확인 사항

- 캐시 직격타: 이전 응답이 캐시된 상태에서 새 호출이 와도 새 필드가 없으면 sufficiency loop 가 LOW 로 떨어질 수 있음. 배포 직후 캐시 워밍업 (`/health` 또는 `warmup` 호출) 권장.
- `LawSearchHit.enforcement_date` 가 law.go.kr 응답에 누락된 경우, `Article.enforcement_date` 도 `None` 이 됨 — 이 동작은 의도된 것 (옵셔널 필드).
