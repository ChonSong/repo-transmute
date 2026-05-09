"""Frontend module for repo-transmute — JSX/TSX extraction, CSS mapping, API rewriting."""

from repo_transmute.frontend.component_extractor import (
    extract_components_from_file,
    extract_routes_from_file,
    extract_frontend_blueprint,
    ComponentDef,
    RouteDef,
    APICallDef,
    ImportDef,
)

from repo_transmute.frontend.css_mapper import (
    extract_css_theme_system,
    map_theme_compatibility,
    extract_api_url_mappings,
    CSSThemeSystem,
    ThemeDef,
    CSSVarDef,
    TailwindTheme,
)

from repo_transmute.frontend.api_rewriter import (
    extract_api_calls_from_file,
    extract_all_api_calls,
    generate_rewrite_rules,
    analyze_api_compatibility,
    generate_api_migration_blueprint,
    APISignature,
    APIRewriteRule,
    APIMapping,
)

__all__ = [
    # Component extraction
    'extract_components_from_file',
    'extract_routes_from_file',
    'extract_frontend_blueprint',
    'ComponentDef',
    'RouteDef',
    'APICallDef',
    'ImportDef',
    # CSS mapping
    'extract_css_theme_system',
    'map_theme_compatibility',
    'extract_api_url_mappings',
    'CSSThemeSystem',
    'ThemeDef',
    'CSSVarDef',
    'TailwindTheme',
    # API rewriting
    'extract_api_calls_from_file',
    'extract_all_api_calls',
    'generate_rewrite_rules',
    'analyze_api_compatibility',
    'generate_api_migration_blueprint',
    'APISignature',
    'APIRewriteRule',
    'APIMapping',
]
