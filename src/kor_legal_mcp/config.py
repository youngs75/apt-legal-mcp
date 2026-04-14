from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    law_api_key: str
    law_api_search_url: str
    law_api_service_url: str
    cache_ttl_hours: int
    cache_max_items: int
    server_port: int
    law_api_timeout_seconds: float
    law_api_max_concurrency: int

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            law_api_key=os.getenv("LAW_API_KEY", ""),
            law_api_search_url=os.getenv(
                "LAW_API_SEARCH_URL", "http://www.law.go.kr/DRF/lawSearch.do"
            ),
            law_api_service_url=os.getenv(
                "LAW_API_SERVICE_URL", "http://www.law.go.kr/DRF/lawService.do"
            ),
            cache_ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "24")),
            cache_max_items=int(os.getenv("CACHE_MAX_ITEMS", "1000")),
            server_port=int(os.getenv("SERVER_PORT", "8001")),
            law_api_timeout_seconds=float(os.getenv("LAW_API_TIMEOUT_SECONDS", "15")),
            law_api_max_concurrency=int(os.getenv("LAW_API_MAX_CONCURRENCY", "5")),
        )


settings = Settings.from_env()
