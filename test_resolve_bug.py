"""Quick bug check for resolve_imports."""
import re

line = "import { User, Post } from './models';"

pattern = r"^(\s*import\s+(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+['\"])(\.\.[^'\"]+|\.[^'\"]+)(['\"];?.*)$"

js_match = re.match(pattern, line)
if js_match:
    prefix, import_path, suffix = js_match.group(1), js_match.group(2), js_match.group(3)
    print("prefix:", repr(prefix))
    print("import_path:", repr(import_path))
    print("suffix:", repr(suffix))
    
    # BUGGY: tries to find { User, Post } in prefix+"{" 
    symbol_match_buggy = re.search(r"import\s+\{([^}]+)\}", prefix + "{")
    print("\nBUGGY symbol_match (prefix+'{'):", symbol_match_buggy)
    
    # CORRECT: search in the full original line
    symbol_match_correct = re.search(r"import\s+\{([^}]+)\}", line)
    print("CORRECT symbol_match (line):", symbol_match_correct)
    if symbol_match_correct:
        symbols = [s.strip() for s in symbol_match_correct.group(1).split(",")]
        print("symbols:", symbols)
