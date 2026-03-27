"""Pipeline coordinator for RepoTransmute - multi-pass transpilation with refinement."""

import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

import yaml
from tqdm import tqdm

from repo_transmute.blueprint import Blueprint, load_blueprint
from repo_transmute.blueprint.extractor import extract_all
from repo_transmute.blueprint.storage import save_blueprint
from repo_transmute.ingestion.clone import clone_repo
from repo_transmute.ingestion.detector import detect_language
from repo_transmute.transpiler.llm import Transpiler
from repo_transmute.transpiler.prompts import build_transpile_prompt
from repo_transmute.transpiler.chunker import (
    chunk_repository,
    create_chunks,
    Chunk,
    Reassembler,
    extract_imports,
    extract_exports,
)


# Default directories
DEFAULT_CACHE_DIR = Path("./data/cache")
DEFAULT_OUTPUT_DIR = Path("./data/blueprints")
DEFAULT_RUST_DIR = Path("./data/outputs")


@dataclass
class ValidationReport:
    """Report from integration validation."""
    import_valid: bool = True
    type_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.import_valid and self.type_valid


@dataclass
class PipelineResult:
    """Result from running the full pipeline."""
    success: bool
    transpiled_code: str = ""
    tests: str = ""
    validation: Optional[ValidationReport] = None
    passes_run: int = 0
    chunks_processed: int = 0
    total_chunks: int = 0
    error: Optional[str] = None
    files_written: List[str] = field(default_factory=list)


@dataclass
class ChunkProgress:
    """Progress tracking for chunk processing."""
    chunk_id: int
    status: str  # pending, processing, completed, failed
    files: List[str]
    functions: int = 0
    error: Optional[str] = None


class IntegrationValidator:
    """Validates transpiled code for import and type correctness."""

    def __init__(self, target_lang: str = "typescript"):
        self.target_lang = target_lang
        self.current_code = ""
        self.import_errors: List[str] = []
        self.type_errors: List[str] = []

    def validate_imports(self, code: str) -> bool:
        """Validate that all imports are valid for the target language."""
        self.current_code = code
        self.import_errors = []

        if self.target_lang in ("typescript", "javascript", "ts", "js"):
            return self._validate_ts_imports(code)
        elif self.target_lang == "rust":
            return self._validate_rust_imports(code)
        elif self.target_lang == "python":
            return self._validate_python_imports(code)

        return True

    def _validate_ts_imports(self, code: str) -> bool:
        """Validate TypeScript/JavaScript imports."""
        import_pattern = r"(?:import|from)\s+['\"]([^'\"]+)['\"]"
        imports = re.findall(import_pattern, code)

        for imp in imports:
            if imp.startswith("..") or imp.startswith("."):
                if not imp.endswith((".ts", ".tsx", ".js", ".jsx", ".json")):
                    self.import_errors.append(f"Missing extension in relative import: {imp}")

        return len(self.import_errors) == 0

    def _validate_rust_imports(self, code: str) -> bool:
        """Validate Rust imports."""
        use_pattern = r"use\s+([^;]+);"
        uses = re.findall(use_pattern, code)

        for use in uses:
            if "::" in use:
                parts = use.split("::")
                if not parts[-1].replace("{", "").replace("}", "").replace("*", "").replace("as", "").strip().isidentifier():
                    self.import_errors.append(f"Invalid use statement: use {use}")

        return len(self.import_errors) == 0

    def _validate_python_imports(self, code: str) -> bool:
        """Validate Python imports."""
        import_patterns = [
            r"^import\s+(\S+)",
            r"^from\s+(\S+)\s+import",
        ]

        for pattern in import_patterns:
            matches = re.findall(pattern, code, re.MULTILINE)
            for module in matches:
                if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$", module):
                    self.import_errors.append(f"Invalid import: {module}")

        return len(self.import_errors) == 0

    def validate_types(self, code: str) -> bool:
        """Validate type annotations are correct."""
        self.type_errors = []

        if self.target_lang in ("typescript", "ts"):
            return self._validate_ts_types(code)
        elif self.target_lang == "python":
            return self._validate_python_types(code)

        return True

    def _validate_ts_types(self, code: str) -> bool:
        """Validate TypeScript type annotations."""
        any_matches = re.findall(r":\s*any\b", code)
        if any_matches:
            self.type_errors.append(f"Found {len(any_matches)} 'any' type annotations")

        if "interface" not in code and "type" not in code and "class" in code:
            self.type_errors.append("No type definitions found (consider using interfaces)")

        return len(self.type_errors) == 0

    def _validate_python_types(self, code: str) -> bool:
        """Validate Python type hints."""
        if "Optional[" in code or "List[" in code or "Dict[" in code:
            if "from typing import" not in code and "import typing" not in code:
                self.type_errors.append("Using typing constructs without importing typing")

        return len(self.type_errors) == 0

    def generate_report(self) -> ValidationReport:
        """Generate a validation report."""
        return ValidationReport(
            import_valid=len(self.import_errors) == 0,
            type_valid=len(self.type_errors) == 0,
            errors=self.import_errors + self.type_errors,
            warnings=[]
        )


def generate_module_tests(chunk_files: List[Path], target_lang: str = "typescript") -> str:
    """Generate Jest/Vitest tests for each module."""
    if target_lang in ("typescript", "javascript", "ts", "js"):
        return _generate_js_tests(chunk_files)
    elif target_lang == "python":
        return _generate_python_tests(chunk_files)
    elif target_lang == "rust":
        return _generate_rust_tests(chunk_files)

    return "# Tests not supported for this language"


def _generate_js_tests(chunk_files: List[Path]) -> str:
    """Generate Jest/Vitest tests for JavaScript/TypeScript."""
    test_lines = [
        "import { describe, it, expect, beforeEach } from 'vitest';",
        "",
    ]

    modules: dict[str, List[Path]] = {}
    for f in chunk_files:
        module_name = f.parent.name if f.parent.name not in ("src", "lib", "app") else f.stem
        if module_name not in modules:
            modules[module_name] = []
        modules[module_name].append(f)

    for module_name, files in modules.items():
        test_lines.append(f"describe('{module_name}', {{")
        test_lines.append("  let module;")
        test_lines.append("")
        test_lines.append("  beforeEach(() => {")
        test_lines.append(f"    // Setup for {module_name}")
        test_lines.append("  });")
        test_lines.append("")

        for file in files:
            content = file.read_text()

            func_patterns = [
                r"export\s+(?:const|let|var|function)\s+(\w+)",
                r"export\s+async\s+function\s+(\w+)",
                r"export\s+default\s+(?:function|const)",
            ]

            for pattern in func_patterns:
                matches = re.findall(pattern, content)
                for func_name in matches:
                    test_lines.append(f"  it('should export {func_name}', () => {{")
                    test_lines.append(f"    expect(typeof {func_name}).toBe('function');")
                    test_lines.append("  });")
                    test_lines.append("")

        test_lines.append("});")
        test_lines.append("")

    test_lines.append("describe('Integration', () => {")
    test_lines.append("  it('should handle end-to-end flow', () => {")
    test_lines.append("    // TODO: Add integration test")
    test_lines.append("    expect(true).toBe(true);")
    test_lines.append("  });")
    test_lines.append("});")

    return "\n".join(test_lines)


def _generate_python_tests(chunk_files: List[Path]) -> str:
    """Generate pytest tests for Python."""
    test_lines = [
        '"""Auto-generated tests for transpiled module."""',
        "import pytest",
        "from pathlib import Path",
        "",
    ]

    modules: dict[str, List[Path]] = {}
    for f in chunk_files:
        module_name = f.stem
        if module_name not in modules:
            modules[module_name] = []
        modules[module_name].append(f)

    for module_name, files in modules.items():
        classes = set()
        functions = set()

        for file in files:
            content = file.read_text()
            classes.update(re.findall(r"^class\s+(\w+)", content, re.MULTILINE))
            functions.update(re.findall(r"^(?:async\s+)?def\s+(\w+)\s*\(", content, re.MULTILINE))

        if classes:
            test_lines.append(f"class Test{module_name.title()}:")
            for cls in classes:
                test_lines.append(f"    def test_{cls.lower()}_instantiation(self):")
                test_lines.append(f"        # TODO: Test {cls}")
                test_lines.append(f"        assert True")
                test_lines.append("")

        for func in functions:
            if not func.startswith("_"):
                test_lines.append(f"def test_{func}():")
                test_lines.append(f"    # TODO: Test {func}")
                test_lines.append("    assert True")
                test_lines.append("")

    return "\n".join(test_lines)


def _generate_rust_tests(chunk_files: List[Path]) -> str:
    """Generate Rust tests."""
    test_lines = [
        "// Auto-generated tests",
        "#[cfg(test)]",
        "mod tests {",
        "    use super::*;",
        "",
    ]

    modules: dict[str, List[Path]] = {}
    for f in chunk_files:
        module_name = f.stem
        if module_name not in modules:
            modules[module_name] = []
        modules[module_name].append(f)

    for module_name, files in modules.items():
        for file in files:
            content = file.read_text()

            func_pattern = r"#\[(test|pub)\]\s*(?:async\s+)?fn\s+(\w+)"
            matches = re.findall(func_pattern, content)

            for _, func_name in matches:
                test_lines.append(f"    #[test]")
                test_lines.append(f"    fn test_{func_name}() {{")
                test_lines.append(f"        // TODO: Test {func_name}")
                test_lines.append("        assert!(true);")
                test_lines.append("    }")
                test_lines.append("")

    test_lines.append("}")
    test_lines.append("")
    test_lines.append("#[tokio::test]")
    test_lines.append("async fn test_integration() {")
    test_lines.append("    // TODO: Add integration test")
    test_lines.append("    assert!(true);")
    test_lines.append("}")

    return "\n".join(test_lines)


class PipelineCoordinator:
    """Coordinates the full transpilation pipeline with multi-pass refinement."""

    def __init__(
        self,
        max_passes: int = 2,
        model: str = "MiniMax-M2.7",
        target_lang: str = "typescript",
        max_functions_per_chunk: int = 30
    ):
        self.max_passes = max_passes
        self.model = model
        self.target_lang = target_lang
        self.max_functions_per_chunk = max_functions_per_chunk
        self.transpiler = Transpiler(model=model)
        self.validator = IntegrationValidator(target_lang)
        self.results: List[str] = []
        self.chunk_progress: List[ChunkProgress] = []

    def transpile_chunk(
        self,
        chunk: Chunk,
        repo_path: Path,
        language: str,
        output_dir: Optional[Path] = None
    ) -> str:
        """Transpile a single chunk.

        Args:
            chunk: The chunk to transpile
            repo_path: Path to the repository
            language: Source language
            output_dir: Optional output directory

        Returns:
            Transpiled code for this chunk
        """
        from repo_transmute.blueprint.extractor import extract_from_python, extract_classes_from_python

        functions = []
        data_structures = []

        for file_path in chunk.files:
            try:
                if language == "python":
                    functions.extend(extract_from_python(file_path))
                    data_structures.extend(extract_classes_from_python(file_path))
                elif language in ("javascript", "typescript"):
                    from repo_transmute.blueprint.extractor import extract_from_javascript, extract_from_typescript
                    extractor = extract_from_typescript if language == "typescript" else extract_from_javascript
                    functions.extend(extractor(file_path))
            except Exception as e:
                print(f"Warning: Could not extract from {file_path}: {e}")
                continue

        chunk_blueprint = Blueprint(
            repo=repo_path.name,
            language=language,
            functions=functions,
            data_structures=data_structures
        )

        # Serialize blueprint data to a temp file
        blueprint_data = {
            "blueprint": {
                "repo": chunk_blueprint.repo,
                "language": chunk_blueprint.language,
                "functions": [
                    {
                        "name": func.name,
                        "signature": func.signature,
                        "file": str(func.file),
                        "line": func.line,
                        "async": func.async_flag,
                        "docstring": func.docstring or "",
                        "decorators": [d for d in (func.decorators or [])],
                        "body": func.body or "",
                    }
                    for func in chunk_blueprint.functions
                ],
                "data_structures": [
                    {
                        "name": ds.name,
                        "type": ds.type,
                        "file": str(ds.file),
                        "line": ds.line,
                        "fields": ds.fields,
                        "docstring": ds.docstring or "",
                        "methods": [
                            {"name": m.name, "signature": m.signature,
                             "body": m.body or "", "docstring": m.docstring or ""}
                            for m in (ds.methods or [])
                        ],
                    }
                    for ds in chunk_blueprint.data_structures
                ]
            }
        }

        # Write to a named temp file (delete=False so we can read it after)
        tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        tmp_path = Path(tmp_file.name)
        try:
            yaml.dump(blueprint_data, tmp_file)
            tmp_file.close()
            code = self.transpiler.transpile(tmp_path, self.target_lang, output_dir)
            return code
        finally:
            tmp_path.unlink(missing_ok=True)

    def transpile_with_refinement(
        self,
        blueprint: Blueprint,
        output_dir: Optional[Path] = None
    ) -> str:
        """Run multi-pass transpilation with refinement."""
        blueprint_data = {
            "blueprint": {
                "repo": blueprint.repo,
                "language": blueprint.language,
                "functions": [
                    {
                        "name": func.name,
                        "signature": func.signature,
                        "file": str(func.file),
                        "line": func.line,
                        "async_flag": func.async_flag
                    }
                    for func in blueprint.functions
                ],
                "data_structures": [
                    {
                        "name": ds.name,
                        "type": ds.type,
                        "file": str(ds.file),
                        "line": ds.line,
                        "fields": ds.fields
                    }
                    for ds in blueprint.data_structures
                ]
            }
        }

        tmp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        tmp_path = Path(tmp_file.name)
        try:
            yaml.dump(blueprint_data, tmp_file)
            tmp_file.close()

            # Pass 1: Initial transpilation
            code = self.transpiler.transpile(tmp_path, self.target_lang, output_dir)
            self.results.append(code)

            # Validate and refine
            for pass_num in range(2, self.max_passes + 1):
                validation = self._validate_and_refine(code, pass_num)
                if validation:
                    code = validation
                    self.results.append(code)

            return code

        finally:
            tmp_path.unlink(missing_ok=True)

    def _validate_and_refine(self, code: str, pass_num: int) -> Optional[str]:
        """Validate code and attempt refinement if issues found."""
        import_valid = self.validator.validate_imports(code)
        type_valid = self.validator.validate_types(code)

        if import_valid and type_valid:
            return None

        issues = []
        if not import_valid:
            issues.append(f"Import errors: {', '.join(self.validator.import_errors)}")
        if not type_valid:
            issues.append(f"Type errors: {', '.join(self.validator.type_errors)}")

        refinement_prompt = f"""Refine this {self.target_lang} code to fix the following issues:
{chr(10).join(issues)}

Current code:
```{self.target_lang}
{code}
```

Requirements:
- Fix all import issues
- Add proper type annotations
- Maintain existing functionality
- Output ONLY the fixed code, no explanations
"""

        try:
            refined_code = self.transpiler._call_minimax(refinement_prompt)
            refined_code = re.sub(r"^```[\w]*\n", "", refined_code)
            refined_code = re.sub(r"\n```$", "", refined_code)
            return refined_code.strip()
        except Exception:
            return None

    def transpile_all_chunks(
        self,
        repo_path: Path,
        language: str,
        output_dir: Optional[Path] = None,
        progress_callback: Optional[callable] = None
    ) -> Tuple[str, int, int, List[str]]:
        """Transpile all chunks from a repository.

        Args:
            repo_path: Path to the repository
            language: Source language
            output_dir: Optional output directory
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (combined_transpiled_code, chunks_processed, total_chunks, written_paths)
        """
        print(f"Chunking repository: {repo_path.name}")

        # chunk_repository accepts max_functions (not chunk_size)
        chunks = chunk_repository(repo_path, max_functions=self.max_functions_per_chunk)
        total_chunks = len(chunks)
        print(f"Created {total_chunks} chunks")

        reassembler = Reassembler(chunks, repo_path)
        chunk_order = reassembler.get_chunk_order()
        chunks_processed = 0

        for idx, chunk_id in enumerate(tqdm(chunk_order, desc="Transpiling chunks", unit="chunk")):
            chunk = chunks[chunk_id]

            progress = ChunkProgress(
                chunk_id=chunk_id,
                status="processing",
                files=[str(f.relative_to(repo_path)) for f in chunk.files],
                functions=sum(1 for f in chunk.files if f.suffix == '.py')
            )
            self.chunk_progress.append(progress)

            if progress_callback:
                progress_callback(idx + 1, total_chunks, f"Processing chunk {chunk_id + 1}/{total_chunks}")

            print(f"  Transpiling chunk {idx + 1}/{total_chunks} (id={chunk_id}): {len(chunk.files)} files — {[f.name for f in chunk.files]}")

            try:
                transpiled_code = self.transpile_chunk(
                    chunk=chunk,
                    repo_path=repo_path,
                    language=language,
                    output_dir=output_dir
                )

                reassembler.add_transpiled(chunk_id, transpiled_code, file_paths=[f for f in chunk.files])
                progress.status = "completed"
                chunks_processed += 1

            except Exception as e:
                progress.status = "failed"
                progress.error = str(e)
                continue

        # Combine all transpiled chunks
        combined_code = reassembler.combine()

        # Resolve cross-chunk imports so internal references point to the right files
        resolved_code = reassembler.resolve_imports()

        print(f"\nProcessed {chunks_processed}/{total_chunks} chunks successfully")

        written_files = reassembler.write_files(
            output_dir=output_dir,
            file_ext=self._get_extension()
        )
        written_paths = [str(p) for p in written_files.values()]

        return resolved_code, chunks_processed, total_chunks, written_paths

    def run_full_pipeline(
        self,
        repo: str,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        chunk_dir: Optional[Path] = None,
        progress_callback: Optional[callable] = None,
    ) -> PipelineResult:
        """Run the full transpilation pipeline.

        Args:
            repo: Repository in format "owner/repo"
            cache_dir: Directory for cloned repos
            output_dir: Directory for blueprints
            chunk_dir: Optional directory for chunked files (if pre-chunked)
            progress_callback: Optional callback for progress updates (idx, total, message)

        Returns:
            PipelineResult with transpiled code, tests, and validation
        """
        try:
            if "/" not in repo:
                return PipelineResult(
                    success=False,
                    error="Invalid repo format. Use 'owner/repo'"
                )

            owner, name = repo.split("/", 1)

            # Clone if not already cached
            repo_path = cache_dir / f"{owner}__{name}"
            if not repo_path.exists():
                repo_path = clone_repo(owner, name, cache_dir)

            # Detect language
            language = detect_language(repo_path)

            # Extract full blueprint (for metadata)
            blueprint = extract_all(repo_path, language)

            # Step 2: Transpile ALL chunks
            transpiled_code, chunks_processed, total_chunks, written_paths = self.transpile_all_chunks(
                repo_path=repo_path,
                language=language,
                output_dir=output_dir,
                progress_callback=progress_callback
            )

            # Step 3: Generate tests (from combined output)
            if output_dir:
                output_files = list(output_dir.glob(f"{name}*.{self._get_extension()}"))
            else:
                output_files = []

            if output_files:
                tests = generate_module_tests(output_files, self.target_lang)
            else:
                tests = "# No output files found for test generation - chunks processed individually"

            # Step 4: Validate
            self.validator.validate_imports(transpiled_code)
            self.validator.validate_types(transpiled_code)
            validation_report = self.validator.generate_report()

            return PipelineResult(
                success=True,
                transpiled_code=transpiled_code,
                tests=tests,
                validation=validation_report,
                passes_run=len(self.results),
                chunks_processed=chunks_processed,
                total_chunks=total_chunks,
                files_written=written_paths
            )

        except Exception as e:
            return PipelineResult(
                success=False,
                error=str(e),
                passes_run=len(self.results)
            )

    def _get_extension(self) -> str:
        """Get file extension for target language."""
        ext_map = {
            "typescript": "ts",
            "javascript": "js",
            "rust": "rs",
            "python": "py",
        }
        return ext_map.get(self.target_lang, "txt")


def chunk_repository(
    repo_path: Path,
    max_functions: int = 30
) -> List[Chunk]:
    """Chunk repository files into groups for processing.

    Note: This function is kept for backward compatibility but
    the main chunking is done via repo_transmute.transpiler.chunker.chunk_repository

    Args:
        repo_path: Path to repository
        max_functions: Maximum functions per chunk

    Returns:
        List of file chunks
    """
    # Import from chunker module
    from repo_transmute.transpiler.chunker import chunk_repository as cr
    return cr(repo_path, max_functions=max_functions)


def analyze_dependencies(repo_path: Path) -> dict:
    """Analyze repository dependencies."""
    deps = {
        "files": [],
        "imports": {},
        "external": set(),
        "internal": set()
    }

    from repo_transmute.ingestion.walker import walk_source_files

    files = list(walk_source_files(repo_path))
    deps["file_count"] = len(files)

    import_patterns = {
        "python": [
            r"^import\s+(\S+)",
            r"^from\s+(\S+)\s+import"
        ],
        "javascript": [
            r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]",
            r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
        ],
        "typescript": [
            r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"]",
            r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
        ]
    }

    language = detect_language(repo_path)
    patterns = import_patterns.get(language, [])

    all_imports = []
    for file in files:
        try:
            content = file.read_text()
            for pattern in patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                all_imports.extend(matches)
        except Exception:
            continue

    for imp in all_imports:
        if imp.startswith("."):
            deps["internal"].add(imp)
        elif any(imp.startswith(prefix) for prefix in ("npm", "pip", "cargo", "go", "gem")):
            deps["external"].add(imp)
        else:
            stdlib = {"os", "sys", "re", "json", "typing", "pathlib", "asyncio"}
            if imp.split(".")[0] not in stdlib:
                deps["external"].add(imp)
            else:
                deps["internal"].add(imp)

    deps["external"] = list(deps["external"])
    deps["internal"] = list(deps["internal"])

    return deps
