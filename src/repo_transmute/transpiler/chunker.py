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
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        tree = ast.parse(content, filename=str(file_path))
        
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                count += 1
        return count
    except Exception:
        # Fallback: count def/class lines
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        return len(re.findall(r'^(\s*)(def|class|async\s+def)\s+', content, re.MULTILINE))


def extract_imports(file_path: Path) -> List[str]:
    """Extract import statements from a Python file."""
    try:
        content = file_path.read_text(encoding='utf-8', errors='ignore')
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
        content = file_path.read_text(encoding='utf-8', errors='ignore')
        tree = ast.parse(content, filename=str(file_path))
        
        exports = []
        
        # Check for __all__
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
        
        # Add top-level functions and classes
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                exports.append(node.name)
        
        return exports
    except Exception:
        return []


def get_module_name(file_path: Path, base_path: Path) -> str:
    """Get the module name for a file relative to base_path."""
    rel_path = file_path.relative_to(base_path)
    parts = list(rel_path.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts) if parts else ""


def chunk_by_files(files: List[Path], max_functions: int = 30) -> List[List[Path]]:
    """
    Group files into chunks that respect module boundaries.
    
    Each chunk contains files that are self-contained and won't exceed
    the function limit. Files within the same directory are grouped together
    to maintain module coherence.
    
    Args:
        files: List of Python file paths to chunk
        max_functions: Maximum number of functions per chunk (default: 30)
    
    Returns:
        List of chunks, each containing a list of file paths
    """
    if not files:
        return []
    
    # Group files by parent directory (module)
    modules: Dict[Path, List[Path]] = {}
    for f in files:
        parent = f.parent
        if parent not in modules:
            modules[parent] = []
        modules[parent].append(f)
    
    # Sort modules by path to ensure consistent ordering
    sorted_modules = sorted(modules.items(), key=lambda x: str(x[0]))
    
    chunks: List[List[Path]] = []
    current_chunk: List[Path] = []
    current_functions = 0
    
    for module_path, module_files in sorted_modules:
        # Sort files within module (__init__.py first, then alphabetical)
        sorted_files = sorted(module_files, key=lambda f: (
            0 if f.name == "__init__.py" else 1,
            f.name
        ))
        
        for file_path in sorted_files:
            func_count = count_functions(file_path)
            
            # If single file exceeds limit, it goes in its own chunk
            if func_count > max_functions:
                # Flush current chunk first
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = []
                    current_functions = 0
                
                # Put this large file alone
                chunks.append([file_path])
                continue
            
            # Check if adding this file would exceed limit
            if current_functions + func_count > max_functions and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_functions = 0
            
            current_chunk.append(file_path)
            current_functions += func_count
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def create_chunks(files: List[Path], base_path: Optional[Path] = None, max_functions: int = 30) -> List[Chunk]:
    """
    Create Chunk objects with metadata from a list of files.
    
    Args:
        files: List of Python file paths
        base_path: Base path for calculating module names (defaults to common ancestor)
        max_functions: Maximum functions per chunk
    
    Returns:
        List of Chunk objects with populated metadata
    """
    if not files:
        return []
    
    if base_path is None:
        # Find common ancestor
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
    
    # Get file chunks
    file_chunks = chunk_by_files(files, max_functions)
    
    chunks = []
    for chunk_id, chunk_files in enumerate(file_chunks):
        # Collect all imports and exports
        all_imports: Set[str] = set()
        all_exports: Set[str] = set()
        
        for f in chunk_files:
            all_imports.update(extract_imports(f))
            all_exports.update(extract_exports(f))
        
        chunk = Chunk(
            id=chunk_id,
            files=chunk_files,
            imports=sorted(all_imports),
            exports=sorted(all_exports),
            dependencies=[]
        )
        chunks.append(chunk)
    
    # Calculate dependencies between chunks
    for i, chunk in enumerate(chunks):
        chunk_imports = set(chunk.imports)
        
        for j, other_chunk in enumerate(chunks):
            if i == j:
                continue
            
            # Check if any import could be satisfied by other chunk's exports
            for export in other_chunk.exports:
                if export in chunk_imports:
                    if j not in chunk.dependencies:
                        chunk.dependencies.append(j)
    
    return chunks


class Reassembler:
    """
    Combines transpiled chunks back into a single codebase.
    
    Handles cross-chunk import resolution and proper ordering
    based on dependencies.
    """
    
    def __init__(self, chunks: List[Chunk], base_path: Optional[Path] = None):
        """
        Initialize the reassembler with chunk metadata.
        
        Args:
            chunks: List of Chunk objects with metadata
            base_path: Base path for resolving file paths
        """
        self.chunks = {chunk.id: chunk for chunk in chunks}
        self.base_path = base_path or Path.cwd()
        self.transpiled: Dict[int, str] = {}
    
    def add_transpiled(self, chunk_id: int, code: str) -> None:
        """
        Add transpiled code for a chunk.
        
        Args:
            chunk_id: The chunk ID this code belongs to
            code: The transpiled code string
        """
        self.transpiled[chunk_id] = code
    
    def _topological_sort(self) -> List[int]:
        """Sort chunks by dependencies (chunks with fewer deps first)."""
        # Simple sort: put chunks with no dependencies first
        sorted_ids = []
        remaining = set(self.transpiled.keys())
        
        while remaining:
            # Find chunks with no unsatisfied dependencies
            ready = []
            for chunk_id in remaining:
                chunk = self.chunks[chunk_id]
                deps = [d for d in chunk.dependencies if d in remaining]
                if not deps:
                    ready.append(chunk_id)
            
            if not ready:
                # Circular dependency or missing deps - just take remaining
                ready = list(remaining)
            
            sorted_ids.extend(sorted(ready))
            remaining -= set(ready)
        
        return sorted_ids
    
    def combine(self) -> str:
        """
        Merge all transpiled chunks into a single string.
        
        Chunks are ordered by dependency (chunks without dependencies first).
        
        Returns:
            Combined code from all chunks
        """
        if not self.transpiled:
            return ""
        
        sorted_ids = self._topological_sort()
        
        parts = []
        for chunk_id in sorted_ids:
            chunk = self.chunks[chunk_id]
            code = self.transpiled.get(chunk_id, "")
            
            # Add header comment
            if chunk.files:
                file_names = ", ".join(f.name for f in chunk.files[:3])
                if len(chunk.files) > 3:
                    file_names += f" (+{len(chunk.files) - 3} more)"
                parts.append(f"\n# ===== Chunk {chunk_id}: {file_names} =====\n")
            
            parts.append(code)
        
        return "\n".join(parts)
    
    def resolve_imports(self, global_exports: Optional[Dict[str, str]] = None) -> str:
        """
        Resolve cross-chunk imports and fix references.
        
        Args:
            global_exports: Optional mapping of names to their definitions
                           for resolving imports not in chunk exports
        
        Returns:
            Combined code with resolved imports
        """
        combined = self.combine()
        
        if global_exports is None:
            # Build export map from all chunks
            global_exports = {}
            for chunk in self.chunks.values():
                for export in chunk.exports:
                    # Map export name to its chunk
                    if export not in global_exports:
                        global_exports[export] = f"chunk_{chunk.id}"
        
        # For now, just return combined code
        # In a full implementation, this would:
        # 1. Parse the combined code
        # 2. Resolve import statements to local definitions
        # 3. Add necessary forward declarations
        # 4. Handle circular dependencies
        
        return combined
    
    def get_chunk_order(self) -> List[int]:
        """
        Get the recommended processing order for chunks.
        
        Returns:
            List of chunk IDs in dependency order
        """
        return self._topological_sort()


# Convenience functions for quick usage
def chunk_repository(repo_path: Path, max_functions: int = 30) -> List[Chunk]:
    """
    Chunk an entire repository by finding all Python files.
    
    Args:
        repo_path: Path to the repository root
        max_functions: Maximum functions per chunk
    
    Returns:
        List of Chunk objects
    """
    py_files = list(repo_path.rglob("*.py"))
    # Exclude common non-source directories
    py_files = [
        f for f in py_files
        if not any(part.startswith('.') or part in ('venv', 'env', '__pycache__', 'node_modules')
                   for part in f.parts)
    ]
    return create_chunks(py_files, base_path=repo_path, max_functions=max_functions)


if __name__ == "__main__":
    # Quick test with the test repo
    import sys
    
    test_repo = Path("data/cache/lfnovo__open-notebook")
    if test_repo.exists():
        print(f"Testing with {test_repo}...")
        chunks = chunk_repository(test_repo, max_functions=30)
        
        print(f"\nCreated {len(chunks)} chunks:")
        for chunk in chunks:
            func_count = sum(count_functions(f) for f in chunk.files)
            print(f"  Chunk {chunk.id}: {len(chunk.files)} files, ~{func_count} functions")
            print(f"    Files: {[f.name for f in chunk.files[:5]]}{'...' if len(chunk.files) > 5 else ''}")
            print(f"    Dependencies: {chunk.dependencies}")
    else:
        print(f"Test repo not found at {test_repo}")
        sys.exit(1)
