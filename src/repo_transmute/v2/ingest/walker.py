"""Smart file tree traversal — identifies relevant source files."""

from __future__ import annotations

from pathlib import Path

from repo_transmute.v2.models import Framework


# File extensions by framework
FRAMEWORK_EXTS: dict[Framework, list[str]] = {
    Framework.REACT: [".tsx", ".jsx", ".ts", ".js"],
    Framework.VUE: [".vue", ".ts", ".js"],
    Framework.SVELTE: [".svelte", ".ts", ".js"],
    Framework.SOLID: [".tsx", ".jsx", ".ts", ".js"],
    Framework.PREACT: [".tsx", ".jsx", ".ts", ".js"],
    Framework.NEXTJS: [".tsx", ".jsx", ".ts", ".js"],
    Framework.NUXT: [".vue", ".ts", ".js"],
    Framework.ASTRO: [".astro", ".ts", ".js"],
    Framework.UNKNOWN: [".tsx", ".jsx", ".vue", ".svelte", ".ts", ".js"],
}

# Directories to skip
SKIP_DIRS = {
    "node_modules", ".git", ".next", ".nuxt", ".svelte-kit", ".astro",
    "dist", "build", "out", ".cache", "__pycache__", ".venv", "venv",
    "coverage", ".turbo", ".nx",
}

# Files to skip
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.cjs",
    ".prettierrc", ".prettierrc.json",
    "tsconfig.json", "jsconfig.json",
}


def walk_project(
    repo_path: Path,
    framework: Framework,
) -> dict[str, list[Path]]:
    """Walk the project and categorize files by type.
    
    Returns:
        Dict mapping category to list of file paths:
        - 'components': Component files (.tsx, .vue, .svelte, etc.)
        - 'pages': Page/route files
        - 'styles': CSS/SCSS files
        - 'utils': Utility/helper files
        - 'config': Config files
        - 'api': API/client files
    """
    exts = FRAMEWORK_EXTS.get(framework, FRAMEWORK_EXTS[Framework.UNKNOWN])
    
    result: dict[str, list[Path]] = {
        "components": [],
        "pages": [],
        "styles": [],
        "utils": [],
        "config": [],
        "api": [],
        "other": [],
    }
    
    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue
        
        # Skip directories
        if any(skip in file_path.parts for skip in SKIP_DIRS):
            continue
        
        # Skip non-source files
        suffix = file_path.suffix
        name = file_path.name
        
        # Skip binary/lock files
        if suffix in {".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf"}:
            continue
        if name in SKIP_FILES:
            continue
        
        # Categorize
        rel_path = file_path.relative_to(repo_path)
        rel_str = str(rel_path)
        
        if suffix in {".css", ".scss", ".sass", ".less", ".styl"}:
            result["styles"].append(file_path)
        elif suffix in exts:
            # Check if it's a page
            if _is_page_file(rel_str, framework):
                result["pages"].append(file_path)
            elif _is_component_file(rel_str, name, framework):
                result["components"].append(file_path)
            elif _is_api_file(rel_str, name):
                result["api"].append(file_path)
            elif _is_util_file(rel_str, name):
                result["utils"].append(file_path)
            elif _is_config_file(rel_str, name):
                result["config"].append(file_path)
            else:
                result["other"].append(file_path)
        elif suffix in {".json", ".yaml", ".yml", ".toml"}:
            if _is_config_file(rel_str, name):
                result["config"].append(file_path)
    
    return result


def _is_page_file(rel_str: str, framework: Framework) -> bool:
    """Check if a file is a page/route file."""
    page_indicators = [
        "/pages/", "/routes/", "/views/", "/app/",
        "pages/", "routes/", "views/", "app/",
    ]
    if framework == Framework.NEXTJS:
        # Next.js uses app/ and pages/ directories
        return "app/" in rel_str or "pages/" in rel_str
    if framework == Framework.NUXT:
        return "pages/" in rel_str
    
    return any(ind in rel_str for ind in page_indicators)


def _is_component_file(rel_str: str, name: str, framework: Framework) -> bool:
    """Check if a file is a component file."""
    component_indicators = [
        "/components/", "/ui/", "/widgets/",
        "components/", "ui/", "widgets/",
    ]
    # Check if in a components directory or named like a component
    if any(ind in rel_str for ind in component_indicators):
        return True
    # Check if filename starts with uppercase (React convention)
    if name and name[0].isupper():
        return True
    return False


def _is_api_file(rel_str: str, name: str) -> bool:
    """Check if a file is an API/client file."""
    api_indicators = ["api", "client", "fetch", "http", "request", "service"]
    return any(ind in name.lower() for ind in api_indicators)


def _is_util_file(rel_str: str, name: str) -> bool:
    """Check if a file is a utility file."""
    util_indicators = ["util", "helper", "lib", "common", "shared", "constants", "types"]
    return any(ind in name.lower() for ind in util_indicators)


def _is_config_file(rel_str: str, name: str) -> bool:
    """Check if a file is a config file."""
    config_indicators = ["config", "webpack", "vite", "babel", "eslint", "prettier", "tsconfig"]
    return any(ind in name.lower() for ind in config_indicators)
