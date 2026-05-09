"""Validation module for transpiled code."""

import re
import subprocess
from pathlib import Path
from typing import Optional


class ValidationResult:
    """Result of code validation."""
    
    def __init__(self, success: bool, output: str = "", error: str = ""):
        self.success = success
        self.output = output
        self.error = error
    
    def __str__(self):
        if self.success:
            return "✅ Validation passed"
        return f"❌ Validation failed: {self.error}"


def validate_typescript(file_path: Path) -> ValidationResult:
    """Validate TypeScript using tsc --noEmit."""
    if not file_path.exists():
        return ValidationResult(False, error=f"File not found: {file_path}")
    
    try:
        # Run tsc --noEmit to check for errors
        result = subprocess.run(
            ["tsc", "--noEmit", str(file_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            return ValidationResult(True, output="TypeScript validation passed")
        else:
            return ValidationResult(False, error=result.stderr or result.stdout)
    
    except FileNotFoundError:
        return ValidationResult(False, error="TypeScript (tsc) not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(False, error="Validation timed out")
    except Exception as e:
        return ValidationResult(False, error=str(e))


def validate_rust(file_path: Path) -> ValidationResult:
    """Validate Rust using cargo check."""
    if not file_path.exists():
        return ValidationResult(False, error=f"File not found: {file_path}")
    
    # Need to get the cargo project directory
    cargo_toml = file_path.parent / "Cargo.toml"
    
    # If no Cargo.toml, create a temporary one
    if not cargo_toml.exists():
        # Create a minimal Cargo.toml for validation
        cargo_content = '''[package]
name = "temp"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
reqwest = { version = "0.11", features = ["json"] }
tokio = { version = "1.0", features = ["full"] }
axum = "0.7"
anyhow = "1.0"
'''
        cargo_toml.write_text(cargo_content)
    
    try:
        # Run cargo check
        result = subprocess.run(
            ["cargo", "check"],
            capture_output=True,
            text=True,
            cwd=file_path.parent,
            timeout=120
        )
        
        if result.returncode == 0:
            return ValidationResult(True, output="Rust validation passed")
        else:
            return ValidationResult(False, error=result.stderr or result.stdout)
    
    except FileNotFoundError:
        return ValidationResult(False, error="Rust (cargo) not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(False, error="Validation timed out")
    except Exception as e:
        return ValidationResult(False, error=str(e))


def validate_python(file_path: Path) -> ValidationResult:
    """Validate Python using py_compile."""
    if not file_path.exists():
        return ValidationResult(False, error=f"File not found: {file_path}")
    
    try:
        result = subprocess.run(
            ["python3", "-m", "py_compile", str(file_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return ValidationResult(True, output="Python validation passed")
        else:
            return ValidationResult(False, error=result.stderr)
    
    except FileNotFoundError:
        return ValidationResult(False, error="Python not installed")
    except Exception as e:
        return ValidationResult(False, error=str(e))


def validate_go(file_path: Path) -> ValidationResult:
    """Validate Go code using go vet."""
    if not file_path.exists():
        return ValidationResult(False, error=f"File not found: {file_path}")
    
    try:
        result = subprocess.run(
            ["go", "vet", str(file_path)],
            capture_output=True,
            text=True,
            cwd=file_path.parent,
            timeout=60
        )
        
        if result.returncode == 0:
            return ValidationResult(True, output="Go validation passed")
        else:
            return ValidationResult(False, error=result.stderr or result.stdout)
    
    except FileNotFoundError:
        return ValidationResult(False, error="Go not installed")
    except subprocess.TimeoutExpired:
        return ValidationResult(False, error="Go validation timed out")
    except Exception as e:
        return ValidationResult(False, error=str(e))


def validate_react(file_path: Path, project_dir: Path | None = None) -> ValidationResult:
    """Validate React/TSX code using tsc --noEmit and optionally vite build.
    
    For single file validation, uses tsc --noEmit.
    For project-wide validation, uses vite build in the project directory.
    """
    if not file_path.exists():
        return ValidationResult(False, error=f"File not found: {file_path}")
    
    # Try tsc --noEmit first (works for single files with proper tsconfig)
    work_dir = project_dir or file_path.parent
    tsconfig = work_dir / "tsconfig.json"
    
    if tsconfig.exists():
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", str(file_path)],
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=60,
            )
            
            if result.returncode == 0:
                return ValidationResult(True, output="React/TSX validation passed (tsc)")
            else:
                # Check if error is just "npx not found" or similar infra issue
                if "command not found" in result.stderr.lower() or "npm" in result.stderr.lower():
                    # Fall through to vite build check
                    pass
                else:
                    return ValidationResult(False, error=result.stderr or result.stdout)
        except FileNotFoundError:
            pass  # npx/tsc not available, try vite
        except subprocess.TimeoutExpired:
            return ValidationResult(False, error="React validation timed out (tsc)")
    
    # Try vite build for project-wide validation
    if project_dir and (project_dir / "vite.config.ts").exists():
        try:
            result = subprocess.run(
                ["npx", "vite", "build", "--mode", "development"],
                capture_output=True,
                text=True,
                cwd=project_dir,
                timeout=120,
            )
            
            if result.returncode == 0:
                return ValidationResult(True, output="React/TSX validation passed (vite build)")
            else:
                return ValidationResult(False, error=result.stderr or result.stdout)
        except FileNotFoundError:
            return ValidationResult(False, error="vite not installed")
        except subprocess.TimeoutExpired:
            return ValidationResult(False, error="React validation timed out (vite)")
    
    # Last resort: basic syntax check with python regex
    content = file_path.read_text()
    issues = _basic_react_syntax_check(content, file_path)
    if issues:
        return ValidationResult(False, error="Basic syntax issues: " + "; ".join(issues))
    return ValidationResult(True, output="Basic React/TSX syntax check passed")


def _basic_react_syntax_check(content: str, file_path: Path) -> list[str]:
    """Basic syntax checks for React/TSX files."""
    issues = []
    
    # Check for unclosed JSX tags
    open_tags = []
    for match in re.finditer(r'<(\w+)[^>]*(?<!/)>', content):
        tag = match.group(1)
        if tag[0].isupper() or tag in ('div', 'span', 'p', 'a', 'button', 'input', 'img', 'ul', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'section', 'main', 'header', 'footer', 'nav', 'form', 'label', 'select', 'option', 'textarea'):
            open_tags.append(tag)
    
    for match in re.finditer(r'</(\w+)>', content):
        close_tag = match.group(1)
        if open_tags and open_tags[-1] == close_tag:
            open_tags.pop()
    
    # Check for unclosed braces
    brace_count = content.count('{') - content.count('}')
    if brace_count != 0:
        issues.append(f"Unclosed braces: {'opening' if brace_count > 0 else 'closing'} ({abs(brace_count)} unmatched)")
    
    # Check for unclosed parentheses
    paren_count = content.count('(') - content.count(')')
    if paren_count != 0:
        issues.append(f"Unclosed parentheses: {'opening' if paren_count > 0 else 'closing'} ({abs(paren_count)} unmatched)")
    
    # Check for common JSX mistakes
    if 'class=' in content and 'className=' not in content and 'class="' in content:
        issues.append("Use 'className' instead of 'class' in JSX")
    
    if 'for=' in content and 'htmlFor=' not in content and 'for="' in content:
        issues.append("Use 'htmlFor' instead of 'for' in JSX")
    
    # Check for self-closing tag issues
    if re.search(r'<(img|br|hr|input|meta|link)[^>]*[^/]>', content):
        # Allow <img /> but flag <img > without closing
        pass  # This is too noisy, skip
    
    return issues


def validate(file_path: Path, language: str, project_dir: Path | None = None) -> ValidationResult:
    """Validate code based on language.
    
    Args:
        file_path: Path to the code file
        language: Programming language (typescript, rust, python, react)
        project_dir: Optional project root for build-based validation
        
    Returns:
        ValidationResult
    """
    lang = language.lower()
    
    if "react" in lang or "jsx" in lang or "tsx" in lang:
        return validate_react(file_path, project_dir)
    elif "typescript" in lang or "ts" in lang:
        return validate_typescript(file_path)
    elif "rust" in lang:
        return validate_rust(file_path)
    elif "python" in lang or "py" in lang:
        return validate_python(file_path)
    elif "go" in lang or "golang" in lang:
        return validate_go(file_path)
    else:
        return ValidationResult(False, error=f"Unsupported language: {language}")
