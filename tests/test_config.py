"""Configuration guards that fail fast with an explanation."""
from __future__ import annotations

import pytest

from mdw import config


def test_user_agent_is_required(monkeypatch):
    monkeypatch.delenv(config.USER_AGENT_ENV, raising=False)
    with pytest.raises(config.ConfigError, match="contact@example.com"):
        config.user_agent()


def test_user_agent_containing_github_is_rejected_before_any_request(monkeypatch):
    # SEC answers HTTP 403 to any User-Agent with this substring; catch it locally.
    monkeypatch.setenv(config.USER_AGENT_ENV, "mdw someone.github@example.com")
    with pytest.raises(config.ConfigError, match="github"):
        config.user_agent()


def test_user_agent_passes_through(monkeypatch):
    monkeypatch.setenv(config.USER_AGENT_ENV, "  mdw someone@example.com ")
    assert config.user_agent() == "mdw someone@example.com"
