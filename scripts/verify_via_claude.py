"""End-to-end test: Claude API → deployed kor-legal-mcp.

Drives the deployed MCP server through Claude using the MCP connector
(`mcp_servers` parameter on messages.create). For each prompt:
  - prints which tools Claude called and with what input
  - prints each tool result preview
  - prints Claude's final text answer
  - reports overall PASS/FAIL based on whether tool calls succeeded

Requires:
  ANTHROPIC_API_KEY  — in .env or environment
  MCP_URL            — deployed MCP endpoint, defaults to the value below

Run:
  ./.venv/Scripts/python.exe scripts/verify_via_claude.py
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

import anthropic  # noqa: E402
import httpx  # noqa: E402

MCP_URL = os.getenv(
    "MCP_URL",
    "https://portal-serving-mcp-661b67eeaf0d.samsungsdscoe.com/mcp",
)
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

PROMPTS: list[tuple[str, str]] = [
    (
        "single-tool: search_law",
        "한국 법령 중 '층간소음'과 관련된 조문을 3건 찾아서 법령명과 조문번호만 알려줘.",
    ),
    (
        "single-tool: get_law_article",
        "공동주택관리법 제20조의 전문을 그대로 가져와서 보여줘.",
    ),
    (
        "chain: search_precedent → get_precedent_detail",
        "공동주택 입주자대표회의가 주택관리업자를 선정하는 입찰 절차를 위반한 사례에 "
        "대한 대법원 판례를 한 건 찾아서, 사건번호와 판결의 핵심 요지를 정리해줘.",
    ),
    (
        "complex: 종합 자문",
        "우리 단지에 층간소음 분쟁이 있어. 관련 법령 조문 한 두 개와 최근 판례 두 건을 "
        "찾아서 각각 핵심만 요약해주고 출처(법령명/조문번호, 사건번호/법원)를 명시해줘.",
    ),
]


def _short(text: str, limit: int = 300) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def run_prompt(client: anthropic.Anthropic, label: str, prompt: str) -> bool:
    print(f"\n{'=' * 70}\n[{label}]\n{'=' * 70}")
    print(f"Q: {prompt}\n")

    try:
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
            mcp_servers=[
                {
                    "type": "url",
                    "url": MCP_URL,
                    "name": "kor-legal-mcp",
                }
            ],
            betas=["mcp-client-2025-04-04"],
        )
    except Exception as exc:
        print(f"REQUEST FAILED [{type(exc).__name__}]: {exc!r}")
        return False

    tool_calls = 0
    tool_errors = 0
    final_text_parts: list[str] = []

    for block in resp.content:
        btype = getattr(block, "type", "?")
        if btype == "mcp_tool_use":
            tool_calls += 1
            name = getattr(block, "name", "?")
            input_data = getattr(block, "input", {})
            print(f"  → tool_use   {name}({_short(str(input_data), 200)})")
        elif btype == "mcp_tool_result":
            is_error = getattr(block, "is_error", False)
            if is_error:
                tool_errors += 1
            content = getattr(block, "content", [])
            preview = ""
            if content and hasattr(content[0], "text"):
                preview = _short(content[0].text, 250)
            marker = "ERR " if is_error else "OK  "
            print(f"  ← tool_result {marker}{preview}")
        elif btype == "text":
            final_text_parts.append(getattr(block, "text", ""))

    final_text = "\n".join(final_text_parts).strip()
    print(f"\nA: {_short(final_text, 600)}")

    ok = tool_calls > 0 and tool_errors == 0
    print(
        f"\nResult: {'PASS' if ok else 'FAIL'} "
        f"(tool_calls={tool_calls}, tool_errors={tool_errors})"
    )
    return ok


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set (add it to .env)")
        sys.exit(1)
    print(f"MCP_URL = {MCP_URL}")
    print(f"MODEL   = {MODEL}")

    # Honor corporate proxy explicitly. Anthropic's bundled httpx client
    # ignores env-based proxy settings on this VDI for some reason. Also
    # disable SSL verification because the corporate proxy performs TLS
    # interception with its own (non-public) CA — the system trust store
    # doesn't have it, so verification would fail.
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy:
        import warnings
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        http_client = httpx.Client(proxy=proxy, verify=False, timeout=120.0)
    else:
        http_client = None
    client = anthropic.Anthropic(api_key=api_key, http_client=http_client)

    results = []
    for label, prompt in PROMPTS:
        results.append((label, run_prompt(client, label, prompt)))

    print(f"\n{'=' * 70}\nSUMMARY\n{'=' * 70}")
    for label, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")

    failed = sum(1 for _, ok in results if not ok)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
