"""API rewriter — adapt API calls during migration."""

from __future__ import annotations

from repo_transmute.v2.models import APICallDef


def rewrite_api_calls(
    calls: list[APICallDef],
    source_base_url: str = "",
    target_base_url: str = "",
) -> list[dict]:
    """Rewrite API calls for the target stack.
    
    Generates mapping rules for adapting API endpoints:
    - URL rewriting (base URL changes)
    - Method adaptation
    - Streaming/SSE handling
    - Auth token handling
    
    Returns:
        List of rewrite rules
    """
    rules = []
    
    for call in calls:
        rule = {
            "source_url": call.url,
            "target_url": _rewrite_url(call.url, source_base_url, target_base_url),
            "method": call.method,
            "is_streaming": call.is_sse or call.is_websocket,
            "auth_required": call.auth_required,
        }
        rules.append(rule)
    
    return rules


def _rewrite_url(url: str, source_base: str, target_base: str) -> str:
    """Rewrite a URL from source base to target base."""
    if not source_base or not target_base:
        return url
    
    if url.startswith(source_base):
        return url.replace(source_base, target_base, 1)
    
    # Handle relative URLs
    if url.startswith("/"):
        return target_base.rstrip("/") + url
    
    return url
