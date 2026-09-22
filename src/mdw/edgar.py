"""A small, polite SEC EDGAR client.

EDGAR's published fair-access policy allows 10 requests/second and requires a
descriptive User-Agent. This client enforces both, retries transient failures
with backoff, and knows nothing about DuckDB: it returns parsed JSON and lets
``ingest`` decide what to do with it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class EdgarError(RuntimeError):
    """Raised when EDGAR returns an unrecoverable response."""


class RateLimiter:
    """Minimum spacing between calls. Simple and sufficient for a sequential loader."""

    def __init__(self, max_per_second: float, clock=time.monotonic, sleep=time.sleep):
        if max_per_second <= 0:
            raise ValueError("max_per_second must be positive")
        self._interval = 1.0 / max_per_second
        self._clock = clock
        self._sleep = sleep
        self._next_allowed = 0.0

    def wait(self) -> None:
        now = self._clock()
        if now < self._next_allowed:
            self._sleep(self._next_allowed - now)
            now = self._next_allowed
        self._next_allowed = now + self._interval


@dataclass
class EdgarClient:
    user_agent: str
    max_per_second: float = 5.0  # half of SEC's ceiling; there is no prize for being fast
    timeout: float = 60.0
    max_attempts: int = 4
    session: requests.Session = field(default_factory=requests.Session)
    sleep: Callable[[float], None] = time.sleep

    def __post_init__(self) -> None:
        self._limiter = RateLimiter(self.max_per_second)
        self.session.headers.update(
            {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        )

    def get_json(self, url: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self._limiter.wait()
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
            else:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 404:
                    raise EdgarError(f"404 not found: {url}")
                if resp.status_code == 403:
                    raise EdgarError(
                        f"403 forbidden from {url}. SEC rejects requests whose User-Agent "
                        f'is not of the form "app-name contact@example.com" (current: '
                        f"{self.user_agent!r})."
                    )
                if resp.status_code not in RETRY_STATUSES:
                    raise EdgarError(f"HTTP {resp.status_code} from {url}")
                last_error = EdgarError(f"HTTP {resp.status_code} from {url}")
            if attempt < self.max_attempts:
                self.sleep(2 ** (attempt - 1))  # 1s, 2s, 4s
        raise EdgarError(f"giving up on {url} after {self.max_attempts} attempts") from last_error

    def ticker_map(self) -> dict[str, dict[str, Any]]:
        """Ticker -> {cik, title}. EDGAR publishes this as a dict keyed by row index."""
        payload = self.get_json(TICKERS_URL)
        return {
            row["ticker"].upper(): {"cik": int(row["cik_str"]), "title": row["title"]}
            for row in payload.values()
        }

    def company_facts(self, cik: int) -> dict[str, Any]:
        return self.get_json(COMPANY_FACTS_URL.format(cik=cik))
