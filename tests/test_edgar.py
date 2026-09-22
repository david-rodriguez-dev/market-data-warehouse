"""EDGAR client behaviour, without the network."""
from __future__ import annotations

import pytest

from mdw.edgar import EdgarClient, EdgarError, RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(round(s, 6))
        self.t += s


class FakeResponse:
    def __init__(self, status_code: int, payload=None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.headers: dict[str, str] = {}
        self._responses = list(responses)
        self.calls: list[str] = []

    def get(self, url: str, timeout: float) -> FakeResponse:
        self.calls.append(url)
        return self._responses.pop(0)


def make_client(*responses: FakeResponse) -> tuple[EdgarClient, FakeSession, list[float]]:
    session = FakeSession(list(responses))
    backoffs: list[float] = []
    client = EdgarClient(
        user_agent="test-app test@example.com",
        session=session,
        sleep=backoffs.append,
        max_per_second=1e9,
    )
    return client, session, backoffs


def test_rate_limiter_spaces_calls_at_the_configured_interval():
    clock = FakeClock()
    limiter = RateLimiter(4, clock=clock.now, sleep=clock.sleep)
    for _ in range(3):
        limiter.wait()
    assert clock.slept == [0.25, 0.25]


def test_rate_limiter_rejects_non_positive_rate():
    with pytest.raises(ValueError):
        RateLimiter(0)


def test_user_agent_is_sent_on_every_request():
    client, session, _ = make_client(FakeResponse(200, {}))
    client.get_json("https://example.test/x")
    assert session.headers["User-Agent"] == "test-app test@example.com"


def test_retries_transient_errors_with_backoff_then_succeeds():
    client, session, backoffs = make_client(
        FakeResponse(503), FakeResponse(429), FakeResponse(200, {"ok": True})
    )
    assert client.get_json("https://example.test/x") == {"ok": True}
    assert len(session.calls) == 3
    assert backoffs == [1, 2]


def test_404_is_not_retried():
    client, session, backoffs = make_client(FakeResponse(404))
    with pytest.raises(EdgarError, match="404"):
        client.get_json("https://example.test/missing")
    assert len(session.calls) == 1
    assert backoffs == []


def test_gives_up_after_max_attempts():
    client, session, _ = make_client(*[FakeResponse(503)] * 4)
    with pytest.raises(EdgarError, match="giving up"):
        client.get_json("https://example.test/x")
    assert len(session.calls) == 4


def test_ticker_map_reshapes_edgars_index_keyed_payload():
    payload = {
        "0": {"cik_str": 320193, "ticker": "aapl", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
    }
    client, _, _ = make_client(FakeResponse(200, payload))
    assert client.ticker_map() == {
        "AAPL": {"cik": 320193, "title": "Apple Inc."},
        "MSFT": {"cik": 789019, "title": "MICROSOFT CORP"},
    }
