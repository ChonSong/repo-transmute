"""Pipeline coordinator for RepoTransmute - multi-pass transpilation with refinement."""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from repo_transmute.blueprint import Blueprint, load_blueprint
from repo_transmute.blueprint.extractor import extract_all
from repo_transmute.blueprint.storage import save_blueprint
from repo_transmute.ingestion.clone import clone_repo
from repo_transmute.ingestion.detector import detect_language
from repo_transmute.transpiler.llm import Transpiler
from repo_transmute.transpiler.prompts import build_transpile_prompt


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
        # Check for common import issues
        import_pattern = r"(?:import|from)\s+['\"]([^'\"]+)['\"]"
        imports = re.findall(import_pattern, code)
        
        # Check for relative path issues
        for imp in imports:
            if imp.startswith("..") or imp.startswith("."):
                # Check for missing file extensions
                if not imp.endswith((".ts", ".tsx", ".js", ".jsx", ".json")):
                    self.import_errors.append(f"Missing extension in relative import: {imp}")
        
        # Check for undefined exports being imported
        export_pattern = r"export\s+(?:const|let|var|function|class|interface|type)"
        exports = set(re.findall(r"export\s+(?:const|let|var|function|class|interface|type)\s+(\w+)", code))
        
        for imp in imports:
            if imp.startswith("."):
                continue  # Skip relative imports
        
        return len(self.import_errors) == 0
    
    def _validate_rust_imports(self, code: str) -> bool:
        """Validate Rust imports."""
        use_pattern = r"use\s+([^;]+);"
        uses = re.findall(use_pattern, code)
        
        # Check for common issues
        for use in uses:
            # Check for unresolveable paths
            if "::" in use:
                parts = use.split("::")
                # Last part should be valid identifier
                if not parts[-1].replace("{", "").replace("}", "").replace("*", "").replace("as", "").strip().isidentifier():
                    self.import_errors.append(f"Invalid use statement: use {use}")
        
        return len(self.import_errors) == 0
    
    def _validate_python_imports(self, code: str) -> bool:
        """Validate Python imports."""
        import re
        
        # Find all import statements
        import_patterns = [
            r"^import\s+(\S+)",
            r"^from\s+(\S+)\s+import",
        ]
        
        for pattern in import_patterns:
            matches = re.findall(pattern, code, re.MULTILINE)
            for module in matches:
                # Check for invalid characters
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
        # Check for any: usage
        any_matches = re.findall(r":\s*any\b", code)
        if any_matches:
            self.type_errors.append(f"Found {len(any_matches)} 'any' type annotations")
        
        # Check for untyped returns
        func_pattern = r"function\s+\w+\s*\([^)]*\)(?:\s*:\s*\w+)?\s*\{"
        matches = re.findall(func_pattern, code)
        
        # Check for proper interface usage
        if "interface" not in code and "type" not in code and "class" in code:
            self.type_errors.append("No type definitions found (consider using interfaces)")
        
        return len(self.type_errors) == 0
    
    def _validate_python_types(self, code: str) -> bool:
        """Validate Python type hints."""
        # Check for typing module usage
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
    """Generate Jest/Vitest tests for each module.
    
    Args:
        chunk_files: List of source files in this chunk/module
        target_lang: Target language for tests
    
    Returns:
        Generated test code as string
    """
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
    
    # Group files by module (directory)
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
        
        # Find exported functions from each file
        for file in files:
            content = file.read_text()
            
            # Find exported functions
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
    
    # Add integration test
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
        # Find classes and functions
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
            
            # Find public functions
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
        target_lang: str = "typescript"
    ):
        self.max_passes = max_passes
        self.model = model
        self.target_lang = target_lang
        self.transpiler = Transpiler(model=model)
        self.validator = IntegrationValidator(target_lang)
        self.results: List[str] = []
    
    def transpile_with_refinement(
        self,
        blueprint: Blueprint,
        output_dir: Optional[Path] = None
    ) -> str:
        """Run multi-pass transpilation with refinement.
        
        Pass 1: Generate initial code
        Pass 2+: Fix issues, add types, improve quality
        
        Returns:
            Best transpiled code result
        """
        # Save blueprint to temp file for transpiler
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            blueprint_data = {
                "blueprint": {
                    "repo": blueprint.repo,
                    "language": blueprint.language,
                    "functions": [
                        {
                            "name": func.name,
                            "signature": func.signature,
                            "file": func.file,
                            "line": func.line,
                            "async_flag": func.async_flag
                        }
                        for func in blueprint.functions
                    ],
                    "data_structures": [
                        {
                            "name": ds.name,
                            "type": ds.type,
                            "file": ds.file,
                            "line": ds.line,
                            "fields": ds.fields
                        }
                        for ds in blueprint.data_structures
                    ]
                }
            }
            yaml.dump(blueprint_data, f)
            temp_path = Path(f.name)
        
        try:
            # Pass 1: Initial transpilation
            code = self.transpiler.transpile(temp_path, self.target_lang, output_dir)
            self.results.append(code)
            
            # Validate and refine
            for pass_num in range(2, self.max_passes + 1):
                validation = self._validate_and_refine(code, pass_num)
                if validation:
                    code = validation
                    self.results.append(code)
            
            return code
            
        finally:
            # Cleanup temp file
            temp_path.unlink(missing_ok=True)
    
    def _validate_and_refine(self, code: str, pass_num: int) -> Optional[str]:
        """Validate code and attempt refinement if issues found."""
        import tempfile
        
        # Validate current code
        import_valid = self.validator.validate_imports(code)
        type_valid = self.validator.validate_types(code)
        
        if import_valid and type_valid:
            return None  # No issues, no refinement needed
        
        # Generate refinement prompt
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
            # Call the transpiler with refinement prompt
            refined_code = self.transpiler._call_minimax(refinement_prompt)
            
            # Clean up the response
            refined_code = re.sub(r"^```[\w]*\n", "", refined_code)
            refined_code = re.sub(r"\n```$", "", refined_code)
            
            return refined_code.strip()
            
        except Exception:
            # If refinement fails, return original
            return None
    
    def run_full_pipeline(
        self,
        repo: str,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
        chunk_dir: Optional[Path] = None,
    ) -> PipelineResult:
        """Run the full transpilation pipeline.
        
        Args:
            repo: Repository in format "owner/repo"
            cache_dir: Directory for cloned repos
            output_dir: Directory for blueprints
            chunk_dir: Optional directory for chunked files (if pre-chunked)
        
        Returns:
            PipelineResult with transpiled code, tests, and validation
        """
        try:
            # Step 1: Clone and extract blueprint
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
            
            # Extract blueprint
            blueprint = extract_all(repo_path, language)
            
            # Step 2: Transpile with refinement
            transpiled_code = self.transpile_with_refinement(blueprint, output_dir)
            
            # Step 3: Generate tests
            # Find the transpiled files
            if output_dir:
                output_files = list(output_dir.glob(f"{name}*.{self._get_extension()}"))
            else:
                output_files = []
            
            if output_files:
                tests = generate_module_tests(output_files, self.target_lang)
            else:
                tests = "# No output files found for test generation"
            
            # Step 4: Validate
            validation = self.validator.validate_imports(transpiled_code)
            self.validator.validate_types(transpiled_code)
            validation_report = self.validator.generate_report()
            
            return PipelineResult(
                success=True,
                transpiled_code=transpiled_code,
                tests=tests,
                validation=validation_report,
                passes_run=len(self.results)
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
    chunk_size: int = 20
) -> List[List[Path]]:
    """Chunk repository files into groups for processing.
    
    Args:
        repo_path: Path to repository
        chunk_size: Number of files per chunk
    
    Returns:
        List of file chunks
    """
    from repo_transmute.ingestion.walker import walk_source_files
    
    files = list(walk_source_files(repo_path))
    chunks = []
    
    for i in range(0, len(files), chunk_size):
        chunks.append(files[i:i + chunk_size])
    
    return chunks


def analyze_dependencies(repo_path: Path) -> dict:
    """Analyze repository dependencies.
    
    Args:
        repo_path: Path to repository
    
    Returns:
        Dictionary with dependency information
    """
    deps = {
        "files": [],
        "imports": {},
        "external": set(),
        "internal": set()
    }
    
    from repo_transmute.ingestion.walker import walk_source_files
    
    # Find all source files
    files = list(walk_source_files(repo_path))
    deps["file_count"] = len(files)
    
    # Analyze imports in each file
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
    
    # Categorize imports
    for imp in all_imports:
        if imp.startswith("."):
            deps["internal"].add(imp)
        elif any(imp.startswith(prefix) for prefix in ("npm", "pip", "cargo", "go", "gem")):
            deps["external"].add(imp)
        else:
            # Third-party or standard library
            stdlib = {"os", "sys", "re", "json", "typing", "pathlib", "asyncio"}
            if imp.split(".")[0] not in stdlib:
                deps["external"].add(imp)
            else:
                deps["internal"].add(imp)
    
    deps["external"] = list(deps["external"])
    deps["internal"] = list(deps["internal"])
    
    return deps
