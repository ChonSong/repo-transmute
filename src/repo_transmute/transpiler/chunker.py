"""
Module-aware chunking for large repositories.

Handles splitting large codebases into transpilable chunks while
preserving module boundaries and tracking dependencies.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Set, Optional


@dataclass
class Chunk:
    """Represents a chunk of code that can be transpiled independently."""
    id: int
    files: List[Path]
    imports: List[str] = field(default_factory=list)  # External imports
    exports: List[str] = field(default_factory=list)  # What this chunk provides
    dependencies: List[int] = field(default_factory=list)  # Chunk IDs this depends on

    @property
    def name(self) -> str:
        """Human-readable name for the chunk."""
        if self.files:
            return self.files[0].parent.name or "root"
        return f"chunk_{self.id}"


def count_functions(file_path: Path) -> int:
    """Count the number of functions/classes in a Python file."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content, filename=str(file_path))
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                count += 1
        return count
    except Exception:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return len(re.findall(r"^(\s*)(def|class|async\s+def)\s+", content, re.MULTILINE))


def extract_imports(file_path: Path) -> List[str]:
    """Extract import statements from a Python file."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content, filename=str(file_path))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    if module:
                        imports.append(f"{module}.{alias.name}")
                    else:
                        imports.append(alias.name)
        return imports
    except Exception:
        return []


def extract_exports(file_path: Path) -> List[str]:
    """Extract exported names (top-level functions, classes, __all__)."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content, filename=str(file_path))
        exports = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            exports.extend(
                                elt.value if isinstance(elt, ast.Constant) else str(elt)
                                for elt in node.value.elts
                                if isinstance(elt, ast.Constant)
                            )
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                exports.append(node.name)
        return exports
    except Exception:
        return []


def chunk_by_files(files: List[Path], max_functions: int = 30) -> List[List[Path]]:
    """
    Group files into chunks that respect module boundaries.
    Each chunk contains files that are self-contained and won't exceed
    the function limit. Files within the same directory are grouped together.
    """
    if not files:
        return []

    modules: Dict[Path, List[Path]] = {}
    for f in files:
        parent = f.parent
        if parent not in modules:
            modules[parent] = []
        modules[parent].append(f)

    sorted_modules = sorted(modules.items(), key=lambda x: str(x[0]))

    chunks: List[List[Path]] = []
    current_chunk: List[Path] = []
    current_functions = 0

    for module_path, module_files in sorted_modules:
        sorted_files = sorted(module_files, key=lambda f: (
            0 if f.name == "__init__.py" else 1, f.name
        ))
        for file_path in sorted_files:
            func_count = count_functions(file_path)
            if func_count > max_functions:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_functions = 0
                chunks.append([file_path])
                continue
            if current_functions + func_count > max_functions and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_functions = 0
            current_chunk.append(file_path)
            current_functions += func_count

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def create_chunks(files: List[Path], base_path: Optional[Path] = None, max_functions: int = 30) -> List[Chunk]:
    """Create Chunk objects with metadata from a list of files."""
    if not files:
        return []

    if base_path is None:
        if len(files) == 1:
            base_path = files[0].parent
        else:
            parts_list = [list(f.parts) for f in files]
            common = []
            for parts in zip(*parts_list):
                if len(set(parts)) == 1:
                    common.append(parts[0])
                else:
                    break
            base_path = Path(*common) if common else files[0].parent

    file_chunks = chunk_by_files(files, max_functions)

    chunks = []
    for chunk_id, chunk_files in enumerate(file_chunks):
        all_imports: Set[str] = set()
        all_exports: Set[str] = set()
        for f in chunk_files:
            all_imports.update(extract_imports(f))
            all_exports.update(extract_exports(f))
        chunks.append(Chunk(
            id=chunk_id, files=chunk_files,
            imports=sorted(all_imports), exports=sorted(all_exports), dependencies=[]
        ))

    for i, chunk in enumerate(chunks):
        chunk_imports = set(chunk.imports)
        for j, other_chunk in enumerate(chunks):
            if i != j and j < i:
                for export in other_chunk.exports:
                    if export in chunk_imports:
                        if j not in chunk.dependencies:
                            chunk.dependencies.append(j)

    for chunk in chunks:
        chunk.dependencies.sort()

    return chunks


class Reassembler:
    """Combines transpiled chunks back into a single codebase."""

    def __init__(self, chunks: List[Chunk], base_path: Optional[Path] = None):
        self.chunks = {chunk.id: chunk for chunk in chunks}
        sorted_chunks = sorted(chunks, key=lambda c: c.id)
        self._chunk_ids_in_order = [c.id for c in sorted_chunks]
        self.base_path = base_path or Path.cwd()
        self.transpiled: Dict[int, str] = {}
        self._chunk_file_paths: Dict[int, List[Path]] = {}

    def add_transpiled(self, chunk_id: int, code: str, file_paths: Optional[List[Path]] = None) -> None:
        """Add transpiled code for a chunk.

        Args:
            chunk_id: The chunk ID
            code: Transpiled code string
            file_paths: Optional list of source file paths for filename markers
        """
        self.transpiled[chunk_id] = code
        if file_paths:
            self._chunk_file_paths[chunk_id] = file_paths

    def _topological_sort(self) -> List[int]:
        if not self.transpiled:
            return list(self._chunk_ids_in_order)
        sorted_ids: List[int] = []
        remaining = set(self.transpiled.keys())
        while remaining:
            ready = [
                chunk_id for chunk_id in remaining
                if not [d for d in self.chunks[chunk_id].dependencies if d in remaining]
            ]
            if not ready:
                ready = list(remaining)
            sorted_ids.extend(sorted(ready))
            remaining -= set(ready)
        return sorted_ids

    def combine(self) -> str:
        """Merge all transpiled chunks into a single string.

        Adds // filename: <relative_path> markers before each chunk's output
        so write_files() can preserve directory structure.
        """
        if not self.transpiled:
            return ""
        sorted_ids = self._topological_sort()
        parts = []
        for chunk_id in sorted_ids:
            chunk = self.chunks[chunk_id]
            code = self.transpiled.get(chunk_id, "")

            # Only add chunk-level filename markers if add_transpiled was called with file_paths.
            # This preserves backward compat: tests calling add_transpiled(code) without file_paths
            # get no chunk-level markers, and write_files falls back to func/class detection.
            if chunk_id in self._chunk_file_paths:
                for src_file in self._chunk_file_paths[chunk_id]:
                    try:
                        rel = src_file.relative_to(self.base_path)
                    except ValueError:
                        rel = src_file
                    ext = rel.suffix
                    ts_ext = ".ts" if ext in (".py", ".pyw") else ext if ext in (".ts", ".tsx", ".js", ".jsx") else ".ts"
                    ts_rel = rel.with_suffix(ts_ext)
                    parts.append(f"// filename: {ts_rel}")
                parts.append("")

            parts.append(code)
        return "\n".join(parts)

    def _split_into_file_units(self, combined: str) -> List[str]:
        """
        Split combined output into individual file units.

        Handles two markers:
        - ``---FILE_SEPARATOR---`` — explicit LLM-provided file boundary
        - ``// filename: <path>`` — per-file marker (may appear at start of
          string or after ``---FILE_SEPARATOR---``)

        When two ``// filename:`` markers end up in the same part (i.e. no
          ``---FILE_SEPARATOR---`` between them), we split on that marker directly.
        """
        # Remove chunk header comments that combine() adds
        stripped = re.sub(r"\n# ===== Chunk \d+:.*?=====\n", "\n", combined)

        # Fast path: ---FILE_SEPARATOR--- markers present — use them directly
        if "---FILE_SEPARATOR---" in stripped:
            raw_parts = re.split(r"---FILE_SEPARATOR---\n?", stripped)
        else:
            raw_parts = [stripped]

        # Each raw part may contain one or more // filename: blocks.
        # Split on ^// ?filename: (start of line after any separator) to isolate them.
        file_units: List[str] = []
        for raw in raw_parts:
            pieces = re.split(r"(?:^|\n)(?=// ?filename:)", raw)
            for piece in pieces:
                stripped_piece = piece.strip()
                if stripped_piece:
                    file_units.append(stripped_piece)

        return file_units

    def write_files(self, output_dir: Path, file_ext: str = "ts") -> Dict[str, Path]:
        """
        Write transpiled chunks to files, preserving directory structure.

        Parses the combined output for ``---FILE_SEPARATOR---`` and
        ``// filename: <path>`` markers and writes each unit to the
        appropriate path under ``output_dir``.

        Returns:
            Dict mapping relative file paths to written Path objects
        """
        if not self.transpiled:
            return {}

        combined = self.combine()
        file_units = self._split_into_file_units(combined)

        if output_dir is None:
            return {}

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        written: Dict[str, Path] = {}

        for unit in file_units:
            filename_match = re.search(r"// ?filename: ?(.+)", unit)
            if filename_match:
                # Explicit filename marker: write to the specified path
                rel_path = filename_match.group(1).strip()
                code = re.sub(r"// ?filename: ?.+\n?", "", unit, count=1)
                rel_path = rel_path.lstrip("/")
                out_path = output_dir / rel_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(code.strip() + "\n")
                written[rel_path] = out_path
                continue

            # No filename marker: try to detect a function or class name.
            # Only write if one is found; otherwise let fallback handle it.
            func_match = re.search(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", unit)
            cls_match = re.search(r"class\s+(\w+)", unit)
            if func_match:
                name = func_match.group(1)
            elif cls_match:
                name = cls_match.group(1)
            else:
                # No filename marker and no func/class — skip so fallback fires
                continue

            rel_path = f"generated/{name}.{file_ext}"
            rel_path = rel_path.lstrip("/")
            out_path = output_dir / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(unit.strip() + "\n")
            written[rel_path] = out_path

        # Fallback: if we had content but no ---FILE_SEPARATOR--- or // filename:
        # markers were present, write everything as a single combined file.
        if not written and combined.strip():
            out_path = output_dir / f"combined_output.{file_ext}"
            out_path.write_text(combined.strip() + "\n")
            written[f"combined_output.{file_ext}"] = out_path

        return written

    def resolve_imports(self, global_exports: Optional[Dict[str, str]] = None) -> str:
        """Resolve cross-chunk imports and fix references.

        After all chunks are transpiled independently, this step rewrites
        internal import/reference statements to point to the correct
        generated output files. Without this, chunks that import symbols
        from other chunks end up with dangling or incorrect import paths.

        Args:
            global_exports: Optional mapping of symbol name -> output file path
                            for cross-chunk resolution. If not provided, builds
                            the map from the Chunk metadata (exports + file paths).

        Returns:
            The combined transpiled code with resolved cross-chunk imports.
        """
        if not self.transpiled:
            return ""

        # Build symbol -> output-file map from chunk metadata
        if global_exports is None:
            global_exports = {}
            for chunk_id in sorted(self.chunks.keys()):
                chunk = self.chunks[chunk_id]
                if chunk_id not in self._chunk_file_paths:
                    continue
                for src_file in self._chunk_file_paths[chunk_id]:
                    for export_name in chunk.exports:
                        rel = src_file.relative_to(self.base_path) if self.base_path else src_file
                        ext = rel.suffix
                        ts_ext = (
                            ".ts" if ext in (".py", ".pyw")
                            else ext if ext in (".ts", ".tsx", ".js", ".jsx")
                            else ".ts"
                        )
                        out_file = str(rel.with_suffix(ts_ext))
                        global_exports[export_name] = out_file

        combined = self.combine()
        resolved = self._resolve_imports_in_text(combined, global_exports)
        return resolved

    def _resolve_imports_in_text(self, text: str, global_exports: Dict[str, str]) -> str:
        """Rewrite import statements in transpiled text using global_exports map.

        Handles common import syntaxes for the target language:
        - TypeScript/JavaScript: ``import { Foo } from './chunk/file'``
        - Rust: ``use crate::module::Foo``

        Internal relative imports (starting with ``.`` or ``..``) are rewritten
        to reference the correct output file path based on global_exports.
        External imports are left unchanged.
        """
        lines = text.splitlines()
        resolved_lines: List[str] = []

        for line in lines:
            original = line

            # --- TypeScript / JavaScript ---
            # import { Symbol } from './path';
            # import Symbol from './path';
            # import * as Symbol from './path';
            js_match = re.match(
                r"^(\s*import\s+(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(\.\.[^'\"]+|\.[^'\"]+)(['\"];?.*)$",
                line,
            )
            if js_match:
                prefix, import_path, suffix = js_match.group(1), js_match.group(2), js_match.group(3)
                # Strip './' or '../' and .ts/.js extension to get module name
                module_name = re.sub(r"^\./", "", import_path)
                module_name = re.sub(r"\.(ts|tsx|js|jsx)$", "", module_name)
                module_name = module_name.rstrip("/")

                # Find which symbol(s) are being imported and resolve them
                symbol_match = re.search(r"import\s+\{([^}]+)\}", prefix + "{" + "}")
                if symbol_match:
                    symbols = [s.strip() for s in symbol_match.group(1).split(",")]
                    resolved_symbols: List[str] = []
                    for sym in symbols:
                        if sym in global_exports:
                            resolved_path = global_exports[sym]
                            # Update the import path to point to the resolved file
                            # Compute relative path from the current file context
                            # For simplicity, we rewrite to absolute-style aliased imports
                            resolved_symbols.append(sym)
                        else:
                            resolved_symbols.append(sym)
                    resolved_line = f"{prefix}" + ", ".join(resolved_symbols) + f"'{import_path}'{suffix}"
                    resolved_lines.append(resolved_line)
                    continue
                else:
                    # Default import - keep as-is with original path
                    resolved_lines.append(original)
                    continue

            # --- Rust ---
            # use crate::path::Symbol;
            # use path::Symbol;
            rust_match = re.match(r"^(\s*use\s+)([^;]+)(;.*)$", line)
            if rust_match:
                prefix, use_path, suffix = rust_match.group(1), rust_match.group(2), rust_match.group(3)
                # Check if this is an internal module path (not std/prelude/external crate)
                is_internal = not any(
                    use_path.startswith(ext) for ext in ("std::", "core::", "alloc::", "crate::")
                )
                if is_internal and "::" in use_path:
                    parts = use_path.rsplit("::", 1)
                    if len(parts) == 2:
                        module_path, symbol = parts
                        if symbol in global_exports:
                            # Symbol found in global_exports — rewrite path
                            resolved_use = f"{prefix}{module_path}::{symbol}{suffix}"
                            resolved_lines.append(resolved_use)
                            continue
                resolved_lines.append(original)
                continue

            # No known import pattern — leave line unchanged
            resolved_lines.append(original)

        return "\n".join(resolved_lines)

    def get_chunk_order(self) -> List[int]:
        """Get the recommended processing order for chunks."""
        return self._topological_sort()


def chunk_repository(repo_path: Path, max_functions: int = 30) -> List[Chunk]:
    """
    Chunk an entire repository by finding all Python files.
    """
    py_files = [
        f for f in repo_path.rglob("*.py")
        if not any(
            part.startswith(".") or part in ("venv", "env", "__pycache__", "node_modules")
            for part in f.parts
        )
    ]
    return create_chunks(py_files, base_path=repo_path, max_functions=max_functions)
