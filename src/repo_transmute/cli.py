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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _target_ext(target: str) -> str:
    """Return the canonical file extension for a target language name."""
    return {
        "typescript": "ts",
        "ts": "ts",
        "tsx": "ts",
        "javascript": "js",
        "js": "js",
        "jsx": "js",
        "rust": "rs",
        "python": "py",
    }.get(target.lower(), "txt")


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

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
@click.option("--max-functions", "-f", default=30, type=int, help="Maximum functions per chunk")
def pipeline(repo: str, target: str, output_dir: Path, cache_dir: Path, model: str, max_passes: int, max_functions: int):
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
    click.echo(f"Target: {target} | Max passes: {max_passes} | Max functions/chunk: {max_functions}")
    click.echo("="*50)
    
    # Initialize coordinator
    coordinator = PipelineCoordinator(
        target_lang=target,
        max_passes=max_passes,
        max_functions_per_chunk=max_functions
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
        click.echo(f"Chunks processed: {result.chunks_processed}/{result.total_chunks}")
        
        if result.files_written:
            click.echo(f"Files written: {len(result.files_written)}")
            for path in result.files_written[:10]:
                click.echo(f"  - {path}")
            if len(result.files_written) > 10:
                click.echo(f"  ... and {len(result.files_written) - 10} more")
        elif result.transpiled_code:
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
        
        ext = _target_ext(target)
        code_file = output_dir / f"{name}.{ext}"
        code_file.write_text(result.transpiled_code)
        click.echo(f"\nSaved transpiled code to {code_file}")
        
        test_file = output_dir / f"{name}.test.{ext}"
        test_file.write_text(result.tests)
        click.echo(f"Saved tests to {test_file}")
        
    else:
        click.echo(click.style(f"\n❌ Pipeline failed: {result.error}", fg="red"))


@cli.command()
@click.argument("repo", default="")
@click.option("--cache-dir", "-c", type=click.Path(path_type=Path), default=DEFAULT_CACHE_DIR, help="Cache directory for cloned repos")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=DEFAULT_OUTPUT_DIR, help="Output directory for chunks")
@click.option("--chunk-size", "-s", default=20, help="Maximum functions per chunk (for backward compat)")
def chunk(repo: str, cache_dir: Path, output_dir: Path, chunk_size: int = 20):
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
    
    click.echo(f"Chunking {repo} (max_functions={chunk_size})...")
    
    chunks = chunk_repository(repo_path, max_functions=chunk_size)
    
    click.echo(f"\nCreated {len(chunks)} chunks:")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for i, chunk in enumerate(chunks):
        click.echo(f"\nChunk {i+1}: {len(chunk.files)} files")
        for f in chunk.files[:5]:  # Show first 5 files
            click.echo(f"  - {f.relative_to(repo_path)}")
        if len(chunk.files) > 5:
            click.echo(f"  ... and {len(chunk.files) - 5} more")
        
        # Save chunk manifest
        chunk_data = {
            "chunk": i + 1,
            "total_chunks": len(chunks),
            "files": [str(f.relative_to(repo_path)) for f in chunk.files]
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
@click.argument("blueprint", required=False)
@click.option("--target", "-t", default=None, help="Target language (auto-detect from compatibility if not specified)")
@click.option("--output-dir", "-o", type=click.Path(path_type=Path), default=DEFAULT_RUST_DIR, help="Output directory for transpiled code")
@click.option("--model", "-m", default="MiniMax-M2.7", help="LLM model to use")
@click.option("--repo", "-r", default=None, help="Cached repo path or 'owner/repo' to use chunk mode")
@click.option("--chunk-id", "-i", "chunk_id", type=int, default=None, help="Chunk ID to transpile (0-based, requires --repo)")
@click.option("--cache-dir", "-c", type=click.Path(path_type=Path), default=DEFAULT_CACHE_DIR, help="Cache directory for cloned repos")
@click.option("--max-functions", "-f", default=30, type=int, help="Maximum functions per chunk (chunk mode only)")
def transpile(
    blueprint: str,
    target: str,
    output_dir: Path,
    model: str,
    repo: str,
    chunk_id: int,
    cache_dir: Path,
    max_functions: int,
):
    """Transpile a blueprint file OR a single chunk from a cached repository.

    Blueprint mode (transpile a saved YAML blueprint):
        repo-transmute transpile blueprints/HKUDS__nanobot.yaml -t typescript

    Chunk mode (transpile one chunk from a cached repo):
        repo-transmute transpile --repo HKUDS__nanobot --chunk-id 0 -t typescript
        repo-transmute transpile -r ChonSong/repo-transmute --chunk-id 3
    """
    # --- Chunk mode ---
    if repo is not None or chunk_id is not None:
        if chunk_id is None:
            raise click.ClickException("--chunk-id is required when using --repo")
        _transpile_single_chunk(
            repo=repo,
            chunk_id=chunk_id,
            target=target or "typescript",
            output_dir=output_dir,
            cache_dir=cache_dir,
            model=model,
            max_functions=max_functions,
        )
        return

    # --- Blueprint mode ---
    if not blueprint:
        raise click.ClickException(
            "Either a blueprint path or --repo is required.\n"
            "  Blueprint: repo-transmute transpile blueprints/repo.yaml -t typescript\n"
            "  Chunk:     repo-transmute transpile --repo owner/repo --chunk-id 0"
        )

    blueprint_path = Path(blueprint)
    if not blueprint_path.exists():
        raise click.ClickException(f"Blueprint file not found: {blueprint}")
    
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
        raise click.ClickException(f"Transpilation failed: {e}")
    
    click.echo(click.style("Done!", fg="green"))


def _transpile_single_chunk(
    repo: str,
    chunk_id: int,
    target: str,
    output_dir: Path,
    cache_dir: Path,
    model: str,
    max_functions: int,
):
    """Transpile one chunk from a cached repository (not a Click command)."""
    # Resolve repo path
    if "/" in repo:
        owner, name = repo.split("/", 1)
        repo_path = cache_dir / f"{owner}__{name}"
    else:
        # Short name — look for any cached repo whose folder name ends with the given string
        candidates = list(cache_dir.glob(f"*{repo}*"))
        if not candidates:
            raise click.ClickException(
                f"No cached repo matching '{repo}' found in {cache_dir}.\n"
                "Run 'repo-transmute ingest owner/repo' first to cache it."
            )
        if len(candidates) > 1:
            lines = [f"Ambiguous repo '{repo}'. Matches:"]
            lines.extend(f"  {c.name}" for c in candidates)
            raise click.ClickException("\n".join(lines))
        repo_path = candidates[0]

    if not repo_path.exists():
        raise click.ClickException(
            f"Cached repo not found at {repo_path}.\n"
            "Run 'repo-transmute ingest owner/repo' first to cache it."
        )

    # Detect language and create chunks
    language = detect_language(repo_path)
    click.echo(f"Detected language: {language}")

    chunks = chunk_repository(repo_path, max_functions=max_functions)
    total = len(chunks)

    if chunk_id < 0 or chunk_id >= total:
        raise click.ClickException(
            f"chunk {chunk_id} out of range. Available: 0–{total - 1}"
        )

    chunk = chunks[chunk_id]
    click.echo(f"\nChunk {chunk_id}/{total - 1}: {len(chunk.files)} files")
    for f in chunk.files:
        click.echo(f"  - {f.relative_to(repo_path)}")

    coordinator = PipelineCoordinator(
        target_lang=target,
        max_passes=1,
        max_functions_per_chunk=max_functions,
        model=model,
    )

    click.echo(f"\nTranspiling (target={target})...")
    try:
        result = coordinator.transpile_chunk(
            chunk=chunk,
            repo_path=repo_path,
            language=language,
            output_dir=output_dir,
        )
    except Exception as e:
        raise click.ClickException(f"Transpile failed: {e}")

    click.echo("\n--- Transpiled Code ---")
    click.echo(result)
    click.echo("--- End ---\n")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = _target_ext(target)
        out_file = output_dir / f"chunk{chunk_id:03d}.{suffix}"
        out_file.write_text(result)
        click.echo(click.style(f"Saved → {out_file}", fg="green"))


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
