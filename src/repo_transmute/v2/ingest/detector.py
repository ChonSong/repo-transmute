"""Multi-framework detection from project structure and dependencies."""

from __future__ import annotations

from pathlib import Path

from repo_transmute.v2.models import Framework, StyleApproach


# Framework fingerprints: sets of files/patterns that indicate a framework
FRAMEWORK_SIGNALS: dict[Framework, list[str]] = {
    Framework.REACT: ["react", "react-dom", "jsx", "tsx"],
    Framework.VUE: ["vue", ".vue"],
    Framework.SVELTE: ["svelte", ".svelte"],
    Framework.SOLID: ["solid-js", "solid-start"],
    Framework.PREACT: ["preact"],
    Framework.NEXTJS: ["next"],
    Framework.NUXT: ["nuxt"],
    Framework.ASTRO: ["astro"],
}

# Style approach fingerprints
STYLE_SIGNALS: dict[StyleApproach, list[str]] = {
    StyleApproach.TAILWIND: ["tailwindcss", "tailwind.config", "@tailwind"],
    StyleApproach.CSS_MODULES: [".module.css", ".module.scss", "styles.module"],
    StyleApproach.STYLED_COMPONENTS: ["styled-components", "styled."],
    StyleApproach.CSS_VARIABLES: ["var(--"],
    StyleApproach.SCSS_SASS: [".scss", ".sass", "node-sass", "sass"],
    StyleApproach.INLINE_STYLES: ["style={{"],
    StyleApproach.EMOTION: ["@emotion/", "css`"],
    StyleApproach.VANILLA_CSS: [".css"],
}


def detect_framework(repo_path: Path) -> tuple[Framework, StyleApproach]:
    """Detect the framework and style approach of a project.
    
    Returns:
        (Framework, StyleApproach) tuple
    """
    # Check package.json first
    pkg_json = repo_path / "package.json"
    pkg_content = ""
    if pkg_json.exists():
        pkg_content = pkg_json.read_text()
    
    # Scan for framework indicators
    framework_scores: dict[Framework, int] = {f: 0 for f in Framework}
    
    # Check dependencies in package.json
    for framework, signals in FRAMEWORK_SIGNALS.items():
        for signal in signals:
            if signal in pkg_content:
                framework_scores[framework] += 2
    
    # Check file extensions
    for ext, framework in [
        (".tsx", Framework.REACT),
        (".jsx", Framework.REACT),
        (".vue", Framework.VUE),
        (".svelte", Framework.SVELTE),
    ]:
        if list(repo_path.rglob(f"*{ext}")):
            framework_scores[framework] += 3
    
    # Check for config files
    config_files = {
        "next.config": Framework.NEXTJS,
        "nuxt.config": Framework.NUXT,
        "astro.config": Framework.ASTRO,
        "svelte.config": Framework.SVELTE,
        "vite.config": None,  # Generic, doesn't indicate framework
    }
    for config_name, framework in config_files.items():
        if framework and list(repo_path.rglob(f"{config_name}*")):
            framework_scores[framework] += 5
    
    # Pick the highest scoring framework
    best_framework = max(framework_scores, key=framework_scores.get)
    if framework_scores[best_framework] == 0:
        best_framework = Framework.UNKNOWN
    
    # Detect style approach
    style_scores: dict[StyleApproach, int] = {s: 0 for s in StyleApproach}
    
    for approach, signals in STYLE_SIGNALS.items():
        for signal in signals:
            if signal in pkg_content:
                style_scores[approach] += 2
    
    # Check for style files
    style_file_signals = {
        "tailwind.config": StyleApproach.TAILWIND,
        ".module.css": StyleApproach.CSS_MODULES,
        ".module.scss": StyleApproach.CSS_MODULES,
    }
    for file_pattern, approach in style_file_signals.items():
        if list(repo_path.rglob(f"*{file_pattern}*")):
            style_scores[approach] += 3
    
    # Check for CSS variable usage in CSS files
    for css_file in repo_path.rglob("*.css"):
        content = css_file.read_text()
        if "var(--" in content:
            style_scores[StyleApproach.CSS_VARIABLES] += 1
        if "@tailwind" in content:
            style_scores[StyleApproach.TAILWIND] += 3
    
    best_style = max(style_scores, key=style_scores.get)
    if style_scores[best_style] == 0:
        best_style = StyleApproach.UNKNOWN
    
    return best_framework, best_style


def detect_entry_points(repo_path: Path, framework: Framework) -> list[str]:
    """Detect the main entry points of the project."""
    entry_points = []
    
    # Common entry patterns
    patterns = ["src/main", "src/index", "src/app", "index"]
    for pattern in patterns:
        for ext in [".tsx", ".ts", ".jsx", ".js"]:
            candidate = repo_path / f"{pattern}{ext}"
            if candidate.exists():
                entry_points.append(str(candidate.relative_to(repo_path)))
    
    return entry_points
