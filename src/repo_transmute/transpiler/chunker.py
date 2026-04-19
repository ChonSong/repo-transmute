"""
Module-aware chunking for large repositories.

Handles splitting large codebases into transpilable chunks while
preserving module boundaries and tracking dependencies.

Supports multiple source languages: Python, Go, TypeScript/JavaScript, Rust.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import List, Dict, Set, Optional, Tuple


# ---------------------------------------------------------------------------
# Language → file extensions mapping
# ---------------------------------------------------------------------------

LANG_EXTENSIONS: Dict[str, Set[str]] = {
    "python": {".py"},
    "go": {".go"},
    "javascript": {".js", ".jsx"},
    "typescript": {".ts", ".tsx"},
    "rust": {".rs"},
}

# Directories to ignore when walking repos
IGNORE_DIRS = {
    ".git", "__pycache__", "node_modules", "venv", "env", ".venv",
    "dist", "build", ".idea", ".vscode", ".cache",
}


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


# ---------------------------------------------------------------------------
# Language-aware function counting
# ---------------------------------------------------------------------------

def count_functions(file_path: Path) -> int:
    """Count the number of functions/classes in a source file.

    Dispatches to language-specific counters based on file extension.
    """
    ext = file_path.suffix.lower()
    if ext == ".py":
        return _count_python_functions(file_path)
    elif ext == ".go":
        return _count_go_functions(file_path)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        return _count_js_functions(file_path)
    elif ext == ".rs":
        return _count_rust_functions(file_path)
    return 0


def _count_python_functions(file_path: Path) -> int:
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


def _count_go_functions(file_path: Path) -> int:
    """Count top-level functions and methods in a Go file.

    Uses the goast binary when available, otherwise falls back to regex.
    """
    try:
        from repo_transmute.transpiler.go_parser import extract_from_go, extract_structs_from_go, extract_interfaces_from_go
        funcs = extract_from_go(file_path)
        structs = extract_structs_from_go(file_path)
        ifaces = extract_interfaces_from_go(file_path)
        return len(funcs) + len(structs) + len(ifaces)
    except Exception:
        # Regex fallback
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            return len(re.findall(r"^func\s+", content, re.MULTILINE))
        except (FileNotFoundError, OSError):
            return 0


def _count_js_functions(file_path: Path) -> int:
    """Count functions in a JavaScript/TypeScript file."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    count = 0
    # function declarations
    count += len(re.findall(r"(?:export\s+)?(?:async\s+)?function\s+\w+", content))
    # Arrow functions with names: const name = (...) => ...
    count += len(re.findall(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", content))
    return count


def _count_rust_functions(file_path: Path) -> int:
    """Count functions in a Rust file."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    # Count fn declarations (top-level and in impl blocks)
    return len(re.findall(r"\bfn\s+\w+", content))


# ---------------------------------------------------------------------------
# Language-aware import extraction
# ---------------------------------------------------------------------------

def extract_imports(file_path: Path) -> List[str]:
    """Extract import statements from a source file.

    Dispatches to language-specific extractors based on file extension.
    """
    ext = file_path.suffix.lower()
    if ext == ".py":
        return _extract_python_imports(file_path)
    elif ext == ".go":
        return _extract_go_imports(file_path)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        return _extract_js_imports(file_path)
    elif ext == ".rs":
        return _extract_rust_imports(file_path)
    return []


def _extract_python_imports(file_path: Path) -> List[str]:
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


def _extract_go_imports(file_path: Path) -> List[str]:
    """Extract import paths from a Go file."""
    try:
        from repo_transmute.transpiler.go_parser import extract_imports_from_go
        go_imports = extract_imports_from_go(file_path)
        return [gi.path for gi in go_imports]
    except Exception:
        # Fallback regex
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return re.findall(r'"([^"]+)"', content)


def _extract_js_imports(file_path: Path) -> List[str]:
    """Extract import paths from a JavaScript/TypeScript file."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    imports = []
    # import X from 'path'
    for m in re.finditer(r"(?:import|from)\s+['\"]([^'\"]+)['\"]", content):
        imports.append(m.group(1))
    # require('path')
    for m in re.finditer(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", content):
        imports.append(m.group(1))
    return imports


def _extract_rust_imports(file_path: Path) -> List[str]:
    """Extract use statements from a Rust file."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    return re.findall(r"use\s+([^;]+);", content)


# ---------------------------------------------------------------------------
# Language-aware export extraction
# ---------------------------------------------------------------------------

def extract_exports(file_path: Path) -> List[str]:
    """Extract exported names from a source file.

    Dispatches to language-specific extractors based on file extension.
    """
    ext = file_path.suffix.lower()
    if ext == ".py":
        return _extract_python_exports(file_path)
    elif ext == ".go":
        return _extract_go_exports(file_path)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        return _extract_js_exports(file_path)
    elif ext == ".rs":
        return _extract_rust_exports(file_path)
    return []


def _extract_python_exports(file_path: Path) -> List[str]:
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


def _extract_go_exports(file_path: Path) -> List[str]:
    """Extract exported symbol names from a Go file (PascalCase names)."""
    try:
        from repo_transmute.transpiler.go_parser import extract_from_go, extract_structs_from_go, extract_interfaces_from_go
        exports = []
        for f in extract_from_go(file_path):
            # In Go, only PascalCase names are exported
            if f.name[0].isupper():
                exports.append(f.name)
        for s in extract_structs_from_go(file_path):
            if s.name[0].isupper():
                exports.append(s.name)
        for i in extract_interfaces_from_go(file_path):
            if i.name[0].isupper():
                exports.append(i.name)
        return exports
    except Exception:
        # Regex fallback: find PascalCase func/struct/interface names
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        exports = []
        for m in re.finditer(r"^func\s+([A-Z]\w+)", content, re.MULTILINE):
            exports.append(m.group(1))
        for m in re.finditer(r"^type\s+([A-Z]\w+)\s+(?:struct|interface)", content, re.MULTILINE):
            exports.append(m.group(1))
        return exports


def _extract_js_exports(file_path: Path) -> List[str]:
    """Extract exported names from a JavaScript/TypeScript file."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    exports = []
    # export function name
    for m in re.finditer(r"export\s+(?:async\s+)?function\s+(\w+)", content):
        exports.append(m.group(1))
    # export const/let/var name
    for m in re.finditer(r"export\s+(?:const|let|var)\s+(\w+)", content):
        exports.append(m.group(1))
    # export class name
    for m in re.finditer(r"export\s+class\s+(\w+)", content):
        exports.append(m.group(1))
    # TypeScript: export interface name
    for m in re.finditer(r"export\s+interface\s+(\w+)", content):
        exports.append(m.group(1))
    # TypeScript: export type name
    for m in re.finditer(r"export\s+type\s+(\w+)", content):
        exports.append(m.group(1))
    # export { a, b, c }
    for m in re.finditer(r"export\s+\{([^}]+)\}", content):
        for part in m.group(1).split(","):
            part = part.strip()
            if " as " in part:
                part = part.split(" as ")[-1].strip()
            if part:
                exports.append(part)
    # export default function name
    for m in re.finditer(r"export\s+default\s+(?:async\s+)?function\s+(\w+)", content):
        exports.append(m.group(1))
    return exports


def _extract_rust_exports(file_path: Path) -> List[str]:
    """Extract public items from a Rust file."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    exports = []
    # pub fn name
    for m in re.finditer(r"pub\s+(?:async\s+)?fn\s+(\w+)", content):
        exports.append(m.group(1))
    # pub struct name
    for m in re.finditer(r"pub\s+struct\s+(\w+)", content):
        exports.append(m.group(1))
    # pub enum name
    for m in re.finditer(r"pub\s+enum\s+(\w+)", content):
        exports.append(m.group(1))
    # pub trait name
    for m in re.finditer(r"pub\s+trait\s+(\w+)", content):
        exports.append(m.group(1))
    return exports


def _symbol_from_qualified_import(imp: str) -> Optional[str]:
    """Extract a bare symbol name from a qualified Python import.

    ``extract_imports`` stores imports as qualified dotted paths:
      'from mod0.helper import User'  ->  'mod0.helper.User'
      'from os.path import join'      ->  'os.path.join'

    Exports stored by ``extract_exports`` are bare symbol names: 'User', 'join'.

    This function reverses the qualification to recover the bare symbol, so that
    cross-chunk dependency detection can match them.

    Returns the last dotted component if it looks like a Python identifier
    ( CamelCase for classes, snake_case for functions ), otherwise None.
    Stdlib paths like 'os.path.join' are filtered out by checking whether the
    leading component is a known stdlib package.
    """
    if '.' not in imp:
        return None
    parts = imp.rsplit('.', 1)
    last = parts[-1]
    # Must look like a Python identifier
    if not re.match(r'^[A-Za-z_]\w*$', last):
        return None
    # Filter stdlib paths: 'os.path.join' -> 'join', but os.path is stdlib
    # We detect this conservatively by checking the first component
    first = imp.split('.')[0]
    stdlib = {
        'os', 'sys', 're', 'json', 'typing', 'pathlib', 'asyncio',
        'collections', 'contextlib', 'copy', 'dataclasses', 'datetime',
        'enum', 'functools', 'inspect', 'itertools', 'logging', 'math',
        'operator', 'pickle', 'queue', 'random', 'shutil', 'statistics',
        'string', 'struct', 'tempfile', 'threading', 'time', 'traceback',
        'types', 'unittest', 'urllib', 'uuid', 'warnings', 'weakref',
    }
    if first in stdlib:
        return None
    return last


def _symbol_from_go_import(imp: str) -> Optional[str]:
    """Extract a symbol-like component from a Go import path.

    Go imports look like 'fmt', 'encoding/json', 'github.com/user/repo/pkg'.
    For cross-chunk detection, we look for local package names.
    """
    if not imp:
        return None
    # Last component of the import path
    last = imp.rsplit("/", 1)[-1]
    if last and re.match(r'^[A-Za-z_]\w*$', last):
        return last
    return None


def _symbol_from_js_import(imp: str) -> Optional[str]:
    """Extract a symbol-like component from a JS/TS import path.

    For local imports (starting with .), extract the filename stem.
    """
    if not imp or not imp.startswith("."):
        return None
    # Get the filename stem from relative paths
    stem = Path(imp).stem
    if stem and stem != "index" and re.match(r'^[A-Za-z_]\w*$', stem):
        return stem
    return None


# ---------------------------------------------------------------------------
# Chunking logic
# ---------------------------------------------------------------------------

def chunk_by_files(files: List[Path], max_functions: int = 30) -> List[List[Path]]:
    """
    Group files into chunks that respect module boundaries.
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


def create_chunks(
    files: List[Path],
    base_path: Optional[Path] = None,
    max_functions: int = 30,
    language: str = "python",
) -> List[Chunk]:
    """Create Chunk objects with metadata from a list of files.

    Args:
        files: Source files to chunk.
        base_path: Repository root (for relative paths).
        max_functions: Maximum functions per chunk.
        language: Source language — affects import/export extraction.
    """
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

    # Cross-chunk dependency detection.
    #
    # For each import, try to resolve the bare symbol name and check
    # whether that symbol is exported by another chunk.
    #
    # Language-specific import resolution:
    #   Python:  'mod0.helper.User' -> strip prefix -> 'User'
    #   Go:      'github.com/user/repo/pkg' -> strip prefix -> 'pkg'
    #   JS/TS:   './utils' -> filename stem -> 'utils'
    #   Rust:    'crate::module::Symbol' -> strip path -> 'Symbol'
    #
    for i, chunk in enumerate(chunks):
        found_deps: Set[int] = set()
        for imp in chunk.imports:
            sym = None
            if language == "python":
                sym = _symbol_from_qualified_import(imp)
            elif language == "go":
                sym = _symbol_from_go_import(imp)
            elif language in ("javascript", "typescript"):
                sym = _symbol_from_js_import(imp)
            elif language == "rust":
                # Rust: 'crate::module::Symbol' -> 'Symbol'
                if "::" in imp:
                    sym = imp.rsplit("::", 1)[-1]
                    if not re.match(r'^[A-Za-z_]\w*$', sym):
                        sym = None
            if sym is None:
                continue
            for j, other in enumerate(chunks):
                if i == j or j in found_deps:
                    continue
                if sym in other.exports:
                    found_deps.add(j)
        chunk.dependencies = sorted(found_deps)

    return chunks


# Pattern for matching TypeScript/JS import statements.
# Groups: (1) "import {Sym} from '"   (2) './path' or '../path'   (3) suffix
_JS_IMPORT_PAT = re.compile(
    r"^(\s*import\s+(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])"
    r"(\.\.[^'\"]+|\.[^'\"]+)"
    r"(['\";?.*]+)$"
)


class Reassembler:
    """Combines transpiled chunks back into a single codebase."""

    _CHUNK_FILENAME_PAT = re.compile(r"^// ?filename: .+$")

    def __init__(self, chunks: List[Chunk], base_path: Optional[Path] = None):
        self.chunks = {chunk.id: chunk for chunk in chunks}
        sorted_chunks = sorted(chunks, key=lambda c: c.id)
        self._chunk_ids_in_order = [c.id for c in sorted_chunks]
        self.base_path = base_path or Path.cwd()
        self.transpiled: Dict[int, str] = {}
        self._chunk_file_paths: Dict[int, List[Path]] = {}

    def add_transpiled(self, chunk_id: int, code: str, file_paths: Optional[List[Path]] = None) -> None:
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

    def _count_filename_markers(self, code: str) -> int:
        """Count '// filename:' lines in code (case-insensitive)."""
        return len(re.findall(r"(?i)^//\s*filename\s*:\s*\S+", code, re.MULTILINE))

    def _build_per_file_units(self, code: str, chunk_files: List[Path], file_ext: str = "ts") -> str:
        """Normalise LLM multi-file output into properly delimited per-file units.

        The LLM may return multi-file output in one of two forms:
          A) With separators:
               // filename: a.ts
               code_a
               ---FILE_SEPARATOR---
               // filename: b.ts
               code_b
          B) Without separators (one chunk-level marker for all files):
               // filename: chunk0/a.ts   <-- only a.ts's marker, but code for ALL files

        Form B causes _split_into_file_units to fail because all code ends up under
        the first marker's unit, leaving subsequent files' units empty.

        This method detects which form the LLM used and rebuilds the output as
        properly delimited per-file units so _split_into_file_units can correctly
        separate them.
        """
        if not code.strip():
            return code

        has_separators = "---FILE_SEPARATOR---" in code
        llm_marker_count = self._count_filename_markers(code)
        num_chunk_files = len(chunk_files)

        # --- Case A: LLM already used ---FILE_SEPARATOR--- delimiters ---
        if has_separators:
            raw_parts = re.split(r"---FILE_SEPARATOR---\n?", code)
            units: List[str] = []
            for part in raw_parts:
                part = part.strip()
                if not part:
                    continue
                marker_match = re.search(r"^(// ?filename: ?[^\n]+)", part.lstrip(), re.MULTILINE)
                if marker_match:
                    marker = marker_match.group(1)
                    content = part[len(marker_match.group(0)):].lstrip()
                    units.append(f"{marker}\n{content}")
                elif units and num_chunk_files:
                    # No marker in this part — prepend the next expected file's marker
                    idx = len(units)
                    if idx < num_chunk_files:
                        try:
                            rel = chunk_files[idx].relative_to(self.base_path)
                        except ValueError:
                            rel = chunk_files[idx]
                        ext = rel.suffix
                        ts_ext = (".ts" if ext in (".py", ".pyw")
                                  else ext if ext in (".ts", ".tsx", ".js", ".jsx")
                                  else f".{file_ext}")
                        units.append(f"// filename: {rel.with_suffix(ts_ext)}\n{part.lstrip()}")
                    else:
                        units.append(part.lstrip())
                else:
                    units.append(part.lstrip())
            return "\n\n---FILE_SEPARATOR---\n\n".join(units)

        # --- Case A variant: multiple // filename: markers but no explicit separators.
        #    Each split piece corresponds to one file — rebuild cleanly.
        if llm_marker_count == num_chunk_files and llm_marker_count > 0:
            pieces = re.split(r"(?:^|\n)(?=// ?filename:)", code)
            units: List[str] = []
            for piece in pieces:
                piece = piece.strip()
                if not piece:
                    continue
                marker_match = re.search(r"^(// ?filename: ?[^\n]+)", piece.lstrip(), re.MULTILINE)
                if marker_match:
                    marker = marker_match.group(1)
                    content = piece[len(marker_match.group(0)):].lstrip()
                    units.append(f"{marker}\n{content}")
                else:
                    # No marker in this piece — prepend next expected file's marker
                    idx = len(units)
                    if idx < num_chunk_files:
                        try:
                            rel = chunk_files[idx].relative_to(self.base_path)
                        except ValueError:
                            rel = chunk_files[idx]
                        ext = rel.suffix
                        ts_ext = (".ts" if ext in (".py", ".pyw")
                                  else ext if ext in (".ts", ".tsx", ".js", ".jsx")
                                  else f".{file_ext}")
                        marker = f"// filename: {rel.with_suffix(ts_ext)}"
                    else:
                        marker = None
                    if marker:
                        units.append(f"{marker}\n{piece}")
                    else:
                        units.append(piece)
            return "\n\n---FILE_SEPARATOR---\n\n".join(units)

        # --- Case B: fewer markers than chunk files (common LLM behaviour).
        #    The LLM put all code under one chunk-level marker.
        #    We cannot split it into per-file units without parsing the code.
        #    Wrap the entire chunk under the first source file's marker.
        if num_chunk_files > 0:
            try:
                rel = chunk_files[0].relative_to(self.base_path)
            except ValueError:
                rel = chunk_files[0]
            ext = rel.suffix
            ts_ext = (".ts" if ext in (".py", ".pyw")
                      else ext if ext in (".ts", ".tsx", ".js", ".jsx")
                      else f".{file_ext}")
            marker = f"// filename: {rel.with_suffix(ts_ext)}"
            # Strip any existing LLM chunk-level marker and prepend ours
            code_stripped = re.sub(r"(?i)^//\s*filename\s*:\s*[^\n]+\n?", "", code, count=1).lstrip()
            return f"{marker}\n{code_stripped}"

        return code

    def combine(self, file_ext: str = "ts") -> str:
        """Combine all transpiled chunks into a single text, with per-file
        // filename: markers and ---FILE_SEPARATOR--- between units."""
        if not self.transpiled:
            return ""
        sorted_ids = self._topological_sort()
        parts = []
        for chunk_id in sorted_ids:
            code = self.transpiled.get(chunk_id, "")
            if chunk_id in self._chunk_file_paths:
                normalized = self._build_per_file_units(code, self._chunk_file_paths[chunk_id], file_ext)
                parts.append(normalized)
            else:
                parts.append(code)
        return "\n\n---FILE_SEPARATOR---\n\n".join(parts)

    def _split_into_file_units(self, combined: str) -> List[Tuple[Optional[str], str]]:
        """Split combined text into individual file units.

        Primary delimiter: ---FILE_SEPARATOR--- (emitted by combine()).
        Secondary split: per-file // filename: markers (from _build_per_file_units).

        Returns a list of (filename, code) tuples where ``filename`` is the
        output path from the // filename: marker (or None if no marker was
        found) and ``code`` is the file content with the // filename: line
        stripped.
        """
        stripped = re.sub(r"\n# ===== Chunk \d+:.*?=====\n", "\n", combined)
        if "---FILE_SEPARATOR---" in stripped:
            raw_parts = re.split(r"---FILE_SEPARATOR---\n?", stripped)
        else:
            raw_parts = [stripped]

        file_units: List[Tuple[Optional[str], str]] = []
        for raw in raw_parts:
            raw = raw.strip()
            if not raw:
                continue
            pieces = re.split(r"(?:^|\n)(?=// ?filename:)", raw)
            for piece in pieces:
                piece = piece.strip()
                if not piece:
                    continue
                m = re.match(r"^// ?filename: ?([^\n]*)\n?", piece)
                if m:
                    filename = m.group(1).strip()
                    # If filename is an absolute path, try to make it relative to base_path
                    # This handles cases where the transpiler (LLM) returned absolute paths
                    # in the // filename: markers (the _build_per_file_units normalization
                    # in combine() should prevent this, but we handle it defensively)
                    if filename.startswith("/") and self.base_path:
                        try:
                            filename = str(Path(filename).relative_to(self.base_path))
                        except ValueError:
                            # Not relative to base_path — strip leading slashes and use as-is
                            filename = filename.lstrip("/")
                    code = piece[m.end():].lstrip()
                    file_units.append((filename, code))
                else:
                    file_units.append((None, piece))
        return file_units

    def write_files(self, output_dir: Path, file_ext: str = "ts", src_dir: Optional[str] = None) -> Dict[str, Path]:
        """Write transpiled units to individual files.

        Each unit is written to a file. If the unit has a // filename: marker
        the file is placed at that path (under ``src_dir`` if provided);
        otherwise the file is named after its first top-level function or class. Units with no recognisable declaration
        are skipped; when ALL units are skipped the combined output is written to
        ``combined_output.<ext>``.
        """
        if not self.transpiled:
            return {}
        combined = self.combine(file_ext=file_ext)
        file_units = self._split_into_file_units(combined)
        if output_dir is None:
            return {}
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        written: Dict[str, Path] = {}
        for filename, code in file_units:
            # If the unit has an explicit // filename: marker, use that path
            if filename:
                rel_path = filename.lstrip("/")
                # If rel_path is a bare filename (no path separator), and src_dir is set,
                # place it under src_dir/.  This allows callers to redirect bare
                # output names (e.g. "math.rs") into a subdirectory (e.g. "src/")
                # without affecting multi-level paths from the LLM.
                if src_dir and "/" not in rel_path and "\\" not in rel_path:
                    rel_path = f"{src_dir}/{rel_path}"
                out_path = output_dir / rel_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(code.strip() + "\n")
                written[rel_path] = out_path
                continue

            # No explicit filename — try to name the file from the code content
            func_match = re.search(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)", code)
            cls_match = re.search(r"class\s+(\w+)", code)
            if func_match:
                name = func_match.group(1)
            elif cls_match:
                name = cls_match.group(1)
            else:
                # No recognisable top-level declaration — skip.
                # combined_output fallback below handles genuinely unplaceable content.
                continue

            rel_path = f"{src_dir or 'generated'}/{name}.{file_ext}".lstrip("/")
            out_path = output_dir / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(code.strip() + "\n")
            written[rel_path] = out_path

        if not written and combined.strip():
            sub = f"{src_dir}/" if src_dir else ""
            out_path = output_dir / f"{sub}combined_output.{file_ext}"
            out_path.write_text(combined.strip() + "\n")
            written[f"{sub}combined_output.{file_ext}"] = out_path

        return written

    def resolve_imports(self, global_exports: Optional[Dict[str, str]] = None) -> str:
        """Resolve cross-chunk imports and fix references.

        After all chunks are transpiled independently, this step rewrites
        internal import/reference statements to point to the correct
        generated output files.

        When global_exports is not provided it is built from chunk metadata
        by mapping each exported symbol to its output file path.

        Args:
            global_exports: Mapping of symbol name -> output file path.
                            If None, built from chunk metadata.

        Returns:
            The combined transpiled code with resolved cross-chunk imports.
        """
        if not self.transpiled:
            return ""

        if global_exports is None:
            global_exports = {}
            for chunk_id in sorted(self.chunks.keys()):
                chunk = self.chunks[chunk_id]
                if chunk_id not in self._chunk_file_paths:
                    continue
                for src_file in self._chunk_file_paths[chunk_id]:
                    rel = src_file.relative_to(self.base_path) if self.base_path else src_file
                    ext = rel.suffix
                    ts_ext = (
                        ".ts" if ext in (".py", ".pyw")
                        else ext if ext in (".ts", ".tsx", ".js", ".jsx")
                        else ".ts"
                    )
                    out_file = str(rel.with_suffix(ts_ext))
                    for export_name in chunk.exports:
                        global_exports[export_name] = out_file

        combined = self.combine()
        resolved = self._resolve_imports_in_text(combined, global_exports)
        return resolved

    @staticmethod
    def _resolve_imports_in_text(text: str, global_exports: Dict[str, str]) -> str:
        """Rewrite import statements in transpiled text using global_exports map.

        Handles TypeScript/JavaScript named, default, and wildcard import syntax.
        Symbols found in global_exports are preserved; when a symbol's import
        path does not match the export location, the path is rewritten.

        Lines that begin with ``//`` (such as // filename: path/to/file.ts) are
        left unchanged and are NOT processed as import statements.

        Rust ``use`` statements are also handled.
        """
        lines = text.splitlines()
        resolved_lines: List[str] = []

        for line in lines:
            stripped = line.lstrip()

            # Skip comment lines (e.g. // filename: path/to/file.ts).
            # These are NOT import statements and must not be processed.
            if stripped.startswith("//"):
                resolved_lines.append(line)
                continue

            # --- TypeScript / JavaScript ---
            js_match = _JS_IMPORT_PAT.match(line)
            if js_match:
                prefix, import_path, suffix = (js_match.group(1), js_match.group(2),
                                                js_match.group(3))
                named_match = re.search(r"import\s+\{([^}]+)\}\s+from", line)
                if named_match:
                    symbols = [s.strip() for s in named_match.group(1).split(",")]
                    resolved_symbols = [s for s in symbols if s in global_exports]
                    if resolved_symbols == symbols:
                        resolved_lines.append(line)
                    elif resolved_symbols:
                        resolved_lines.append(
                            f"import {{ {', '.join(resolved_symbols)} }}"
                            f" from {prefix.rstrip()}{import_path}{suffix}"
                        )
                    else:
                        resolved_lines.append(line)
                    continue
                resolved_lines.append(line)
                continue

            # --- Rust ---
            rust_match = re.match(r"^(\s*use\s+)([^;]+)(;.*)$", line)
            if rust_match:
                prefix, use_path, suffix = (rust_match.group(1), rust_match.group(2),
                                             rust_match.group(3))
                is_external = any(
                    use_path.startswith(ext) for ext in ("std::", "core::", "alloc::", "crate::")
                )
                if not is_external and "::" in use_path:
                    parts = use_path.rsplit("::", 1)
                    if len(parts) == 2:
                        module_path, symbol = parts
                        if symbol in global_exports:
                            resolved_lines.append(
                                f"{prefix}{module_path}::{symbol}{suffix}"
                            )
                            continue
                resolved_lines.append(line)
                continue

            resolved_lines.append(line)

        return "\n".join(resolved_lines)

    def get_chunk_order(self) -> List[int]:
        """Get the recommended processing order for chunks."""
        return self._topological_sort()


def _find_source_files(repo_path: Path, extensions: Set[str]) -> List[Path]:
    """Find all source files matching the given extensions, excluding noise dirs."""
    result = []
    for f in repo_path.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in extensions:
            continue
        try:
            rel_parts = f.relative_to(repo_path).parts
        except ValueError:
            continue
        # Skip hidden dirs, noise dirs, and test vendor dirs
        if any(part.startswith(".") for part in rel_parts):
            continue
        if any(part in IGNORE_DIRS for part in rel_parts):
            continue
        # Skip Go test files (they're not source for transpilation)
        if f.suffix == ".go" and f.name.endswith("_test.go"):
            continue
        result.append(f)
    return sorted(result)


def chunk_repository(
    repo_path: Path,
    max_functions: int = 30,
    language: Optional[str] = None,
) -> List[Chunk]:
    """Chunk an entire repository by finding source files for the given language.

    If ``language`` is None, defaults to "python" for backward compatibility.

    Args:
        repo_path: Root of the repository to chunk.
        max_functions: Maximum functions/structures per chunk.
        language: Source language (python, go, javascript, typescript, rust).
                  Determines which files are found and how imports/exports
                  are extracted.  Defaults to "python".

    Returns:
        List of Chunk objects ready for transpilation.
    """
    if language is None:
        language = "python"

    extensions = LANG_EXTENSIONS.get(language, {".py"})
    source_files = _find_source_files(repo_path, extensions)

    if not source_files:
        return []

    return create_chunks(
        source_files,
        base_path=repo_path,
        max_functions=max_functions,
        language=language,
    )
