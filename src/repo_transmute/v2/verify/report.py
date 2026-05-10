"""Generate migration quality report."""

from __future__ import annotations

from pathlib import Path

from repo_transmute.v2.models import ProjectBlueprint, MigrationStatus


def generate_migration_report(
    blueprint: ProjectBlueprint,
    migration_results: dict,
    output_path: Path | None = None,
) -> str:
    """Generate a comprehensive migration quality report.
    
    Includes:
    - Overall migration status
    - Per-component results with vision scores
    - Issues and suggestions
    - Next steps
    """
    if output_path is None:
        output_path = Path("./migration_report.md")
    
    total = migration_results.get("total", 0)
    completed = migration_results.get("completed", 0)
    failed = migration_results.get("failed", 0)
    needs_fix = migration_results.get("needs_fix", 0)
    
    report = f"""# Migration Report

## Summary

| Metric | Value |
|--------|-------|
| Total Components | {total} |
| Completed | {completed} |
| Failed | {failed} |
| Needs Fix | {needs_fix} |
| Success Rate | {completed/total:.0%} |

## Per-Component Results

| Component | Status | Vision Score | Attempts |
|-----------|--------|-------------|----------|
"""
    
    for name, result in migration_results.get("components", {}).items():
        score = result.get("vision_score", "N/A")
        if isinstance(score, float) and score >= 0:
            score = f"{score:.0%}"
        report += f"| {name} | {result.get('status', '?')} | {score} | {result.get('attempts', '?')} |\n"
    
    report += f"""
## Issues

"""
    
    for name, result in migration_results.get("components", {}).items():
        if result.get("status") in (MigrationStatus.FAILED.value, MigrationStatus.NEEDS_FIX.value):
            report += f"### {name}\n"
            report += f"- Status: {result.get('status')}\n"
            report += f"- Attempts: {result.get('attempts', '?')}\n\n"
    
    output_path.write_text(report)
    return str(output_path)
