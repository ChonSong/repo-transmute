"""pytest configuration for repo_transmute tests."""

import os
import re

import pytest


# ---------------------------------------------------------------------------
# Helpers for tests that need real LLM API access
# ---------------------------------------------------------------------------

def require_api_key():
    """Skip the current test if no valid MINIMAX_API_KEY / ZAI_API_KEY is configured.

    A "valid" key is one that matches the expected format for a live account:
    - MiniMax: starts with ``sk-cp-`` and is 60–100 characters long
    - z.ai / GLM: exactly 32 hex characters (no domain prefix)
    """
    problem = _api_key_problem()
    if problem:
        pytest.skip(problem)


def _has_api_key() -> bool:
    """Return True when at least one real (non-placeholder) API key is present."""
    return _api_key_problem() is None


def _api_key_problem() -> str | None:
    """Return a skip reason string if no valid API key is configured, else None.

    Validates key format to avoid false positives from expired/demonstration keys
    that return 401/400 from the API.
    """
    minimax = os.environ.get("MINIMAX_API_KEY") or ""
    zai = os.environ.get("ZAI_API_KEY") or ""

    if minimax:
        # Real MiniMax API keys: sk-cp- prefix + 60–100 chars of alphanum/dash/underscore
        # (125-char keys are internal/demo keys that return 401)
        if minimax.startswith("sk-cp-") and 60 <= len(minimax) <= 100:
            return None  # looks like a real MiniMax key
        return (
            f"MINIMAX_API_KEY is set but does not match real key format "
            f"(starts with 'sk-cp-' and is 60–100 chars). "
            f"Current length={len(minimax)}. "
            f"Set a valid key to enable real-LLM tests."
        )

    if zai:
        # Real z.ai keys: 32 hex characters (no domain prefix, no dashes)
        if re.match(r"^[a-f0-9]{32}$", zai):
            return None  # looks like a real z.ai key
        return (
            f"ZAI_API_KEY is set but does not match real key format (32 hex chars). "
            f"Current length={len(zai)}. "
            f"Set a valid key to enable real-LLM tests."
        )

    return "No MINIMAX_API_KEY or ZAI_API_KEY set — skipping real LLM tests."


# ---------------------------------------------------------------------------
# pytest hooks
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register the ``real_llm`` custom marker."""
    config.addinivalue_line(
        "markers",
        "real_llm: tests that call the real MiniMax or z.ai API (require API key)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip ``@pytest.mark.real_llm`` tests at collection time when no valid key is found.

    This keeps the default ``pytest`` run clean even when the environment
    has misconfigured or expired API keys.  When a valid key is present,
    real_llm tests still need ``-k real_llm`` to be selected (to avoid
    accidental real API calls during normal test runs).
    """
    problem = _api_key_problem()
    if problem is None:
        return  # Valid key present — let tests run (require_api_key() guards at runtime)

    skip_marker = pytest.mark.skip(reason=f"Real LLM tests skipped: {problem}")

    for item in items:
        if item.get_closest_marker("real_llm") is not None:
            item.add_marker(skip_marker)