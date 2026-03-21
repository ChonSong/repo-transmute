"""Extract interfaces, functions, classes from source code."""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set


@dataclass
class Import:
    """Represents an imported module or symbol."""
    module: str
    names: List[str]  # List of imported names (or ['*'] for wildcard)
    alias: Optional[str] = None  # 'as' alias if present


@dataclass
class Function:
    name: str
    signature: str
    file: str
    line: int
    end_line: int = 0  # Added: end line of function
    docstring: Optional[str] = None
    async_flag: bool = False
    decorators: List[str] = field(default_factory=list)  # Added: decorators
    body: str = ""  # Added: full function body code


@dataclass
class DataStructure:
    name: str
    type: str  # class, struct, enum
    file: str
    line: int
    end_line: int = 0  # Added: end line of class
    fields: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    methods: List[Function] = field(default_factory=list)  # Added: class methods


@dataclass
class Blueprint:
    repo: str
    language: str
    functions: List[Function] = field(default_factory=list)
    data_structures: List[DataStructure] = field(default_factory=list)
    imports: List[Import] = field(default_factory=list)  # Added: file imports


def _get_docstring(node: ast.AST) -> Optional[str]:
    """Extract docstring from an AST node."""
    docstring = ast.get_docstring(node)
    if docstring:
        return docstring.strip()
    return None


def _get_decorators(node: ast.FunctionDef) -> List[str]:
    """Extract decorator names from a function."""
    decorators = []
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name):
            decorators.append(decorator.id)
        elif isinstance(decorator, ast.Attribute):
            # Handle @staticmethod.foo() style
            decorators.append(f"{decorator.value.id}.{decorator.attr}")
        elif isinstance(decorator, ast.Call):
            # Handle @decorator() calls
            if isinstance(decorator.func, ast.Name):
                decorators.append(decorator.func.id)
            elif isinstance(decorator.func, ast.Attribute):
                decorators.append(f"{decorator.func.value.id}.{decorator.func.attr}")
    return decorators


def _extract_imports(content: str) -> List[Import]:
    """Extract all imports from Python source."""
    imports = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(Import(
                        module=alias.name,
                        names=[alias.asname or alias.name]
                    ))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.asname or alias.name for alias in node.names]
                imports.append(Import(
                    module=module,
                    names=names
                ))
    except SyntaxError:
        pass
    return imports


def _get_function_body(source_lines: list, start_line: int, end_line: int) -> str:
    """Extract the full body of a function as source code."""
    # Convert to 0-indexed for list access
    start_idx = start_line - 1
    end_idx = end_line
    
    if start_idx < 0:
        start_idx = 0
    if end_idx > len(source_lines):
        end_idx = len(source_lines)
    
    body_lines = source_lines[start_idx:end_idx]
    return '\n'.join(body_lines)


def extract_from_python(file_path: Path) -> List[Function]:
    """Extract functions and classes from Python file using AST."""
    content = file_path.read_text()
    source_lines = content.split('\n')
    functions = []
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Fall back to regex-based extraction for syntax errors
        return _extract_functions_regex(file_path, source_lines)
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Get line numbers
            start_line = node.lineno
            end_line = node.end_lineno or start_line
            
            # Build signature
            args = node.args
            params = []
            defaults_offset = len(args.args) - len(args.defaults)
            
            for i, arg in enumerate(args.args):
                default_idx = i - defaults_offset
                if default_idx >= 0 and default_idx < len(args.defaults):
                    # Has default value
                    default = args.defaults[default_idx]
                    params.append(f"{arg.arg}=<default>")
                else:
                    params.append(arg.arg)
            
            # Handle *args and **kwargs
            if args.vararg:
                params.append(f"*{args.vararg.arg}")
            if args.kwarg:
                params.append(f"**{args.kwarg.arg}")
            
            # Handle positional-only args
            if args.posonlyargs:
                posonly = [a.arg for a in args.posonlyargs]
                params = posonly + ['/'] + params
            
            # Return type
            return_type = ""
            if node.returns:
                return_type = f" -> {ast.unparse(node.returns)}"
            
            # Get decorators
            decorators = _get_decorators(node)
            
            # Get docstring
            docstring = _get_docstring(node)
            
            # Get body
            body = _get_function_body(source_lines, start_line, end_line)
            
            functions.append(Function(
                name=node.name,
                signature=f"({', '.join(params)}){return_type}",
                file=str(file_path),
                line=start_line,
                end_line=end_line,
                docstring=docstring,
                async_flag=isinstance(node, ast.AsyncFunctionDef),
                decorators=decorators,
                body=body
            ))
    
    return functions


def _extract_functions_regex(file_path: Path, source_lines: list) -> List[Function]:
    """Fallback regex-based extraction for files with syntax errors."""
    functions = []
    func_pattern = r'^(async\s+)?def\s+(\w+)\s*\((.*?)\)\s*(?:->\s*(\S+))?:'
    
    for i, line in enumerate(source_lines, 1):
        stripped = line.strip()
        
        match = re.match(func_pattern, stripped)
        if match:
            async_part, name, params, ret = match.groups()
            return_type = f" -> {ret}" if ret else ""
            functions.append(Function(
                name=name,
                signature=f"({params}){return_type}",
                file=str(file_path),
                line=i,
                async_flag=async_part is not None
            ))
    
    return functions


def extract_classes_from_python(file_path: Path) -> List[DataStructure]:
    """Extract classes from Python file using AST."""
    content = file_path.read_text()
    source_lines = content.split('\n')
    classes = []
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _extract_classes_regex(file_path)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Get bases
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(ast.unparse(base))
            
            start_line = node.lineno
            end_line = node.end_lineno or start_line
            
            # Extract methods
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Get method signature
                    args = item.args
                    params = []
                    defaults_offset = len(args.args) - len(args.defaults)
                    
                    # Skip 'self' or 'cls' for params
                    param_args = args.args
                    if param_args and param_args[0].arg in ('self', 'cls'):
                        param_args = param_args[1:]
                    
                    for i, arg in enumerate(param_args):
                        default_idx = i - (defaults_offset - 1)  # Adjust for self/cls
                        if default_idx >= 0 and default_idx < len(args.defaults):
                            params.append(f"{arg.arg}=<default>")
                        else:
                            params.append(arg.arg)
                    
                    if args.vararg:
                        params.append(f"*{args.vararg.arg}")
                    if args.kwarg:
                        params.append(f"**{args.kwarg.arg}")
                    
                    return_type = ""
                    if item.returns:
                        return_type = f" -> {ast.unparse(item.returns)}"
                    
                    decorators = _get_decorators(item)
                    docstring = _get_docstring(item)
                    body = _get_function_body(source_lines, item.lineno, item.end_lineno or item.lineno)
                    
                    methods.append(Function(
                        name=item.name,
                        signature=f"({', '.join(params)}){return_type}",
                        file=str(file_path),
                        line=item.lineno,
                        end_line=item.end_lineno or item.lineno,
                        docstring=docstring,
                        async_flag=isinstance(item, ast.AsyncFunctionDef),
                        decorators=decorators,
                        body=body
                    ))
            
            # Get docstring
            docstring = _get_docstring(node)
            
            classes.append(DataStructure(
                name=node.name,
                type="class",
                file=str(file_path),
                line=start_line,
                end_line=end_line,
                fields=bases,
                docstring=docstring,
                methods=methods
            ))
    
    return classes


def _extract_classes_regex(file_path: Path) -> List[DataStructure]:
    """Fallback regex-based class extraction."""
    content = file_path.read_text()
    classes = []
    class_pattern = r'^class\s+(\w+)(?:\((.*?)\))?\:'
    
    for i, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        match = re.match(class_pattern, stripped)
        if match:
            name, bases = match.groups()
            classes.append(DataStructure(
                name=name,
                type="class",
                file=str(file_path),
                line=i,
                fields=bases.split(",") if bases else []
            ))
    
    return classes


def extract_from_javascript(file_path: Path) -> List[Function]:
    """Extract functions from JavaScript/TypeScript."""
    content = file_path.read_text()
    functions = []
    
    # More comprehensive patterns for JS/ES6
    patterns = [
        # function declarations
        (r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[\(\=]', False),
        # arrow functions: const name = (params) =>
        (r'^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(?(.*?)\)?\s*=>', True),
        # arrow functions: const name = async (params) =>
        (r'^(?:export\s+)?const\s+(\w+)\s*=\s*async\s*\(?(.*?)\)?\s*=>', True),
        # let/var name = (params) =>
        (r'^(?:export\s+)?(?:let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(?(.*?)\)?\s*=>', True),
        # export default function
        (r'^(?:export\s+)?export\s+default\s+(?:async\s+)?function\s+(?:\w+)?\s*\(?(.*?)\)?', False),
        # export default arrow: export default (params) =>
        (r'^(?:export\s+)?export\s+default\s+(?:async\s+)?\(?(.*?)\)?\s*=>', False),
        # method in object: methodName(params) {
        (r'^(\w+)\s*\(?(.*?)\)?\s*\{', False),
        # class methods: methodName() {
        (r'^\s*(?:async\s+)?(\w+)\s*\(?(.*?)\)?\s*(?:\{|:)', False),
    ]
    
    for i, line in enumerate(content.split("\n"), 1):
        # Skip comments and empty lines
        stripped = line.strip()
        if not stripped or stripped.startswith('//') or stripped.startswith('/*') or stripped.startswith('*'):
            continue
            
        for pattern, _ in patterns:
            match = re.match(pattern, stripped)
            if match:
                name = match.group(1)
                params = match.group(2) if match.lastindex >= 2 else ""
                
                # Skip if name looks like a keyword or non-function
                if name in ('if', 'else', 'for', 'while', 'switch', 'try', 'catch', 'return', 'import', 'export', 'from', 'const', 'let', 'var', 'class', 'function', 'async'):
                    continue
                    
                # Clean up params
                params = params.strip() if params else ""
                
                functions.append(Function(
                    name=name,
                    signature=f"({params})",
                    file=str(file_path),
                    line=i,
                    async_flag="async" in stripped
                ))
                break
    
    return functions


def extract_from_typescript(file_path: Path) -> List[Function]:
    """Extract functions from TypeScript (similar to JS but with type annotations)."""
    return extract_from_javascript(file_path)


def extract_all(repo_path: Path, language: str) -> Blueprint:
    """Extract all structures from repo."""
    from repo_transmute.ingestion.walker import walk_source_files
    
    functions = []
    data_structures = []
    all_imports = []
    
    ext_map = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
    }
    
    ext = ext_map.get(language, ".py")
    
    extractors = {
        "python": (extract_from_python, extract_classes_from_python),
        "javascript": (extract_from_javascript, None),
        "typescript": (extract_from_typescript, None),
    }
    
    func_extractor, class_extractor = extractors.get(language, (extract_from_python, None))
    
    for file_path in walk_source_files(repo_path, extensions={ext}):
        try:
            # Extract imports for Python files
            if language == "python":
                content = file_path.read_text()
                file_imports = _extract_imports(content)
                all_imports.extend(file_imports)
            
            functions.extend(func_extractor(file_path))
            if class_extractor and language == "python":
                data_structures.extend(class_extractor(file_path))
        except Exception as e:
            # Skip files that can't be parsed
            continue
    
    return Blueprint(
        repo=str(repo_path.name),
        language=language,
        functions=functions,
        data_structures=data_structures,
        imports=all_imports
    )
