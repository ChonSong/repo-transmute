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

    def add_transpiled(self, chunk_id: int, code: str) -> None:
        self.transpiled[chunk_id] = code

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
        """Merge all transpiled chunks into a single string."""
        if not self.transpiled:
            return ""
        sorted_ids = self._topological_sort()
        parts = []
        for chunk_id in sorted_ids:
            chunk = self.chunks[chunk_id]
            code = self.transpiled.get(chunk_id, "")
            if chunk.files:
                names = ", ".join(f.name for f in chunk.files[:3])
                if len(chunk.files) > 3:
                    names += f" (+{len(chunk.files) - 3} more)"
                parts.append(f"\n# ===== Chunk {chunk_id}: {names} =====\n")
            parts.append(code)
        return "\n".join(parts)

    def write_files(self, output_dir: Path, file_ext: str = "ts") -> Dict[str, Path]:
        """
        Write transpiled chunks to files, preserving directory structure.

        Parses the combined output for ---FILE_SEPARATOR--- markers and
        writes each file to the appropriate path under output_dir.

        Returns:
            Dict mapping relative file paths to written Path objects
        """
        if not self.transpiled:
            return {}

        combined = self.combine()
        # Remove chunk header comments
        combined = re.sub(r"\n# ===== Chunk \d+:.*?=====\n", "\n", combined)

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        written: Dict[str, Path] = {}

        # Split on ---FILE_SEPARATOR--- markers
        parts = re.split(r"---FILE_SEPARATOR---\n?", combined)

        for part in parts:
            part = part.strip()
            if not part:
                continue

            filename_match = re.search(r"// ?filename: ?(.+)", part)
            if filename_match:
                rel_path = filename_match.group(1).strip()
                code = re.sub(r"// ?filename: ?.+\n?", "", part, count=1)
            else:
                func_match = re.search(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", part)
                cls_match = re.search(r"class\s+(\w+)", part)
                if func_match:
                    name = func_match.group(1)
                elif cls_match:
                    name = cls_match.group(1)
                else:
                    name = "output"
                rel_path = f"generated/{name}.{file_ext}"

            rel_path = rel_path.lstrip("/")
            out_path = output_dir / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(code.strip() + "\n")
            written[rel_path] = out_path
            print(f"  Wrote {rel_path}")

        # Fallback: if no files were written (LLM omitted ---FILE_SEPARATOR--- markers),
        # write the combined output as a single file to avoid silent failures
        if not written:
            print(f"  WARNING: No files written -- LLM output may be missing ---FILE_SEPARATOR--- markers.")
            print(f"  Raw combined length: {len(combined)} chars")
            combined_stripped = combined.strip()
            if combined_stripped:
                out_path = output_dir / f"combined_output.{file_ext}"
                out_path.write_text(combined_stripped + chr(10))
                written[f"combined_output.{file_ext}"] = out_path
                print(f"  WARNING: Fallback wrote combined output to {out_path}")


        return written

    def resolve_imports(self, global_exports: Optional[Dict[str, str]] = None) -> str:
        """Resolve cross-chunk imports and fix references."""
        return self.combine()

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
