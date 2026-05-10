"""Core data models for repo-transmute v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Framework(Enum):
    """Supported source frameworks."""
    REACT = "react"
    VUE = "vue"
    SVELTE = "svelte"
    SOLID = "solid"
    PREACT = "preact"
    NEXTJS = "nextjs"
    NUXT = "nuxt"
    ASTRO = "astro"
    UNKNOWN = "unknown"


class TargetStack(Enum):
    """Supported target stacks."""
    REACT_TS = "react-ts"
    VUE_TS = "vue-ts"
    SVELTE_TS = "svelte-ts"
    REACT_JS = "react-js"
    VUE_JS = "vue-js"


class StyleApproach(Enum):
    """CSS/styling approach used by the source."""
    TAILWIND = "tailwind"
    CSS_MODULES = "css-modules"
    STYLED_COMPONENTS = "styled-components"
    CSS_VARIABLES = "css-variables"
    SCSS_SASS = "scss-sass"
    INLINE_STYLES = "inline-styles"
    EMOTION = "emotion"
    VANILLA_CSS = "vanilla-css"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ComponentType(Enum):
    """Type of component."""
    PAGE = "page"          # Top-level page/route component
    LAYOUT = "layout"      # Layout wrapper (sidebar, header, etc.)
    COMPONENT = "component" # Reusable UI component
    WIDGET = "widget"       # Small self-contained widget
    UTILITY = "utility"     # Utility/helper component
    UNKNOWN = "unknown"


class MigrationStatus(Enum):
    """Status of a migration item."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_FIX = "needs_fix"
    SKIPPED = "skipped"


@dataclass
class PropDef:
    """Component prop definition."""
    name: str
    type: str
    default: str | None = None
    required: bool = True
    description: str = ""
    is_optional: bool = False


@dataclass
class StateDef:
    """Component state definition."""
    name: str
    type: str
    init_value: str = ""
    framework_specific: str = ""  # e.g., "useState", "ref", "signal"


@dataclass
class EffectDef:
    """Component effect/lifecycle definition."""
    type: str  # useEffect, onMounted, etc.
    deps: list[str] = field(default_factory=list)
    has_cleanup: bool = False


@dataclass
class APICallDef:
    """API call definition."""
    url: str
    method: str = "GET"
    function_name: str = ""
    is_streaming: bool = False
    is_sse: bool = False
    is_websocket: bool = False
    auth_required: bool = False
    request_body_type: str = ""
    response_type: str = ""


@dataclass
class ImportDef:
    """Import statement definition."""
    module: str
    names: list[str] = field(default_factory=list)
    is_default: bool = False
    is_type_only: bool = False
    is_relative: bool = False  # Relative import (local file) vs package


@dataclass
class ComponentDef:
    """Complete component definition extracted from source."""
    name: str
    file: str  # Relative path
    line: int
    component_type: ComponentType = ComponentType.UNKNOWN
    framework: Framework = Framework.UNKNOWN

    # Structure
    props: list[PropDef] = field(default_factory=list)
    state: list[StateDef] = field(default_factory=list)
    effects: list[EffectDef] = field(default_factory=list)
    api_calls: list[APICallDef] = field(default_factory=list)
    imports: list[ImportDef] = field(default_factory=list)
    children_components: list[str] = field(default_factory=list)  # Components this uses
    hooks_used: list[str] = field(default_factory=list)

    # JSX/Template
    has_jsx: bool = False
    jsx_complexity: int = 0  # Rough count of JSX elements
    template_tags: list[str] = field(default_factory=list)  # HTML/JSX tags used

    # Styling
    css_approach: StyleApproach = StyleApproach.UNKNOWN
    css_variables_used: list[str] = field(default_factory=list)
    tailwind_classes: list[str] = field(default_factory=list)
    style_imports: list[str] = field(default_factory=list)

    # Source code
    full_source: str = ""  # Complete source of the component
    template_source: str = ""  # Just the JSX/template portion

    # Migration state
    migration_status: MigrationStatus = MigrationStatus.PENDING
    target_file: str = ""
    vision_score: float = 0.0  # 0-1 similarity score
    fix_attempts: int = 0


@dataclass
class RouteDef:
    """Route/path definition."""
    path: str
    component: str  # Component name
    file: str  # File path
    is_layout: bool = False
    children: list[RouteDef] = field(default_factory=list)
    is_dynamic: bool = False  # Has :param or [param]


@dataclass
class ThemeDef:
    """Theme definition."""
    name: str
    is_dark: bool = False
    colors: dict[str, str] = field(default_factory=dict)
    css_variables: dict[str, str] = field(default_factory=dict)
    tailwind_config: dict[str, Any] = field(default_factory=dict)
    fonts: list[str] = field(default_factory=list)
    spacing_scale: list[str] = field(default_factory=list)


@dataclass
class StyleSystem:
    """Complete style system of a project."""
    approach: StyleApproach = StyleApproach.UNKNOWN
    themes: list[ThemeDef] = field(default_factory=list)
    global_utilities: list[str] = field(default_factory=list)
    css_files: list[str] = field(default_factory=list)
    css_variables: dict[str, str] = field(default_factory=dict)
    tailwind_config: dict[str, Any] = field(default_factory=dict)
    design_tokens: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScreenshotDef:
    """Screenshot metadata."""
    page_url: str
    component_name: str = ""
    viewport: tuple[int, int] = (1920, 1080)
    full_page: bool = True
    file_path: str = ""
    timestamp: str = ""
    component_bounds: dict[str, int] = field(default_factory=dict)  # x, y, width, height


@dataclass
class VisionResult:
    """Result of vision comparison between source and target screenshots."""
    source_screenshot: str
    target_screenshot: str
    overall_score: float  # 0-1 similarity
    component_scores: dict[str, float] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)  # Detected differences
    suggestions: list[str] = field(default_factory=list)  # Fix suggestions
    layout_match: bool = True
    color_match: bool = True
    typography_match: bool = True
    spacing_match: bool = True


@dataclass
class PageDef:
    """Page definition combining route, component, and screenshots."""
    route: RouteDef
    component: ComponentDef
    source_screenshot: ScreenshotDef | None = None
    target_screenshot: ScreenshotDef | None = None
    vision_result: VisionResult | None = None


@dataclass
class ProjectBlueprint:
    """Complete project blueprint after extraction."""
    source_repo: str
    source_path: Path
    framework: Framework
    style_approach: StyleApproach

    components: list[ComponentDef] = field(default_factory=list)
    routes: list[RouteDef] = field(default_factory=list)
    style_system: StyleSystem | None = None
    pages: list[PageDef] = field(default_factory=list)

    # File tree
    file_tree: dict[str, Any] = field(default_factory=dict)
    total_files: int = 0
    total_lines: int = 0

    # Screenshots
    screenshots: list[ScreenshotDef] = field(default_factory=list)

    # Migration tracking
    migration_order: list[str] = field(default_factory=list)  # Ordered component names
    dependencies: dict[str, list[str]] = field(default_factory=dict)  # component -> deps

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def get_component(self, name: str) -> ComponentDef | None:
        for c in self.components:
            if c.name == name:
                return c
        return None

    def get_dependencies(self, name: str) -> list[str]:
        return self.dependencies.get(name, [])
