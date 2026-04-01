"""Go source parser using the goast helper binary, with pure-Python fallback."""

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from repo_transmute.blueprint.extractor import (
    DataStructure,
    Function,
)


# ---------------------------------------------------------------------------
# goast binary support
# ---------------------------------------------------------------------------

GOAST_BINARY: Optional[Path] = None  # resolved on first call


def _find_goast() -> Optional[Path]:
    """Locate the goast binary.

    Searches in order:
      1. GOAST_BINARY env var
      2. scripts/goast/goast relative to repo root
      3. PATH
    """
    if GOAST_BINARY:
        p = Path(GOAST_BINARY)
        if p.exists():
            return p
        return None

    # Repo-root relative
    here = Path(__file__).resolve().parent  # transpiler/
    repo_root = here.parent.parent.parent  # repo-transmute/src/repo_transmute/ → repo-transmute/
    candidate = repo_root / "scripts" / "goast" / "goast"
    if candidate.exists():
        return candidate

    # PATH
    import shutil
    path_binary = shutil.which("goast")
    if path_binary:
        return Path(path_binary)

    return None


def _parse_goast_output(raw: str) -> dict:
    """Parse JSON emitted by goast, tolerating empty or malformed output."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"functions": [], "structs": [], "interfaces": []}


# ---------------------------------------------------------------------------
# Import extraction (pure Python)
# ---------------------------------------------------------------------------

@dataclass
class GoImport:
    """Represents a Go import."""
    path: str
    names: List[str] = field(default_factory=list)  # named imports, empty for default


def _extract_go_imports(content: str) -> List[GoImport]:
    """Extract all imports from Go source (pure Python, no goast needed).

    Handles:
      - import "fmt"                    → GoImport("fmt")
      - import "math/rand"              → GoImport("math/rand")
      - import name "fmt"               → GoImport("fmt", ["name"])
      - import alias "fmt"              → GoImport("fmt", ["alias"])
      - import ( "fmt" "os" )           → GoImport("fmt"), GoImport("os")
      - import ( "fmt"; "os" )          → multi-line with semicolons
    """
    imports: List[GoImport] = []

    # Remove line comments
    stripped = re.sub(r"//.*", "", content)
    # Remove block comments
    stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)

    # Match import blocks: import ( ... )
    block_pattern = r"import\s*\(([^)]*)\)"
    for m in re.finditer(block_pattern, stripped, re.DOTALL):
        block_body = m.group(1)
        for line in block_body.splitlines():
            line = line.strip().rstrip(";").strip()
            if not line:
                continue
            imp = _parse_single_import(line)
            if imp:
                imports.append(imp)
        stripped = stripped[:m.start()] + stripped[m.end():]

    # Match remaining single-line imports: import "..." or import name "..."
    single_pattern = r'\bimport\s+(?:(\w+)\s+)?"([^"]+)"'
    for m in re.finditer(single_pattern, stripped):
        name_part = m.group(1)  # may be None
        path = m.group(2)
        imports.append(GoImport(path=path, names=[name_part] if name_part else []))

    return imports


def _parse_single_import(line: str) -> Optional[GoImport]:
    """Parse a single import line, returning GoImport or None."""
    line = line.strip().strip(";").strip()
    if not line:
        return None
    # import "path"  or  import name "path"  or  import alias "path"
    m = re.match(r'(\w+)?\s*"([^"]+)"', line)
    if m:
        name = m.group(1)
        path = m.group(2)
        return GoImport(path=path, names=[name] if name else [])
    return None


# ---------------------------------------------------------------------------
# Function body extraction helpers (pure Python)
# ---------------------------------------------------------------------------

def _find_brace_pair(content: str, start: int) -> Tuple[int, int]:
    """Find matching closing brace given an opening brace at `start`.

    Returns (open_idx, close_idx).  Handles strings and comments.
    The cursor starts searching from `start` (the '{').
    """
    depth = 0
    i = start
    in_string = False
    string_char = None
    prev_char = None

    while i < len(content):
        ch = content[i]

        if not in_string:
            if ch in ('"', "'", '`'):
                in_string = True
                string_char = ch
                if ch == '`':
                    # Raw string — find closing backtick
                    i += 1
                    while i < len(content):
                        if content[i] == '`':
                            in_string = False
                            break
                        i += 1
                    if in_string:
                        break  # unclosed raw string
                    prev_char = ch
                    i += 1
                    continue
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return start, i
        else:
            if ch == string_char and prev_char != '\\':
                in_string = False
                string_char = None

        prev_char = ch
        i += 1

    return start, -1  # no match found


def _extract_go_function_bodies(content: str) -> dict:
    """Extract all top-level function definitions with full bodies.

    Scans raw content line-by-line to avoid comment-stripping position mapping issues.

    Returns dict mapping function name -> dict with keys:
      name, signature, line, body, docstring, is_method, receiver
    """
    results = {}
    lines = content.splitlines()

    # We need to find func declarations and track brace depth across lines.
    # Pattern: func [receiver] Name(params) [return_type] {
    # The opening { may be on the same line or several lines later.
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()

        # Skip empty lines and pure comment lines
        if not line or line.startswith("//"):
            i += 1
            continue

        # Check for func keyword
        if not line.startswith("func "):
            i += 1
            continue

        # Found a func declaration — collect all lines until we find the opening {
        func_start_line = i
        func_lines = [line]

        # Find opening brace
        brace_line_idx = None
        brace_col = None
        for li in range(i, n):
            func_line = lines[li]
            bi = func_line.find("{")
            if bi != -1:
                brace_line_idx = li - i
                brace_col = bi
                func_lines.append(func_line)
                break
            func_lines.append(func_line)

        if brace_col is None:
            i += 1
            continue  # malformed — no opening brace

        # Now func_lines[brace_line_idx] contains the {
        # func_lines is a list of lines in the declaration (not including body after {)
        decl_text = "\n".join(func_lines)

        # Extract signature info from the declaration text (up to and including the {)
        sig_up_to_brace = "\n".join(
            func_lines[j] for j in range(brace_line_idx + 1)
        )[:brace_col] if brace_line_idx > 0 else func_lines[0][:brace_col]
        sig_before_name = sig_up_to_brace.strip()

        # Parse: func [receiver] Name(params) [return_type]
        # Strip "func " prefix
        sig = sig_before_name[4:].strip()  # remove leading "func"

        # Extract receiver: (p *Person) or (x Type)
        receiver = None
        if sig.startswith("("):
            paren_end = sig.find(")")
            if paren_end != -1:
                receiver = sig[1:paren_end]
                sig = sig[paren_end + 1:].strip()

        # Now sig is "Name(params) [return_type]"
        # Extract name and params+return
        m = re.match(r'(\w+)\s*\(([^)]*)\)\s*(.*)', sig)
        if not m:
            i += 1
            continue
        name = m.group(1)
        params = m.group(2)
        ret_type = m.group(3).strip()

        # Build signature string
        full_sig_parts = []
        if receiver:
            full_sig_parts.append(f"({receiver})")
        full_sig_parts.append(f"({params})")
        if ret_type:
            full_sig_parts.append(ret_type)
        signature = " ".join(full_sig_parts)

        # Calculate raw byte offset for the opening {
        raw_decl_end = sum(len(lines[j]) + 1 for j in range(func_start_line + brace_line_idx)) + brace_col

        # Find closing brace by tracking depth from the opening {
        body_start = raw_decl_end + 1  # after the opening {
        _, body_end = _find_brace_pair(content, raw_decl_end)
        if body_end == -1:
            i += 1
            continue

        body = content[body_start:body_end + 1]

        # Line number of the func keyword
        line_number = func_start_line + 1  # 1-indexed

        # Extract docstring: comment lines immediately before this func
        docstring = None
        doc_lines = []
        for dl in range(func_start_line - 1, -1, -1):
            prev = lines[dl].strip()
            if prev.startswith("//"):
                doc_lines.append(prev[2:].strip())
            elif prev == "":
                continue
            else:
                break
        if doc_lines:
            docstring = "\n".join(reversed(doc_lines))

        results[name] = {
            "name": name,
            "signature": signature,
            "line": line_number,
            "body": body,
            "docstring": docstring,
            "is_method": receiver is not None,
            "receiver": receiver,
        }

        # Move past this function's closing brace line
        closing_line = content[:body_end].count("\n")
        i = closing_line + 1

    return results


def _extract_go_docstring(prefix: str) -> Optional[str]:
    """Extract a leading doc comment from the lines preceding a declaration."""
    lines = prefix.splitlines()
    doc_lines = []
    for line in reversed(lines):
        stripped = line.strip()
        if stripped.startswith("//"):
            doc_lines.append(stripped[2:].strip())
        elif stripped == "":
            continue
        else:
            break
    if doc_lines:
        return "\n".join(reversed(doc_lines))
    return None


# ---------------------------------------------------------------------------
# Struct / interface helpers (pure Python)
# ---------------------------------------------------------------------------

def _find_type_body(content: str, keyword: str) -> List[dict]:
    """Find all type declarations of a given kind (struct or interface).

    Returns list of dicts with keys: name, docstring, line, fields/methods, body_text.
    """
    results = []
    lines = content.splitlines()
    n = len(lines)
    i = 0

    type_pattern = re.compile(
        r'\btype\s+(\w+)\s+' + keyword + r'\s*\{'
    )

    while i < n:
        line = lines[i].strip()
        m = type_pattern.match(line)
        if not m:
            i += 1
            continue

        name = m.group(1)
        decl_line = i

        # Collect lines until opening {
        decl_lines = [line]
        brace_line_idx = 0
        brace_col = line.index("{")
        for li in range(i + 1, n):
            decl_lines.append(lines[li])
            if "{" in lines[li]:
                brace_line_idx = li - i
                brace_col = lines[li].index("{")
                break

        # Compute raw offset for opening {
        raw_brace = sum(len(lines[j]) + 1 for j in range(i + brace_line_idx)) + brace_col

        # Find closing brace
        _, close_brace = _find_brace_pair(content, raw_brace)
        if close_brace == -1:
            i += 1
            continue

        body_start = raw_brace + 1
        body_text = content[body_start:close_brace]

        # Extract docstring (comment lines above the type declaration)
        doc_lines = []
        for dl in range(decl_line - 1, -1, -1):
            prev = lines[dl].strip()
            if prev.startswith("//"):
                doc_lines.append(prev[2:].strip())
            elif prev == "":
                continue
            else:
                break
        docstring = "\n".join(reversed(doc_lines)) if doc_lines else None

        # Parse fields or methods from body
        items = []
        for body_line in body_text.splitlines():
            stripped = body_line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            if keyword == "struct":
                # Field: Name Type [tags]
                # Remove json tags and other tags in backticks
                clean = re.sub(r'`[^`]*`', '', stripped).strip()
                parts = clean.split()
                if len(parts) >= 2:
                    field_name = parts[-2]
                    field_type = parts[-1]
                    items.append(f"{field_name} {field_type}")
            else:
                # Interface method: Name(params) return_type
                mm = re.match(r'(\w+)\s*\(([^)]*)\)\s*([^\n;]*?)\s*$', stripped)
                if mm:
                    m_name, m_params, m_ret = mm.group(1), mm.group(2), mm.group(3).strip()
                    sig = f"({m_params})"
                    if m_ret:
                        sig += f" {m_ret}"
                    items.append({"name": m_name, "signature": sig})

        results.append({
            "name": name,
            "docstring": docstring,
            "line": decl_line + 1,
            "body_text": body_text,
            "items": items,
        })

        i = content[:close_brace].count("\n") + 2

    return results


# ---------------------------------------------------------------------------
# Main extractors
# ---------------------------------------------------------------------------

def extract_from_go(file_path: Path) -> List[Function]:
    """Extract top-level functions from a Go source file.

    Uses the goast helper binary when available; falls back to a pure-Python
    regex+brace-tracking implementation that captures full bodies.
    """
    content = file_path.read_text()

    goast = _find_goast()
    if goast is not None:
        try:
            result = subprocess.run(
                [str(goast), str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            data = _parse_goast_output(result.stdout)
            functions = []
            for f in data.get("functions", []):
                if f.get("is_method"):
                    continue
                functions.append(
                    Function(
                        name=f["name"],
                        signature=f.get("signature", ""),
                        file=str(file_path),
                        line=f.get("line", 0),
                        docstring=f.get("doc", "").strip() or None,
                    )
                )
            return functions
        except Exception:
            pass

    # Pure-Python fallback — extracts full bodies
    funcs = []
    funcs_by_name = _extract_go_function_bodies(content)
    for name, info in funcs_by_name.items():
        if info["is_method"]:
            # Skip methods — they're attached to structs
            continue
        funcs.append(
            Function(
                name=info["name"],
                signature=info["signature"],
                file=str(file_path),
                line=info["line"],
                docstring=info.get("docstring"),
                body=info.get("body", ""),
            )
        )
    return funcs


def extract_structs_from_go(file_path: Path) -> List[DataStructure]:
    """Extract struct definitions from a Go source file."""
    content = file_path.read_text()

    goast = _find_goast()
    if goast is not None:
        try:
            result = subprocess.run(
                [str(goast), str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            data = _parse_goast_output(result.stdout)
            structs = []
            for s in data.get("structs", []) or []:
                fields = [f"{fi['name']} {fi['type']}" for fi in s.get("fields", []) or []]
                structs.append(
                    DataStructure(
                        name=s["name"],
                        type="struct",
                        file=str(file_path),
                        line=s.get("line", 0),
                        fields=fields,
                        docstring=s.get("doc", "").strip() or None,
                    )
                )
            return structs
        except Exception:
            pass

    # Pure-Python fallback
    structs = []
    for entry in _find_type_body(content, "struct"):
        structs.append(
            DataStructure(
                name=entry["name"],
                type="struct",
                file=str(file_path),
                line=entry["line"],
                fields=entry["items"],
                docstring=entry.get("docstring"),
            )
        )
    return structs


def extract_interfaces_from_go(file_path: Path) -> List[DataStructure]:
    """Extract interface definitions from a Go source file."""
    content = file_path.read_text()

    goast = _find_goast()
    if goast is not None:
        try:
            result = subprocess.run(
                [str(goast), str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            data = _parse_goast_output(result.stdout)
            interfaces = []
            for iface in data.get("interfaces", []) or []:
                methods = []
                for m in iface.get("methods", []) or []:
                    methods.append(
                        Function(
                            name=m["name"],
                            signature=f"({m.get('signature', '')})",
                            file=str(file_path),
                            line=iface.get("line", 0),
                        )
                    )
                interfaces.append(
                    DataStructure(
                        name=iface["name"],
                        type="interface",
                        file=str(file_path),
                        line=iface.get("line", 0),
                        docstring=iface.get("doc", "").strip() or None,
                        methods=methods,
                    )
                )
            return interfaces
        except Exception:
            pass

    # Pure-Python fallback
    interfaces = []
    for entry in _find_type_body(content, "interface"):
        methods = [
            Function(name=it["name"], signature=it["signature"], file=str(file_path), line=entry["line"])
            for it in entry["items"]
        ]
        interfaces.append(
            DataStructure(
                name=entry["name"],
                type="interface",
                file=str(file_path),
                line=entry["line"],
                docstring=entry.get("docstring"),
                methods=methods,
            )
        )
    return interfaces


def extract_imports_from_go(file_path: Path) -> List[GoImport]:
    """Extract imports from a Go source file (pure Python)."""
    content = file_path.read_text()
    return _extract_go_imports(content)


# ---------------------------------------------------------------------------
# Regex-based function extraction (no goast) — kept for backward compat
# ---------------------------------------------------------------------------

_FUNC_RE = re.compile(
    r"^(?:export\s+)?func\s+(?:\(([^)]+)\)\s*)?(\w+)\s*\(([^)]*)\)\s*([^\n{]*)"
)


def _extract_from_go_regex(file_path: Path) -> List[Function]:
    """Fallback regex extraction for environments without goast.

    Less accurate than the goast binary — use only as last resort.
    """
    content = file_path.read_text()
    functions = []
    for i, line in enumerate(content.splitlines(), 1):
        m = _FUNC_RE.match(line.strip())
        if m:
            receiver, name, params, ret = m.group(1), m.group(2), m.group(3), m.group(4).strip()
            sig = f"({params})"
            if ret:
                sig += f" {ret}"
            functions.append(
                Function(
                    name=name,
                    signature=sig,
                    file=str(file_path),
                    line=i,
                )
            )
    return functions
