"""Paths, environment, and the tracked-company list.

Everything the pipeline needs to know about *where* lives here so the other
modules can stay about *what*.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"
DEFAULT_DB_PATH = DATA_DIR / "warehouse.duckdb"
SQL_DIR = PROJECT_ROOT / "sql"
QUALITY_DIR = PROJECT_ROOT / "tests" / "quality"
COMPANIES_PATH = PROJECT_ROOT / "config" / "companies.json"

# SEC requires a descriptive User-Agent identifying the requester. It is
# deliberately *not* defaulted here: a public repo must never ship a contact
# address, and a missing value should fail loudly rather than get rate-limited.
USER_AGENT_ENV = "EDGAR_USER_AGENT"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True)
class Companies:
    tickers: tuple[str, ...]
    taxonomy: str = "us-gaap"
    unit: str = "USD"


def user_agent() -> str:
    value = os.environ.get(USER_AGENT_ENV, "").strip()
    if not value:
        raise ConfigError(
            f"{USER_AGENT_ENV} is not set. SEC EDGAR requires a User-Agent of the "
            f'form "app-name contact@example.com". Example:\n'
            f"  set {USER_AGENT_ENV}=market-data-warehouse you@example.com\n"
            f"The address must be present: EDGAR returns 403 without one."
        )
    return value


def load_companies(path: Path = COMPANIES_PATH) -> Companies:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"company list not found: {path}") from exc
    tickers = raw.get("tickers")
    if not isinstance(tickers, list) or not tickers:
        raise ConfigError(f"{path} must contain a non-empty 'tickers' list")
    return Companies(
        tickers=tuple(t.strip().upper() for t in tickers),
        taxonomy=raw.get("taxonomy", "us-gaap"),
        unit=raw.get("unit", "USD"),
    )


def db_path() -> Path:
    override = os.environ.get("MDW_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH
