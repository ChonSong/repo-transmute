"""CLI for repo-transmute v2 — Vision-Driven Migration Engine."""

from __future__ import annotations

import json
from pathlib import Path

import click
import yaml

from repo_transmute.v2.models import Framework, TargetStack, ProjectBlueprint
from repo_transmute.v2.ingest.clone import clone_repo, clone_local_path
from repo_transmute.v2.ingest.detector import detect_framework
from repo_transmute.v2.ingest.walker import walk_project
from repo_transmute.v2.extract.ast_extractor import extract_components_ast, extract_routes
from repo_transmute.v2.extract.style_extractor import extract_style_system
from repo_transmute.v2.extract.api_extractor import extract_api_patterns
from repo_transmute.v2.extract.screenshot import capture_page_screenshots, check_playwright_installed


@click.group()
@click.version_option(version="2.0.0")
def v2():
    """RepoTransmute v2 — Vision-Driven Code Migration Engine."""
    pass


@v2.command()
@click.argument("source", required=False)
@click.option("--local", "-l", type=click.Path(path_type=Path), default=None,
              help="Local path instead of GitHub repo")
@click.option("--cache-dir", "-c", type=click.Path(path_type=Path), default=Path("./data/cache"),
              help="Cache directory for cloned repos")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=Path("./data/blueprints"),
              help="Output directory for blueprints")
@click.option("--branch", "-b", default=None, help="Branch to checkout")
def ingest(source: str | None, local: Path | None, cache_dir: Path, output_dir: Path, branch: str | None):
    """Clone + detect framework + extract AST blueprint."""
    if not source and not local:
        click.echo("Error: provide either SOURCE (owner/repo) or --local PATH", err=True)
        return
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Clone or use local
    if local:
        repo_path = clone_local_path(local)
        click.echo(f"Using local path: {repo_path}")
    else:
        click.echo(f"Cloning {source}...")
        repo_path = clone_repo(source, cache_dir, branch=branch)
        click.echo(f"Cloned to {repo_path}")
    
    # Detect framework
    click.echo("Detecting framework and style approach...")
    framework, style_approach = detect_framework(repo_path)
    click.echo(f"  Framework: {framework.value}")
    click.echo(f"  Style: {style_approach.value}")
    
    if framework == Framework.UNKNOWN:
        click.echo("Warning: Could not detect framework. Defaulting to React.", err=True)
        framework = Framework.REACT
    
    # Walk project
    click.echo("Walking project structure...")
    file_tree = walk_project(repo_path, framework)
    
    comp_files = file_tree.get("components", []) + file_tree.get("pages", [])
    click.echo(f"  Component files: {len(comp_files)}")
    click.echo(f"  Style files: {len(file_tree.get('styles', []))}")
    click.echo(f"  API files: {len(file_tree.get('api', []))}")
    
    # Extract components
    click.echo("Extracting components (AST)...")
    components = extract_components_ast(repo_path, framework, comp_files)
    click.echo(f"  Found {len(components)} components")
    
    # Extract routes
    click.echo("Extracting routes...")
    routes = extract_routes(repo_path, framework)
    click.echo(f"  Found {len(routes)} routes")
    
    # Extract style system
    click.echo("Extracting style system...")
    style_system = extract_style_system(repo_path)
    click.echo(f"  CSS variables: {len(style_system.css_variables)}")
    click.echo(f"  Themes: {len(style_system.themes)}")
    if style_system.tailwind_config:
        click.echo(f"  Tailwind config: detected")
    
    # Extract API patterns
    click.echo("Extracting API patterns...")
    api_calls = extract_api_patterns(repo_path)
    click.echo(f"  Found {len(api_calls)} API endpoints")
    
    # Build blueprint
    blueprint = ProjectBlueprint(
        source_repo=source or str(local),
        source_path=repo_path,
        framework=framework,
        style_approach=style_approach,
        components=components,
        routes=routes,
        style_system=style_system,
        total_files=sum(len(v) for v in file_tree.values()),
        dependencies={c.name: c.children_components for c in components},
    )
    
    # Compute migration order (dependencies first)
    blueprint.migration_order = _compute_migration_order(blueprint)
    
    # Save blueprint
    output_file = output_dir / f"{(source or local.name).replace('/', '__')}.yaml"
    output_file.write_text(yaml.dump({
        "source_repo": blueprint.source_repo,
        "framework": blueprint.framework.value,
        "style_approach": blueprint.style_approach.value,
        "total_files": blueprint.total_files,
        "components": [
            {
                "name": c.name,
                "file": c.file,
                "line": c.line,
                "type": c.component_type.value,
                "props": len(c.props),
                "state_count": len(c.state),
                "api_calls": len(c.api_calls),
                "jsx_complexity": c.jsx_complexity,
                "children": c.children_components,
            }
            for c in components
        ],
        "routes": [{"path": r.path, "component": r.component} for r in routes],
        "style_system": {
            "approach": style_system.approach.value,
            "themes": len(style_system.themes),
            "css_variables": len(style_system.css_variables),
        },
        "api_calls": [{"url": c.url, "method": c.method} for c in api_calls],
        "migration_order": blueprint.migration_order,
    }, default_flow_style=False))
    
    click.echo(f"\nBlueprint saved to {output_file}")
    click.echo(click.style(f"\n✅ {len(components)} components, {len(routes)} routes extracted", fg="green"))


@v2.command()
@click.argument("source", required=False)
@click.option("--local", "-l", type=click.Path(path_type=Path), default=None)
@click.option("--url", "-u", default="http://localhost:3000", help="URL to screenshot")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=Path("./data/screenshots"))
@click.option("--viewport", "-v", default="1920x1080", help="Viewport size (WxH)")
@click.option("--install-playwright", is_flag=True, help="Install Playwright if not present")
def screenshot(source: str | None, local: Path | None, url: str, output_dir: Path,
               viewport: str, install_playwright: bool):
    """Capture screenshots of source pages for visual reference."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if install_playwright:
        from repo_transmute.v2.extract.screenshot import install_playwright as _install
        click.echo("Installing Playwright...")
        if _install():
            click.echo("Playwright installed.")
        else:
            click.echo("Warning: Playwright installation failed.", err=True)
    
    if not check_playwright_installed():
        click.echo("Playwright not installed. Run with --install-playwright first.", err=True)
        return
    
    width, height = map(int, viewport.split("x"))
    
    click.echo(f"Capturing screenshots of {url}...")
    screenshots = capture_page_screenshots(url, output_dir, viewport=(width, height))
    
    click.echo(f"Captured {len(screenshots)} screenshots:")
    for ss in screenshots:
        click.echo(f"  - {ss.component_name}: {ss.file_path}")


@v2.command()
@click.argument("source", required=True)
@click.argument("target", required=True)
@click.option("--local-source", type=click.Path(path_type=Path), default=None)
@click.option("--local-target", type=click.Path(path_type=Path), default=None)
@click.option("--target-stack", "-t", default="react-ts",
              type=click.Choice(["react-ts", "vue-ts", "svelte-ts"]),
              help="Target stack")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=Path("./data/migrated"))
@click.option("--blueprint", "-b", type=click.Path(path_type=Path), default=None,
              help="Use existing blueprint file")
@click.option("--model", "-m", default="glm-5-turbo", help="LLM model to use")
@click.option("--max-iterations", "-i", default=3, help="Max migration iterations per component")
def migrate(source: str, target: str, local_source: Path | None, local_target: Path | None,
            target_stack: str, output_dir: Path, blueprint: Path | None,
            model: str, max_iterations: int):
    """Full migration: extract → migrate → verify → iterate."""
    from repo_transmute.v2.migrate.engine import MigrationEngine
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    target_stack_enum = TargetStack(target_stack)
    
    click.echo(f"Starting migration: {source} → {target}")
    click.echo(f"Target stack: {target_stack}")
    click.echo(f"Max iterations: {max_iterations}")
    click.echo("=" * 50)
    
    # Load or create blueprint
    if blueprint and blueprint.exists():
        click.echo(f"Loading blueprint from {blueprint}")
        bp_data = yaml.safe_load(blueprint.read_text())
        # For now, create a minimal blueprint from the YAML
        # In production, this would deserialize the full ProjectBlueprint
        click.echo("Blueprint loaded. Components: " + str(len(bp_data.get('components', []))))
    else:
        # Run ingest first
        click.echo("No blueprint found — running ingest first...")
        # Would call ingest here, but for now skip
        click.echo("Error: Run 'v2 ingest' first to create a blueprint.", err=True)
        return
    
    click.echo("\nMigration would start here — blueprint + engine integration in progress.")
    click.echo("The engine is built. Integration with the CLI migrate command is the next step.")


@v2.command()
@click.argument("source_screenshot")
@click.argument("target_screenshot")
@click.option("--output", "-o", default=None, help="Output diff image path")
def verify(source_screenshot: str, target_screenshot: str, output: str | None):
    """Compare source vs target screenshots — visual verification."""
    from repo_transmute.v2.vision.scorer import score_similarity
    
    click.echo(f"Comparing:\n  Source: {source_screenshot}\n  Target: {target_screenshot}")
    
    result = score_similarity(source_screenshot, target_screenshot)
    
    click.echo(f"\nOverall similarity: {result.overall_score:.0%}")
    if result.issues:
        click.echo("\nIssues:")
        for issue in result.issues:
            click.echo(f"  - {issue}")
    if result.suggestions:
        click.echo("\nSuggestions:")
        for s in result.suggestions:
            click.echo(f"  - {s}")


def _compute_migration_order(blueprint: ProjectBlueprint) -> list[str]:
    """Compute migration order using topological sort (dependencies first)."""
    # Simple topological sort
    deps = blueprint.dependencies
    visited = set()
    order = []
    
    def visit(name: str):
        if name in visited:
            return
        visited.add(name)
        for dep in deps.get(name, []):
            visit(dep)
        order.append(name)
    
    for comp in blueprint.components:
        visit(comp.name)
    
    return order


if __name__ == "__main__":
    v2()
