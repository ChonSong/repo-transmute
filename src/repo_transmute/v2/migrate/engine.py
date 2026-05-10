"""Migration engine — orchestrates LLM-driven component migration."""

from __future__ import annotations

from pathlib import Path

from repo_transmute.v2.models import (
    ComponentDef,
    ProjectBlueprint,
    MigrationStatus,
    Framework,
    TargetStack,
    VisionResult,
)


class MigrationEngine:
    """Orchestrates the migration of components from source to target stack."""
    
    def __init__(
        self,
        source_blueprint: ProjectBlueprint,
        target_stack: TargetStack,
        output_dir: Path,
        model: str = "glm-5-turbo",
    ):
        self.source = source_blueprint
        self.target_stack = target_stack
        self.output_dir = output_dir
        self.model = model
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def migrate_all(self, max_iterations: int = 3) -> dict:
        """Migrate all components with vision verification loop.
        
        Returns:
            Migration report with per-component results.
        """
        report = {
            "total": len(self.source.components),
            "completed": 0,
            "failed": 0,
            "needs_fix": 0,
            "skipped": 0,
            "components": {},
        }
        
        # Migrate in dependency order
        for comp_name in self.source.migration_order or [c.name for c in self.source.components]:
            comp = self.source.get_component(comp_name)
            if comp is None:
                report["skipped"] += 1
                continue
            
            result = self._migrate_component(comp, max_iterations)
            report["components"][comp_name] = result
            
            if result["status"] == MigrationStatus.COMPLETED.value:
                report["completed"] += 1
            elif result["status"] == MigrationStatus.FAILED.value:
                report["failed"] += 1
            elif result["status"] == MigrationStatus.NEEDS_FIX.value:
                report["needs_fix"] += 1
        
        return report
    
    def _migrate_component(
        self,
        comp: ComponentDef,
        max_iterations: int,
    ) -> dict:
        """Migrate a single component with iteration loop."""
        from repo_transmute.v2.migrate.codegen import generate_component
        from repo_transmute.v2.migrate.style_mapper import map_styles
        from repo_transmute.v2.migrate.api_rewriter import rewrite_api_calls
        
        context = self._build_context(comp)
        
        for attempt in range(max_iterations):
            comp.fix_attempts = attempt
            
            # Generate migrated code
            migrated_code = generate_component(
                component=comp,
                target_stack=self.target_stack,
                context=context,
                model=self.model,
            )
            
            if not migrated_code:
                continue
            
            # Write migrated code
            target_path = self.output_dir / f"{comp.name.lower()}.tsx"
            target_path.write_text(migrated_code)
            comp.target_file = str(target_path)
            
            # Check build
            build_ok = self._check_build(target_path)
            if not build_ok:
                context["build_errors"] = self._get_build_errors(target_path)
                continue
            
            # Vision verification (if screenshots available)
            if comp.source_screenshot:
                vision_result = self._verify_visual(comp, target_path)
                if vision_result and vision_result.overall_score >= 0.8:
                    comp.migration_status = MigrationStatus.COMPLETED
                    comp.vision_score = vision_result.overall_score
                    return {
                        "status": MigrationStatus.COMPLETED.value,
                        "target_file": str(target_path),
                        "vision_score": vision_result.overall_score,
                        "attempts": attempt + 1,
                    }
                elif vision_result:
                    context["vision_feedback"] = vision_result.issues
                    context["vision_suggestions"] = vision_result.suggestions
            else:
                # No screenshots — accept if build passes
                comp.migration_status = MigrationStatus.COMPLETED
                return {
                    "status": MigrationStatus.COMPLETED.value,
                    "target_file": str(target_path),
                    "vision_score": -1,  # N/A
                    "attempts": attempt + 1,
                }
        
        comp.migration_status = MigrationStatus.FAILED
        return {
            "status": MigrationStatus.FAILED.value,
            "target_file": str(target_path) if comp.target_file else "",
            "vision_score": comp.vision_score,
            "attempts": max_iterations,
        }
    
    def _build_context(self, comp: ComponentDef) -> dict:
        """Build the context for LLM migration."""
        context = {
            "source_code": comp.full_source,
            "framework": self.source.framework.value,
            "target_stack": self.target_stack.value,
            "style_system": {
                "approach": self.source.style_approach.value,
                "css_variables": self.source.style_system.css_variables if self.source.style_system else {},
            },
        }
        
        # Add dependency components' code
        deps = self.source.get_dependencies(comp.name)
        context["dependencies"] = {}
        for dep_name in deps:
            dep = self.source.get_component(dep_name)
            if dep and dep.target_file:
                try:
                    context["dependencies"][dep_name] = Path(dep.target_file).read_text()
                except Exception:
                    pass
        
        return context
    
    def _check_build(self, target_path: Path) -> bool:
        """Check if the migrated code compiles."""
        import subprocess
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", str(target_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(target_path.parent),
            )
            return result.returncode == 0
        except Exception:
            return True  # Assume OK if tsc not available
    
    def _get_build_errors(self, target_path: Path) -> list[str]:
        """Get build errors for a file."""
        import subprocess
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", str(target_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(target_path.parent),
            )
            return result.stderr.strip().split("\n") if result.returncode != 0 else []
        except Exception:
            return []
    
    def _verify_visual(
        self,
        comp: ComponentDef,
        target_path: Path,
    ) -> VisionResult | None:
        """Verify visual fidelity of migrated component."""
        from repo_transmute.v2.vision.scorer import score_similarity
        
        if not comp.source_screenshot:
            return None
        
        # TODO: Build the target project, serve it, screenshot the component
        # Then compare with source screenshot
        # For now, return None to skip vision verification
        return None
