"""CLI for repo-transmute."""

from pathlib import Path

import click
import yaml

from repo_transmute.ingestion.clone import clone_repo
from repo_transmute.ingestion.detector import detect_language
from repo_transmute.blueprint.extractor import extract_all
from repo_transmute.blueprint.storage import save_blueprint, load_blueprint
from repo_transmute.transpiler.llm import transpile_with_llm
from repo_transmute.transpiler.compatibility import check_compatibility, get_recommended_target
from repo_transmute.transpiler.validate import validate

# Pipeline imports
from repo_transmute.pipeline import (
    PipelineCoordinator,
    chunk_repository,
    analyze_dependencies,
)


# Default directories
DEFAULT_CACHE_DIR = Path("./data/cache")
DEFAULT_OUTPUT_DIR = Path("./data/blueprints")
DEFAULT_RUST_DIR = Path("./data/outputs")


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """RepoTransmute - AI-powered code transpilation."""
    pass


@cli.command()
@click.argument("repo", default="")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=DEFAULT_OUTPUT_DIR, help="Output directory for blueprints")
@click.option("--cache-dir", "-c", type=click.Path(path_type=Path), default=DEFAULT_CACHE_DIR, help="Cache directory for cloned repos")
@click.option("--target", "-t", default=None, help="Target language (auto-detected if not specified)")
def ingest(repo: str, output_dir: Path, cache_dir: Path, target: str):
    """Clone repo and extract blueprint."""
    if not repo:
        click.echo("Error: repo argument required", err=True)
        return
        
    if "/" not in repo:
        click.echo(f"Error: Invalid format. Use 'owner/repo'", err=True)
        return
    
    owner, name = repo.split("/", 1)
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    click.echo(f"Cloning {repo}...")
    try:
        repo_path = clone_repo(owner, name, cache_dir)
        click.echo(f"Cloned to {repo_path}")
    except Exception as e:
        click.echo(f"Error cloning repo: {e}", err=True)
        return
    
    click.echo("Detecting language...")
    try:
        language = detect_language(repo_path)
        if not language:
            click.echo("Warning: Could not detect language", err=True)
            language = "unknown"
        click.echo(f"Detected: {language}")
    except Exception as e:
        click.echo(f"Error detecting language: {e}", err=True)
        return
    
    try:
        blueprint = extract_all(repo_path, language)
        file_count = len(list(repo_path.rglob("*.py"))) + len(list(repo_path.rglob("*.js"))) + len(list(repo_path.rglob("*.ts")))
        function_count = len(blueprint.functions)
    except Exception as e:
        click.echo(f"Error analyzing repo: {e}", err=True)
        file_count = 0
        function_count = 0
    
    click.echo("\n" + "="*50)
    click.echo("COMPATIBILITY CHECK")
    click.echo("="*50)
    
    compatibility = check_compatibility(
        source_lang=language,
        target_lang=target,
        file_count=file_count,
        function_count=function_count
    )
    
    click.echo(f"Source Language: {language}")
    click.echo(f"Recommended Target: {compatibility.recommended_target or 'N/A'}")
    click.echo(f"Confidence: {compatibility.confidence:.0%}")
    click.echo(f"Complexity Score: {compatibility.complexity_score}/10")
    
    if compatibility.warnings:
        click.echo("\nWarnings:")
        for warning in compatibility.warnings:
            click.echo(f"  ⚠ {warning}")
    
    if not compatibility.compatible:
        click.echo(click.style("\n❌ NOT COMPATIBLE - Skipping transpilation", fg="red"))
    
    click.echo("\nExtracting blueprint...")
    try:
        if 'blueprint' not in dir():
            blueprint = extract_all(repo_path, language)
        click.echo(f"Found {len(blueprint.functions)} functions")
        click.echo(f"Found {len(blueprint.data_structures)} data structures")
    except Exception as e:
        click.echo(f"Error extracting blueprint: {e}", err=True)
        return
    
    click.echo("Saving blueprint...")
    try:
        output_path = save_blueprint(blueprint, output_dir)
        click.echo(f"Saved to {output_path}")
    except Exception as e:
        click.echo(f"Error saving blueprint: {e}", err=True)
        return
    
    click.echo(click.style("\n✅ Done!", fg="green"))


@cli.command()
@click.argument("repo", default="")
@click.option("--target", "-t", default="typescript", help="Target language")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=DEFAULT_RUST_DIR, help="Output directory for transpiled code")
@click.option("--cache-dir", "-c", type=click.Path(path_type=Path), default=DEFAULT_CACHE_DIR, help="Cache directory for cloned repos")
@click.option("--model", "-m", default="MiniMax-M2.7", help="LLM model to use")
@click.option("--max-passes", "-p", default=2, help="Maximum refinement passes")
def pipeline(repo: str, target: str, output_dir: Path, cache_dir: Path, model: str, max_passes: int):
    """Run full pipeline: ingest -> transpile -> test -> validate.
    
    Example:
        repo-transmute pipeline octocat/Hello-World -t typescript
    """
    if not repo:
        click.echo("Error: repo argument required", err=True)
        return
    
    if "/" not in repo:
        click.echo(f"Error: Invalid format. Use 'owner/repo'", err=True)
        return
    
    click.echo(f"Starting full pipeline for {repo}...")
    click.echo(f"Target: {target} | Max passes: {max_passes}")
    click.echo("="*50)
    
    # Initialize coordinator
    coordinator = PipelineCoordinator(
        max_passes=max_passes,
        model=model,
        target_lang=target
    )
    
    # Run pipeline
    result = coordinator.run_full_pipeline(
        repo=repo,
        cache_dir=cache_dir,
        output_dir=output_dir
    )
    
    if result.success:
        click.echo(click.style("\n✅ Pipeline completed successfully!", fg="green"))
        click.echo(f"Passes run: {result.passes_run}")
        
        if result.transpiled_code:
            click.echo("\nTranspiled code (first 500 chars):")
            click.echo(result.transpiled_code[:500])
        
        if result.validation:
            click.echo("\nValidation Report:")
            click.echo(f"  Import valid: {result.validation.import_valid}")
            click.echo(f"  Type valid: {result.validation.type_valid}")
            if result.validation.errors:
                click.echo("  Errors:")
                for err in result.validation.errors:
                    click.echo(f"    - {err}")
        
        # Save outputs
        output_dir.mkdir(parents=True, exist_ok=True)
        owner, name = repo.split("/", 1)
        
        code_file = output_dir / f"{name}.{target[:3]}"
        code_file.write_text(result.transpiled_code)
        click.echo(f"\nSaved transpiled code to {code_file}")
        
        test_file = output_dir / f"{name}.test.{target[:3]}"
        test_file.write_text(result.tests)
        click.echo(f"Saved tests to {test_file}")
        
    else:
        click.echo(click.style(f"\n❌ Pipeline failed: {result.error}", fg="red"))


@cli.command()
@click.argument("repo", default="")
@click.option("--cache-dir", "-c", type=click.Path(path_type=Path), default=DEFAULT_CACHE_DIR, help="Cache directory for cloned repos")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=DEFAULT_OUTPUT_DIR, help="Output directory for chunks")
@click.option("--chunk-size", "-s", default=20, help="Files per chunk")
def chunk(repo: str, cache_dir: Path, output_dir: Path, chunk_size: int):
    """Chunk repository into smaller pieces for processing.
    
    Example:
        repo-transmute chunk octocat/Hello-World -s 15
    """
    if not repo:
        click.echo("Error: repo argument required", err=True)
        return
    
    if "/" not in repo:
        click.echo(f"Error: Invalid format. Use 'owner/repo'", err=True)
        return
    
    owner, name = repo.split("/", 1)
    repo_path = cache_dir / f"{owner}__{name}"
    
    # Clone if not cached
    if not repo_path.exists():
        click.echo(f"Cloning {repo}...")
        try:
            repo_path = clone_repo(owner, name, cache_dir)
        except Exception as e:
            click.echo(f"Error cloning repo: {e}", err=True)
            return
    
    click.echo(f"Chunking {repo} (chunk size: {chunk_size})...")
    
    chunks = chunk_repository(repo_path, chunk_size)
    
    click.echo(f"\nCreated {len(chunks)} chunks:")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for i, chunk_files in enumerate(chunks):
        click.echo(f"\nChunk {i+1}: {len(chunk_files)} files")
        for f in chunk_files[:5]:  # Show first 5 files
            click.echo(f"  - {f.relative_to(repo_path)}")
        if len(chunk_files) > 5:
            click.echo(f"  ... and {len(chunk_files) - 5} more")
        
        # Save chunk manifest
        chunk_data = {
            "chunk": i + 1,
            "total_chunks": len(chunks),
            "files": [str(f.relative_to(repo_path)) for f in chunk_files]
        }
        chunk_file = output_dir / f"{name}.chunk{i+1}.yaml"
        chunk_file.write_text(yaml.dump(chunk_data))
    
    click.echo(click.style(f"\n✅ Chunking complete!", fg="green"))
    click.echo(f"Chunk manifests saved to {output_dir}")


@cli.command()
@click.argument("repo", default="")
@click.option("--cache-dir", "-c", type=click.Path(path_type=Path), default=DEFAULT_CACHE_DIR, help="Cache directory for cloned repos")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None, help="Output file for dependency analysis")
def deps(repo: str, cache_dir: Path, output: Path):
    """Analyze repository dependencies.
    
    Example:
        repo-transmute deps octocat/Hello-World -o deps.yaml
    """
    if not repo:
        click.echo("Error: repo argument required", err=True)
        return
    
    if "/" not in repo:
        click.echo(f"Error: Invalid format. Use 'owner/repo'", err=True)
        return
    
    owner, name = repo.split("/", 1)
    repo_path = cache_dir / f"{owner}__{name}"
    
    # Clone if not cached
    if not repo_path.exists():
        click.echo(f"Cloning {repo}...")
        try:
            repo_path = clone_repo(owner, name, cache_dir)
        except Exception as e:
            click.echo(f"Error cloning repo: {e}", err=True)
            return
    
    click.echo(f"Analyzing dependencies for {repo}...")
    
    dependency_info = analyze_dependencies(repo_path)
    
    click.echo("\n" + "="*50)
    click.echo("DEPENDENCY ANALYSIS")
    click.echo("="*50)
    click.echo(f"Total files: {dependency_info.get('file_count', 0)}")
    click.echo(f"External dependencies: {len(dependency_info.get('external', []))}")
    click.echo(f"Internal imports: {len(dependency_info.get('internal', []))}")
    
    if dependency_info.get('external'):
        click.echo("\nExternal dependencies:")
        for dep in dependency_info['external'][:10]:
            click.echo(f"  - {dep}")
        if len(dependency_info['external']) > 10:
            click.echo(f"  ... and {len(dependency_info['external']) - 10} more")
    
    if dependency_info.get('internal'):
        click.echo("\nInternal imports:")
        for imp in dependency_info['internal'][:10]:
            click.echo(f"  - {imp}")
        if len(dependency_info['internal']) > 10:
            click.echo(f"  ... and {len(dependency_info['internal']) - 10} more")
    
    # Save to output if specified
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(yaml.dump(dependency_info))
        click.echo(click.style(f"\n✅ Saved to {output}", fg="green"))
    else:
        click.echo(click.style("\n✅ Done!", fg="green"))


@cli.command()
@click.argument("blueprint")
@click.option("--target", "-t", default=None, help="Target language (auto-detect from compatibility if not specified)")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=DEFAULT_RUST_DIR, help="Output directory for transpiled code")
@click.option("--model", "-m", default="MiniMax-M2.7", help="LLM model to use")
def transpile(blueprint: str, target: str, output_dir: Path, model: str):
    """Transpile a blueprint to target language."""
    blueprint_path = Path(blueprint)
    
    if not blueprint_path.exists():
        click.echo(f"Error: Blueprint file not found: {blueprint}", err=True)
        return
    
    if not target:
        bp = load_blueprint(blueprint_path)
        target = get_recommended_target(bp.language) or "typescript"
        click.echo(f"Auto-detected target: {target}")
    
    click.echo(f"Transpiling {blueprint_path} to {target}...")
    
    try:
        result = transpile_with_llm(blueprint_path, target, output_dir, model)
        click.echo("Transpiled code:")
        click.echo(result[:500] + "..." if len(result) > 500 else result)
        
        if output_dir:
            click.echo(click.style(f"\nSaved to {output_dir}/", fg="green"))
            
    except Exception as e:
        click.echo(f"Error transpiling: {e}", err=True)
        return
    
    click.echo(click.style("Done!", fg="green"))


@cli.command()
@click.argument("file")
@click.option("--language", "-l", required=True, help="Language (typescript, rust, python)")
def validate_cmd(file: str, language: str):
    """Validate transpiled code."""
    file_path = Path(file)
    if not file_path.exists():
        click.echo(f"Error: File not found: {file}", err=True)
        return
    
    click.echo(f"Validating {file_path} ({language})...")
    result = validate(file_path, language)
    
    if result.success:
        click.echo(click.style("✅ " + result.output, fg="green"))
    else:
        click.echo(click.style("❌ Validation failed", fg="red"))
        if result.error:
            click.echo(result.error[:500])


@cli.command()
@click.argument("query", required=False)
def search(query: str):
    """Search indexed blueprints (requires Phase 4: TXTAI integration)."""
    if not query:
        click.echo("Query required.")
        return
    click.echo(f"Searching for: {query}")
    click.echo("Search requires TXTAI integration (Phase 4).")


@cli.command()
def status():
    """Show status and statistics."""
    cache_dir = DEFAULT_CACHE_DIR
    output_dir = DEFAULT_OUTPUT_DIR
    
    click.echo("RepoTransmute Status")
    click.echo("=" * 40)
    click.echo(f"Cache dir: {cache_dir}")
    click.echo(f"Output dir: {output_dir}")
    
    if cache_dir.exists():
        repos = list(cache_dir.glob("*__*"))
        click.echo(f"Cached repos: {len(repos)}")
    
    if output_dir.exists():
        blueprints = list(output_dir.glob("*.yaml"))
        click.echo(f"Saved blueprints: {len(blueprints)}")


if __name__ == "__main__":
    cli()


# ═══════════════════════════════════════════════════════════════════
# Frontend Migration Commands
# ═══════════════════════════════════════════════════════════════════

@cli.command()
@click.argument("source_path", type=click.Path(path_type=Path))
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=Path("./data/frontend"), help="Output directory for frontend blueprint")
def frontend_blueprint(source_path: Path, output_dir: Path):
    """Extract frontend blueprint from a project (components, routes, CSS, APIs)."""
    from repo_transmute.frontend import extract_frontend_blueprint
    
    if not source_path.exists():
        click.echo(f"Error: {source_path} does not exist", err=True)
        return
    
    click.echo(f"Extracting frontend blueprint from {source_path}...")
    blueprint = extract_frontend_blueprint(source_path)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "frontend_blueprint.yaml"
    output_file.write_text(yaml.dump(blueprint, default_flow_style=False, sort_keys=False))
    
    click.echo(f"Frontend blueprint saved to {output_file}")
    click.echo(f"  Components: {blueprint['summary']['total_components']}")
    click.echo(f"  Routes: {blueprint['summary']['total_routes']}")
    click.echo(f"  CSS files with themes: {blueprint['summary']['total_css_files']}")
    click.echo(f"  API patterns: {blueprint['summary']['total_api_patterns']}")


@cli.command()
@click.argument("source_path", type=click.Path(path_type=Path))
@click.option("--target-path", "-t", type=click.Path(path_type=Path), default=None, help="Path to target project for comparison")
def theme_analysis(source_path: Path, target_path: Path | None):
    """Analyze theme system compatibility between source and target projects."""
    from repo_transmute.frontend import extract_css_theme_system, map_theme_compatibility
    
    click.echo(f"Analyzing source theme system: {source_path}")
    source_system = extract_css_theme_system(source_path)
    
    click.echo(f"  Approach: {source_system.theme_approach}")
    click.echo(f"  Themes: {len(source_system.themes)}")
    click.echo(f"  CSS variables: {len(source_system.css_variables)}")
    click.echo(f"  Utility classes: {len(source_system.global_utilities)}")
    
    if target_path:
        click.echo(f"\nAnalyzing target theme system: {target_path}")
        target_system = extract_css_theme_system(target_path)
        
        click.echo(f"  Approach: {target_system.theme_approach}")
        click.echo(f"  Themes: {len(target_system.themes)}")
        
        compat = map_theme_compatibility(source_system, target_system)
        click.echo(f"\nCompatibility: {compat['compatibility_score']:.0%}")
        click.echo(f"  Common variables: {len(compat['common_variables'])}")
        click.echo(f"  Source-only: {len(compat['source_only_variables'])}")
        click.echo(f"  Target-only: {len(compat['target_only_variables'])}")
        click.echo(f"\n  {compat['recommendation']}")


@cli.command()
@click.argument("source_path", type=click.Path(path_type=Path))
@click.option("--target-path", "-t", type=click.Path(path_type=Path), default=None, help="Path to target project")
@click.option("--output", "-o", type=click.Path(path_type=Path), default=Path("./data/api_mapping.yaml"))
def api_analysis(source_path: Path, target_path: Path | None, output: Path):
    """Analyze API call patterns and generate migration blueprint."""
    from repo_transmute.frontend import generate_api_migration_blueprint
    
    click.echo(f"Analyzing API calls in {source_path}...")
    blueprint = generate_api_migration_blueprint(source_path, target_path)
    
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.dump(blueprint, default_flow_style=False, sort_keys=False))
    
    click.echo(f"API migration blueprint saved to {output}")
    click.echo(f"  Source APIs: {blueprint['source_api_count']}")
    click.echo(f"  Target APIs: {blueprint['target_api_count']}")
    click.echo(f"  Rewrite rules: {len(blueprint['rewrite_rules'])}")
    click.echo(f"  Streaming APIs: {len(blueprint['streaming_apis'])}")
    click.echo(f"\n  {blueprint['recommendation']}")


@cli.command()
@click.argument("source_path", type=click.Path(path_type=Path))
@click.argument("target_path", type=click.Path(path_type=Path))
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=Path("./data/migrated"))
@click.option("--framework", "-f", default="react", help="Source framework (react, next.js, etc.)")
@click.option("--style", "-s", default="tailwind", help="Source CSS approach (tailwind, css-vars, etc.)")
@click.option("--dry-run", is_flag=True, help="Show plan without executing")
def frontend_migrate(source_path: Path, target_path: Path, output_dir: Path,
                     framework: str, style: str, dry_run: bool):
    """Run full frontend migration: components + themes + APIs."""
    from repo_transmute.frontend import (
        extract_frontend_blueprint,
        extract_css_theme_system,
        map_theme_compatibility,
        generate_api_migration_blueprint,
    )
    from repo_transmute.transpiler.compatibility import check_frontend_compatibility
    
    click.echo("╔══════════════════════════════════════════════╗")
    click.echo("║   Frontend Migration Analysis               ║")
    click.echo("╚══════════════════════════════════════════════╝\n")
    
    # Step 1: Extract blueprints
    click.echo("[1/4] Extracting source frontend blueprint...")
    source_bp = extract_frontend_blueprint(source_path)
    click.echo(f"  Found {source_bp['summary']['total_components']} components, {source_bp['summary']['total_routes']} routes")
    
    # Step 2: Theme analysis
    click.echo("\n[2/4] Analyzing theme systems...")
    source_css = extract_css_theme_system(source_path)
    target_css = extract_css_theme_system(target_path)
    theme_compat = map_theme_compatibility(source_css, target_css)
    click.echo(f"  Compatibility: {theme_compat['compatibility_score']:.0%}")
    click.echo(f"  {theme_compat['recommendation']}")
    
    # Step 3: API analysis
    click.echo("\n[3/4] Analyzing API patterns...")
    api_bp = generate_api_migration_blueprint(source_path, target_path)
    click.echo(f"  {api_bp['recommendation']}")
    
    # Step 4: Compatibility check
    click.echo("\n[4/4] Checking overall compatibility...")
    compat = check_frontend_compatibility(
        framework, style,
        component_count=source_bp['summary']['total_components'],
        has_ssr=False,
    )
    click.echo(f"  Confidence: {compat.confidence:.0%}")
    click.echo(f"  Complexity: {compat.complexity_score}/10")
    for w in compat.warnings:
        click.echo(f"  ⚠ {w}")
    
    if dry_run:
        click.echo("\n[Dry run — no files written]")
        return
    
    # Save migration plan
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = {
        'source_blueprint': source_bp,
        'theme_compatibility': theme_compat,
        'api_migration': api_bp,
        'compatibility': {
            'confidence': compat.confidence,
            'complexity': compat.complexity_score,
            'warnings': compat.warnings,
        },
    }
    plan_file = output_dir / "migration_plan.yaml"
    plan_file.write_text(yaml.dump(plan, default_flow_style=False, sort_keys=False))
    click.echo(f"\nMigration plan saved to {plan_file}")
