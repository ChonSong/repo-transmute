"""Go test stub generator — AST-aware test generation for Go source."""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from repo_transmute.transpiler.go_parser import (
    _extract_go_function_bodies,
    _extract_go_imports,
    extract_structs_from_go,
    GoImport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_test_name(func_name: str) -> str:
    """Convert a function name to a Go test name (Test prefix + CamelCase)."""
    # Already starts with Test?
    if func_name.startswith("Test"):
        return func_name
    return f"Test{func_name[0].upper()}{func_name[1:]}"


def _param_names(params: str) -> List[str]:
    """Extract parameter names from a Go signature string like 'a, b int, c string'."""
    if not params.strip():
        return []
    names = []
    for part in params.split(","):
        part = part.strip()
        if not part:
            continue
        # "a int" → a,  "a, b int" → a, b
        tokens = part.split()
        if tokens:
            names.append(tokens[0])
    return names


def _extract_params_from_signature(sig: str, is_method: bool = False) -> List[str]:
    """Extract parameter names from a full Go function signature.

    Handles both top-level functions and methods:
    - Top-level: "(a, b int) int" -> ["a", "b"]
    - Method: "(p *Person) (nums []int) int" -> ["nums"]
    - Method with no params: "(p *Person) () string" -> []

    Args:
        sig: Full signature like "(a, b int) int" or "(p *Person) (nums []int) int"
        is_method: True if this is a method (has receiver in first parens)

    Returns:
        List of parameter names (excluding receiver for methods)
    """
    if not sig or "(" not in sig:
        return []

    # Find the parameter section
    if is_method:
        # For methods, signature is: "(receiver) (params) return" or "(receiver) () return"
        # We need to find the second '(' to get to actual params
        first_paren = sig.index("(")
        try:
            second_paren = sig.index("(", first_paren + 1)
        except ValueError:
            # No second paren - method has no params, just receiver
            return []
        
        # Find matching close paren
        depth = 1
        i = second_paren + 1
        while i < len(sig) and depth > 0:
            if sig[i] == "(":
                depth += 1
            elif sig[i] == ")":
                depth -= 1
            i += 1
        param_section = sig[second_paren + 1:i - 1]
    else:
        # For top-level: "(a, b int) return"
        first_paren = sig.index("(")
        # Find matching close paren
        depth = 1
        i = first_paren + 1
        while i < len(sig) and depth > 0:
            if sig[i] == "(":
                depth += 1
            elif sig[i] == ")":
                depth -= 1
            i += 1
        param_section = sig[first_paren + 1:i - 1]

    # Now parse the param section like _param_names does
    return _param_names(param_section)


def _extract_return_type(sig: str, is_method: bool = False) -> str:
    """Extract return type from a Go function signature.

    Handles both top-level functions and methods:
    - Top-level: "(a, b int) int" -> "int"
    - Method: "(p *Person) (nums []int) int" -> "int"
    - Method no params: "(p *Person) () string" -> "string"
    - Multi-return: "(a int) (int, error)" -> "(int, error)"

    Args:
        sig: Full signature
        is_method: True if this is a method

    Returns:
        Return type string (may be empty for no return)
    """
    if not sig or ")" not in sig:
        return ""

    # Count closing parens - if there's more than one, the return type is in parens
    close_paren_count = sig.count(")")

    if close_paren_count == 1:
        # Simple case: "(params) return" - return is after the single )
        # Also covers method with no params: "(p *Person) () string" - returns "string"
        last_paren = sig.rindex(")")
        return sig[last_paren + 1:].strip()
    elif close_paren_count >= 2:
        # Multi-return: "(params) (return1, return2)" - find second-to-last )
        # Or method: "(receiver) (params) return" - return is after the last )
        # 
        # For multi-return like "(a int) (int, error)", the return is in parens before the last )
        # We need to find the SECOND-TO-LAST ) to get the full return type
        paren_positions = [i for i, c in enumerate(sig) if c == ')']
        
        if is_method:
            # For methods: "(receiver) (params) return" or "(receiver) () return"
            # Return is after the last )
            last_paren = paren_positions[-1]
            return sig[last_paren + 1:].strip()
        else:
            # For top-level with multi-return: "(params) (int, error)"
            # Return starts after the second-to-last )
            # Example: "(path string) ([]byte, error)"
            # paren_positions = [12, 28]
            # Second-to-last is 12, return starts at 13: "[]byte, error)"
            # We need content from 13 to 28, but excluding the closing )
            return_start = paren_positions[-2] + 1
            return_end = paren_positions[-1]
            return sig[return_start:return_end].strip()

    return ""


def _needs_import(imports: List[GoImport], pkg: str) -> bool:
    """Check if an import for `pkg` is already present."""
    return any(imp.path == pkg for imp in imports)


def _suggest_imports(func_info: dict) -> List[str]:
    """Suggest additional imports needed for test scaffolding.

    Returns a list of package paths that should be added.
    """
    suggestions = set()
    imports_section = str(func_info.get("imports", []))

    # If the function returns an error, suggest "errors"
    sig = func_info.get("signature", "")
    ret_type = ""
    if ")" in sig:
        # signature is like "(a int) string" or "(a int)" for no return
        paren_end = sig.index(")")
        ret_type = sig[paren_end + 1:].strip()

    if ret_type and ret_type != "":
        if ret_type.startswith("error"):
            suggestions.add("errors")
        elif ret_type.startswith("[]"):
            suggestions.add("fmt")  # for make/append in test setup
        elif ret_type not in ("int", "string", "bool", "byte", "rune", "float64", "float32", "int32", "int64"):
            # complex types likely need fmt or the type's package
            suggestions.add("fmt")

    # If the function signature mentions error in params
    if "error" in sig.lower():
        suggestions.add("errors")

    # If body contains assertions like reflect.DeepEqual
    body = func_info.get("body", "")
    if "reflect" in body or "DeepEqual" in body:
        suggestions.add("reflect")
    if "json" in body:
        suggestions.add("encoding/json")

    return sorted(suggestions)


def _funcs_as_dict(funcs_list: List[dict]) -> Dict[str, dict]:
    """Convert list from _extract_go_function_bodies to name->info dict.

    Uses a composite key (name + is_method flag) so both top-level functions
    and methods with the same name are preserved.
    """
    out: Dict[str, dict] = {}
    for info in funcs_list:
        name = info["name"]
        is_method = info.get("is_method", False)
        # Composite key: "name" for top-level, "name+method" for methods
        key = name if not is_method else f"{name}+method"
        if key not in out:
            out[key] = info
        else:
            # Keep the one with lower line number
            existing_line = out[key].get("line", float("inf"))
            new_line = info.get("line", float("inf"))
            if new_line < existing_line:
                out[key] = info
    return out


# ---------------------------------------------------------------------------
# Core test stub generation
# ---------------------------------------------------------------------------

def generate_test_stub(func_info: dict, target_pkg: str = "fixtures") -> str:
    """Generate a Go test function stub.

    Args:
        func_info: dict from _extract_go_function_bodies with keys:
            name, signature, body, docstring, is_method, receiver, line
        target_pkg: the package being tested (used in the test package declaration)

    Returns:
        Go source code for the test function.
    """
    name = func_info["name"]
    sig = func_info["signature"]
    is_method = func_info.get("is_method", False)
    receiver = func_info.get("receiver", "")

    test_name = _to_test_name(name)

    # Use the new helper to extract params correctly (handles method receiver)
    param_names = _extract_params_from_signature(sig, is_method=is_method)

    # Use the new helper to extract return type correctly
    ret_type = _extract_return_type(sig, is_method=is_method)

    # Check if error is in return types (for multi-return like (int, error))
    returns_error = "error" in ret_type

    # Build the test function signature
    if is_method:
        # Methods: func TestFoo(t *testing.T) { ... }
        # We keep receiver in a commented note since t.Test doesn't support it
        lines = [
            f"// Test for {name} (method on {receiver})",
            f"func {test_name}(t *testing.T) {{",
        ]
    else:
        lines = [
            f"// Test for {name}",
            f"func {test_name}(t *testing.T) {{",
        ]

    # If the function has parameters, create zero-value setup
    if param_names:
        lines.append(f"    // TODO: set up test inputs")
        for pname in param_names:
            lines.append(f"    // var {pname} = <value>")

    # If the function returns a value, set up result variable
    if ret_type and ret_type != "error" and ret_type != "":
        lines.append(f"    var want {ret_type}")
        lines.append(f"    // TODO: set want = expected value")
        lines.append("")

    # Build the function call
    if is_method:
        # For a method, we'd need a receiver instance
        recv_type = receiver.split()[-1]  # "p *Person" → "Person"
        lines.append(f"    // receiver := &{recv_type}{{}}  // TODO: initialize receiver")

        if param_names:
            params_str = ", ".join(f"<{p}>" for p in param_names)
            call = f"    got := receiver.{name}({params_str})"
        else:
            call = f"    got := receiver.{name}()"
    else:
        # Top-level function
        if param_names:
            params_str = ", ".join(f"<{p}>" for p in param_names)
            call = f"    got := {name}({params_str})"
        else:
            call = f"    got := {name}()"

    lines.append(f"    {call}")
    lines.append("")

    # Add assertion
    if ret_type == "error" or returns_error:
        lines.append("    if got != nil {")
        lines.append(f'        t.Errorf("{name}() error = %v, want nil", got)')
        lines.append("    }")
    elif ret_type and ret_type != "":
        lines.append("    if got != want {")
        lines.append(f'        t.Errorf("{name}() = %v, want %v", got, want)')
        lines.append("    }")
    else:
        lines.append("    // TODO: add assertions")
        lines.append('    t.Log("test not yet implemented")')

    lines.append("}")

    return "\n".join(lines)


def _has_testing_import(lines: List[str]) -> bool:
    """Check if the import block already includes testing."""
    # Look for 'import (' ... 'testing' ... ')'
    in_import_block = False
    for line in lines:
        if line == "import (":
            in_import_block = True
        elif in_import_block and line == ")":
            break
        elif in_import_block and "testing" in line:
            return True
    return False


def generate_test_file(
    file_path: Path,
    funcs_to_test: Optional[List[str]] = None,
) -> str:
    """Generate a Go test file for a .go source file.

    Args:
        file_path: Path to the Go source file
        funcs_to_test: Optional list of function names to test.
                       If None, tests all public top-level functions.

    Returns:
        Go test file content as a string.
    """
    content = file_path.read_text()
    pkg_name = _detect_package_name(content)
    all_funcs_list = _extract_go_function_bodies(content)
    all_funcs = _funcs_as_dict(all_funcs_list)

    # Filter to top-level functions (not methods) that we want to test
    top_level = {
        name: info
        for name, info in all_funcs.items()
        if not info["is_method"]
    }
    if funcs_to_test is not None:
        top_level = {n: info for n, info in top_level.items() if n in funcs_to_test}

    # Collect all imports needed
    all_imports = _extract_go_imports(content)
    needed_imports: Set[str] = set()

    for imp in all_imports:
        needed_imports.add(imp.path)

    # Build import block
    import_lines = ['"testing"']
    if needed_imports:
        import_lines.append(f'"{pkg_name}"  // TODO: replace with actual import path')
        # Also suggest common test imports
        for pkg in ["fmt", "errors", "reflect"]:
            if not _needs_import(all_imports, pkg):
                pass  # don't auto-add, just note it

    lines = [
        f"package {pkg_name}_test",
        "",
        "import (",
    ]

    # Deduplicate and add imports
    unique_imports: Dict[str, List[str]] = {}
    for imp in all_imports:
        if imp.path not in unique_imports:
            unique_imports[imp.path] = imp.names

    for path, names in sorted(unique_imports.items()):
        if names:
            for n in names:
                lines.append(f'    {n} "{path}"')
        else:
            lines.append(f'    "{path}"')

    # Add testing import if not already present
    if not _has_testing_import(lines):
        lines.append('    "testing"')

    lines.append(")")
    lines.append("")

    # Generate test for each top-level function
    for func_name, func_info in sorted(top_level.items()):
        stub = generate_test_stub(func_info, target_pkg=pkg_name)
        lines.append(stub)
        lines.append("")

    return "\n".join(lines)


def generate_test_file_for_methods(
    file_path: Path,
    struct_name: str,
    target_pkg: str = "fixtures",
) -> str:
    """Generate a Go test file for all methods on a specific struct.

    Args:
        file_path: Path to the Go source file
        struct_name: Name of the struct whose methods to test
        target_pkg: Package being tested

    Returns:
        Go test file content as a string.
    """
    content = file_path.read_text()
    pkg_name = _detect_package_name(content)
    all_funcs_list = _extract_go_function_bodies(content)
    all_funcs = _funcs_as_dict(all_funcs_list)

    # Filter to methods on the given struct
    methods = {
        name: info
        for name, info in all_funcs.items()
        if info["is_method"] and struct_name in info.get("receiver", "")
    }

    if not methods:
        return f"// No methods found for struct {struct_name}\npackage {pkg_name}_test\n"

    # Collect imports
    all_imports = _extract_go_imports(content)

    lines = [
        f"package {pkg_name}_test",
        "",
        'import "testing"',
        "",
    ]

    for method_name, method_info in sorted(methods.items()):
        stub = generate_test_stub_method(method_info, target_pkg=target_pkg)
        lines.append(stub)
        lines.append("")

    return "\n".join(lines)


def generate_test_stub_method(func_info: dict, target_pkg: str = "fixtures") -> str:
    """Generate a Go test stub for a method (with receiver instance setup)."""
    name = func_info["name"]
    sig = func_info["signature"]
    receiver = func_info.get("receiver", "")

    test_name = _to_test_name(name)

    # Use the new helper - methods have is_method=True
    param_names = _extract_params_from_signature(sig, is_method=True)
    ret_type = _extract_return_type(sig, is_method=True)

    # Check if error is in return types
    returns_error = "error" in ret_type

    # Extract receiver type
    recv_type = receiver.split()[-1] if receiver else "Unknown"

    lines = [
        f"// Test for {name} (method on {receiver})",
        f"func {test_name}(t *testing.T) {{",
    ]

    # Initialize receiver
    lines.append(f"    // receiver := &{recv_type}{{}}  // TODO: initialize receiver")
    lines.append("")

    # Add param placeholders
    for pname in param_names:
        lines.append(f"    // var {pname} = <value>")

    if ret_type and ret_type != "error" and ret_type != "":
        lines.append(f"    var want {ret_type}")
        lines.append(f"    // TODO: set want = expected value")

    # Call the method
    if param_names:
        params_str = ", ".join(f"<{p}>" for p in param_names)
        call = f"    got := receiver.{name}({params_str})"
    else:
        call = f"    got := receiver.{name}()"

    lines.append(f"    {call}")
    lines.append("")

    # Add assertion
    if ret_type == "error" or returns_error:
        lines.append("    if got != nil {")
        lines.append(f'        t.Errorf("{name}() error = %v, want nil", got)')
        lines.append("    }")
    elif ret_type and ret_type != "":
        lines.append("    if got != want {")
        lines.append(f'        t.Errorf("{name}() = %v, want %v", got, want)')
        lines.append("    }")
    else:
        lines.append("    // TODO: add assertions")

    lines.append("}")

    return "\n".join(lines)


def _detect_package_name(content: str) -> str:
    """Detect the package name from Go source content."""
    import re
    m = re.search(r"^package\s+(\w+)", content, re.MULTILINE)
    if m:
        return m.group(1)
    return "fixtures"


def write_test_files(
    repo_path: Path,
    output_dir: Optional[Path] = None,
) -> List[Path]:
    """Generate test files for all Go source files in a directory.

    Args:
        repo_path: Directory containing Go source files
        output_dir: Directory to write test files. If None, uses repo_path.

    Returns:
        List of paths to generated test files.
    """
    output_dir = output_dir or repo_path
    generated: List[Path] = []

    go_files = list(repo_path.rglob("*.go"))
    # Exclude test files and generated files
    go_files = [f for f in go_files if "_test.go" not in f.name and not f.name.endswith(".gen.go")]

    # Group functions by file
    file_funcs: Dict[Path, List[str]] = {}

    for f in go_files:
        content = f.read_text()
        funcs_list = _extract_go_function_bodies(content)
        funcs = _funcs_as_dict(funcs_list)
        top_funcs = [n for n, info in funcs.items() if not info["is_method"]]
        if top_funcs:
            file_funcs[f] = top_funcs

    for go_file, func_names in file_funcs.items():
        rel = go_file.relative_to(repo_path)
        test_file = output_dir / rel.parent / f"{rel.stem}_test.go"

        # If output_dir != repo_path, create parent dirs
        test_file.parent.mkdir(parents=True, exist_ok=True)

        content = generate_test_file(go_file, funcs_to_test=func_names)
        test_file.write_text(content)
        generated.append(test_file)

    return generated
