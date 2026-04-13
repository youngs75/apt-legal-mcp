"""로컬 stdio 모드 실행 스크립트.

사용:
    python scripts/run_stdio.py
"""
from __future__ import annotations

from apt_legal_mcp.server import _MCP


def main() -> None:
    _MCP.run()


if __name__ == "__main__":
    main()
