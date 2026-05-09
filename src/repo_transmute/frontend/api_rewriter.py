"""API call pattern detection and rewriting for frontend migration.

Handles:
- Detection of fetch/axios/EventSource/WebSocket call patterns
- API URL mapping between source and target projects
- Generation of rewrite rules for LLM transpilation
- Validation of API contract compatibility
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class APISignature:
    """A frontend API call signature."""
    url: str
    method: str = 'GET'
    function_name: str = ''
    uses_streaming: bool = False
    uses_websocket: bool = False
    uses_sse: bool = False
    has_auth_header: bool = False
    has_body: bool = False
    content_type: str = ''  # application/json, multipart/form-data, etc.
    response_type: str = ''  # json, text, stream, blob
    error_handling: str = ''  # try/catch, .catch(), etc.
    file: str = ''
    line: int = 0


@dataclass
class APIRewriteRule:
    """A rule for rewriting API calls during migration."""
    source_pattern: str  # regex or literal string to match
    target_replacement: str  # replacement string or template
    description: str = ''
    confidence: float = 1.0
    requires_manual_review: bool = False


@dataclass
class APIMapping:
    """Complete API mapping between source and target projects."""
    source_apis: list[APISignature] = field(default_factory=list)
    target_apis: list[APISignature] = field(default_factory=list)
    mappings: list[tuple[APISignature, APISignature, float]] = field(default_factory=list)
    unmapped_source: list[APISignature] = field(default_factory=list)
    unmapped_target: list[APISignature] = field(default_factory=list)


def extract_api_calls_from_file(file_path: Path) -> list[APISignature]:
    """Extract API call signatures from a single file."""
    content = file_path.read_text()
    lines = content.splitlines()
    signatures = []
    
    # fetch() calls
    # Pattern: fetch(url, options)
    fetch_block_pattern = re.compile(
        r'fetch\(\s*([`\'"][^`\'"]+[`\'"]|\w+)\s*,?\s*({[^}]*})?\s*\)',
        re.DOTALL,
    )
    
    for m in fetch_block_pattern.finditer(content):
        url = m.group(1).strip().strip("'\"`")
        options_str = m.group(2) or ''
        
        sig = APISignature(
            url=url,
            file=str(file_path),
            line=content[:m.start()].count('\n') + 1,
        )
        
        # Extract method
        method_match = re.search(r"method\s*:\s*['\"](\w+)['\"]", options_str)
        if method_match:
            sig.method = method_match.group(1)
        
        # Check for auth headers
        if 'Authorization' in options_str or 'Bearer' in options_str or 'token' in options_str.lower():
            sig.has_auth_header = True
        
        # Check for body
        if 'body:' in options_str or 'body :' in options_str:
            sig.has_body = True
        
        # Check content type
        ct_match = re.search(r"Content-Type['\"]?\s*:\s*['\"]([^'\"]+)['\"]", options_str)
        if ct_match:
            sig.content_type = ct_match.group(1)
        
        # Check error handling
        nearby = content[max(0, m.start()-50):m.end()+200]
        if 'try' in nearby and 'catch' in nearby:
            sig.error_handling = 'try/catch'
        elif '.catch(' in nearby:
            sig.error_handling = '.catch()'
        
        # Check response handling
        if '.json()' in nearby:
            sig.response_type = 'json'
        elif '.text()' in nearby:
            sig.response_type = 'text'
        elif '.blob()' in nearby:
            sig.response_type = 'blob'
        
        # Check streaming
        if 'getReader' in nearby or 'ReadableStream' in nearby:
            sig.uses_streaming = True
            sig.response_type = 'stream'
        
        signatures.append(sig)
    
    # EventSource (SSE)
    # Pattern: new EventSource(url) or new EventSource(url, options)
    es_pattern = re.compile(r'new\s+EventSource\(\s*[`\'"]([^`\'"]+)[`\'"]')
    for m in es_pattern.finditer(content):
        sig = APISignature(
            url=m.group(1),
            method='GET',
            uses_sse=True,
            response_type='stream',
            file=str(file_path),
            line=content[:m.start()].count('\n') + 1,
        )
        signatures.append(sig)
    
    # WebSocket
    ws_pattern = re.compile(r'new\s+WebSocket\(\s*[`\'"]([^`\'"]+)[`\'"]')
    for m in ws_pattern.finditer(content):
        sig = APISignature(
            url=m.group(1),
            method='GET',
            uses_websocket=True,
            response_type='stream',
            file=str(file_path),
            line=content[:m.start()].count('\n') + 1,
        )
        signatures.append(sig)
    
    # axios calls: axios.get(url), axios.post(url, data)
    axios_pattern = re.compile(
        r'axios\.(get|post|put|patch|delete)\(\s*[`\'"]([^`\'"]+)[`\'"]'
    )
    for m in axios_pattern.finditer(content):
        sig = APISignature(
            url=m.group(2),
            method=m.group(1).upper(),
            file=str(file_path),
            line=content[:m.start()].count('\n') + 1,
        )
        signatures.append(sig)
    
    # API client methods (custom API wrappers)
    # Pattern: api.get('/path'), apiClient.post('/path'), etc.
    api_client_pattern = re.compile(
        r'(\w+api\w*|\w+client\w*)\.(get|post|put|patch|delete)\(\s*[`\'"]([^`\'"]+)[`\'"]',
        re.IGNORECASE,
    )
    for m in api_client_pattern.finditer(content):
        sig = APISignature(
            url=m.group(3),
            method=m.group(2).upper(),
            function_name=m.group(1),
            file=str(file_path),
            line=content[:m.start()].count('\n') + 1,
        )
        signatures.append(sig)
    
    return signatures


def extract_all_api_calls(repo_path: Path) -> list[APISignature]:
    """Extract all API calls from a repository."""
    all_sigs = []
    
    for ext in ('.tsx', '.jsx', '.ts', '.js'):
        for file_path in repo_path.rglob(f'*{ext}'):
            if any(skip in str(file_path) for skip in ('node_modules', 'dist', '.next', '.turbo', '__pycache__')):
                continue
            
            all_sigs.extend(extract_api_calls_from_file(file_path))
    
    # Deduplicate by (url, method)
    seen = set()
    unique = []
    for sig in all_sigs:
        key = (sig.url, sig.method)
        if key not in seen:
            seen.add(key)
            unique.append(sig)
    
    return unique


def generate_rewrite_rules(
    source_apis: list[APISignature],
    target_api_base: str = '',
    custom_mappings: dict[str, str] | None = None,
) -> list[APIRewriteRule]:
    """Generate rewrite rules for migrating API calls.
    
    Args:
        source_apis: API signatures from source project
        target_api_base: Base URL prefix for target project (e.g., '/api')
        custom_mappings: Manual URL mapping overrides {source_url: target_url}
    
    Returns:
        List of rewrite rules
    """
    rules = []
    custom_mappings = custom_mappings or {}
    
    for sig in source_apis:
        # Check custom mappings first
        if sig.url in custom_mappings:
            target_url = custom_mappings[sig.url]
            rules.append(APIRewriteRule(
                source_pattern=re.escape(sig.url),
                target_replacement=target_url,
                description=f"Custom mapping: {sig.url} → {target_url}",
                confidence=1.0,
            ))
            continue
        
        # Auto-detect mappings based on URL patterns
        # Common patterns:
        # /api/send-stream → /api/agent/chat
        # /api/sessions → /api/sessions (same)
        # /api/files → /api/files/* (pattern change)
        
        rewritten_url = _auto_map_url(sig.url, target_api_base)
        
        if rewritten_url != sig.url:
            rules.append(APIRewriteRule(
                source_pattern=re.escape(sig.url),
                target_replacement=rewritten_url,
                description=f"Auto-mapped: {sig.url} → {rewritten_url}",
                confidence=0.8,
            ))
        else:
            # URL stays the same, but may need method/response changes
            rules.append(APIRewriteRule(
                source_pattern=re.escape(sig.url),
                target_replacement=sig.url,
                description=f"URL unchanged: {sig.url} (verify method/response compatibility)",
                confidence=0.5,
                requires_manual_review=True,
            ))
    
    return rules


def _auto_map_url(source_url: str, target_base: str = '') -> str:
    """Auto-map a source URL to target URL based on common patterns."""
    # Ensure target_base doesn't end with /
    if target_base:
        target_base = target_base.rstrip('/')
    
    # Mapping table for common patterns
    # These are heuristics for hermes-workspace → agent-os
    pattern_map = {
        '/api/send-stream': '/api/agent/chat',
        '/api/send': '/api/agent/chat',
        '/api/chat-events': '/api/agent/chat',
        '/api/events': '/api/events/recent',
        '/api/history': '/api/sessions',
        '/api/session-status': '/api/system/uptime',
        '/api/claude-config': '/api/config',
        '/api/claude-jobs': '/api/cron/jobs',
        '/api/terminal-stream': '/api/terminal',  # agent-os may not have this yet
        '/api/terminal-input': '/api/terminal',
        '/api/memory': '/api/files/read',
        '/api/memory/list': '/api/files',
        '/api/memory/read': '/api/files/read',
        '/api/memory/write': '/api/files/write',
        '/api/memory/search': '/api/files',
        '/api/skills': '/api/skills',
        '/api/models': '/api/model/options',
        '/api/model/info': '/api/model/info',
        '/api/context-usage': '/api/analytics/usage',
        '/api/provider-usage': '/api/analytics/usage',
        '/api/gateway-reprobe': '/api/status',
        '/api/auth': '',  # agent-os doesn't have auth endpoints
        '/api/auth-check': '',
        '/api/paths': '/api/files',
        '/api/workspace': '/api/files',
        '/api/plugins': '/api/dashboard/plugins',
        '/api/integrations': '/api/tools/toolsets',
        '/api/connection-status': '/api/status',
        '/api/connection-settings': '/api/config',
        '/api/session-history': '/api/sessions',
        '/api/sessions/send': '/api/agent/chat',
    }
    
    if source_url in pattern_map:
        mapped = pattern_map[source_url]
        return f"{target_base}{mapped}" if mapped and target_base else mapped
    
    # Pattern-based mapping for variable URLs
    # /api/sessions/:id/messages → /api/sessions/:id/messages (same)
    # /api/files?action=read&path=xxx → /api/files/read/xxx (restructure)
    if '/api/' in source_url:
        parts = source_url.split('?')[0]  # Remove query string
        query_params = ''
        if '?' in source_url:
            query_params = source_url.split('?', 1)[1]
        
        # Handle query-param based file API
        if parts == '/api/files' and 'action=' in query_params:
            action_match = re.search(r'action=(\w+)', query_params)
            if action_match:
                action = action_match.group(1)
                if action in ('read', 'download'):
                    return f"{target_base}/api/files/read/*"
                elif action == 'write':
                    return f"{target_base}/api/files/write/*"
        
        # Handle session ID patterns
        session_match = re.search(r'/api/sessions/(\w+)', parts)
        if session_match:
            # Check if it's a session-specific action
            if '/messages' in parts:
                return f"{target_base}/api/sessions/:id/messages"
            elif '/status' in parts:
                return f"{target_base}/api/sessions/:id"
            elif '/active-run' in parts:
                return f"{target_base}/api/sessions/:id"
            else:
                return f"{target_base}/api/sessions/:id"
    
    # Default: keep URL as-is
    return f"{target_base}{source_url}" if target_base else source_url


def analyze_api_compatibility(
    source_sigs: list[APISignature],
    target_sigs: list[APISignature],
) -> dict[str, Any]:
    """Analyze API compatibility between source and target projects."""
    source_urls = {(s.url, s.method) for s in source_sigs}
    target_urls = {(t.url, t.method) for t in target_sigs}
    
    # URL-only comparison (ignore method for broader matching)
    source_url_set = {s.url for s in source_sigs}
    target_url_set = {t.url for t in target_sigs}
    
    # Find potential matches
    exact_matches = source_urls & target_urls
    url_matches = source_url_set & target_url_set
    source_only = source_urls - target_urls
    target_only = target_urls - source_urls
    
    # Categorize by type
    streaming_source = [s for s in source_sigs if s.uses_streaming or s.uses_sse or s.uses_websocket]
    streaming_target = [t for t in target_sigs if t.uses_streaming or t.uses_sse or t.uses_websocket]
    
    return {
        'total_source_apis': len(source_sigs),
        'total_target_apis': len(target_sigs),
        'exact_matches': len(exact_matches),
        'url_matches': len(url_matches),
        'source_only': len(source_only),
        'target_only': len(target_only),
        'streaming_source_count': len(streaming_source),
        'streaming_target_count': len(streaming_target),
        'compatibility_score': len(exact_matches) / max(len(source_urls), 1),
        'source_apis': [{'url': s.url, 'method': s.method, 'uses_sse': s.uses_sse, 'uses_websocket': s.uses_websocket} for s in source_sigs],
        'target_apis': [{'url': t.url, 'method': t.method, 'uses_sse': t.uses_sse, 'uses_websocket': t.uses_websocket} for t in target_sigs],
        'unmapped_source': [{'url': s.url, 'method': s.method} for s in source_sigs if (s.url, s.method) not in target_urls],
    }


def generate_api_migration_blueprint(
    source_repo: Path,
    target_repo: Path | None = None,
) -> dict[str, Any]:
    """Generate a complete API migration blueprint.
    
    This is the main entry point for API migration analysis.
    """
    source_apis = extract_all_api_calls(source_repo)
    target_apis = []
    
    if target_repo:
        target_apis = extract_all_api_calls(target_repo)
    
    compatibility = analyze_api_compatibility(source_apis, target_apis)
    rewrite_rules = generate_rewrite_rules(source_apis)
    
    return {
        'source_api_count': len(source_apis),
        'target_api_count': len(target_apis),
        'compatibility': compatibility,
        'rewrite_rules': [
            {
                'source': r.source_pattern,
                'target': r.target_replacement,
                'description': r.description,
                'confidence': r.confidence,
                'requires_review': r.requires_manual_review,
            }
            for r in rewrite_rules
        ],
        'streaming_apis': [
            {
                'url': s.url,
                'type': 'sse' if s.uses_sse else 'websocket' if s.uses_websocket else 'stream',
                'file': s.file,
            }
            for s in source_apis
            if s.uses_streaming or s.uses_sse or s.uses_websocket
        ],
        'recommendation': (
            f"{len(source_apis)} source API calls found. "
            f"{compatibility['exact_matches']} exact matches with target. "
            f"{len(rewrite_rules)} rewrite rules generated. "
            f"{compatibility['streaming_source_count']} streaming APIs need special handling."
        ),
    }
