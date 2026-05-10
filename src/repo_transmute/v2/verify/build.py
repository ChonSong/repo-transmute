"""Build target project and capture screenshots."""

from __future__ import annotations

import subprocess
from pathlib import Path


def build_project(project_path: Path, framework: str = "react") -> tuple[bool, str]:
    """Build the target project.
    
    Returns:
        (success, output) tuple
    """
    if framework in ("react", "nextjs", "preact", "solid"):
        return _build_npm_project(project_path)
    elif framework == "vue":
        return _build_npm_project(project_path)
    elif framework == "svelte":
        return _build_npm_project(project_path)
    
    return False, f"Unknown framework: {framework}"


def _build_npm_project(project_path: Path) -> tuple[bool, str]:
    """Build an npm-based project."""
    # Install deps
    result = subprocess.run(
        ["npm", "install"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return False, f"npm install failed: {result.stderr}"
    
    # Build
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return False, f"Build failed: {result.stderr}"
    
    return True, result.stdout
