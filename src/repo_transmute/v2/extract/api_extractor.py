"""API pattern extraction — endpoint discovery and call pattern analysis."""

from __future__ import annotations

import re
from pathlib import Path

from repo_transmute.v2.models import APICallDef


def extract_api_patterns(repo_path: Path) -> list[APICallDef]:
    """Extract all API call patterns from the project."""
    calls = []
    
    # Scan all TS/JS files
    for ext in [".ts", ".tsx", ".js", ".jsx"]:
        for file_path in repo_path.rglob(f"*{ext}"):
            if "node_modules" in str(file_path):
                continue
            try:
                content = file_path.read_text()
                file_calls = _extract_from_file(content, str(file_path.relative_to(repo_path)))
                calls.extend(file_calls)
            except Exception:
                continue
    
    # Deduplicate by URL
    seen = set()
    unique = []
    for call in calls:
        key = f"{call.method}:{call.url}"
        if key not in seen:
            seen.add(key)
            unique.append(call)
    
    return unique


def _extract_from_file(content: str, file_path: str) -> list[APICallDef]:
    """Extract API calls from a single file."""
    calls = []
    
    # fetch() calls
    for match in re.finditer(r'fetch\s*\(\s*[`"\']([^`"\']+)[`"\']', content):
        url = match.group(1)
        calls.append(APICallDef(
            url=url,
            method="GET",
            function_name="",
            is_sse="EventSource" in content or "text/event-stream" in content,
            is_websocket="WebSocket" in content or "new WebSocket" in content,
        ))
    
    # fetch with method
    for match in re.finditer(r'fetch\s*\([^)]*method\s*:\s*[`"\'](\w+)[`"\']', content):
        # Find the URL for this fetch call
        start = match.start()
        url_match = re.search(r'fetch\s*\(\s*[`"\']([^`"\']+)[`"\']', content[max(0,start-50):start+200])
        if url_match:
            calls.append(APICallDef(
                url=url_match.group(1),
                method=match.group(1).upper(),
                function_name="",
            ))
    
    # axios calls
    for match in re.finditer(r'axios\.(get|post|put|delete|patch)\s*\(\s*[`"\']([^`"\']+)[`"\']', content):
        calls.append(APICallDef(
            url=match.group(2),
            method=match.group(1).upper(),
            function_name="",
        ))
    
    # SSE/EventSource
    for match in re.finditer(r'EventSource\s*\(\s*[`"\']([^`"\']+)[`"\']', content):
        calls.append(APICallDef(
            url=match.group(1),
            method="GET",
            function_name="",
            is_sse=True,
        ))
    
    # WebSocket
    for match in re.finditer(r'new WebSocket\s*\(\s*[`"\']([^`"\']+)[`"\']', content):
        calls.append(APICallDef(
            url=match.group(1),
            method="GET",
            function_name="",
            is_websocket=True,
        ))
    
    return calls
