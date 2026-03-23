"""Validation module for transpiled code."""

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


def validate(file_path: Path, language: str) -> ValidationResult:
    """Validate code based on language.
    
    Args:
        file_path: Path to the code file
        language: Programming language (typescript, rust, python)
        
    Returns:
        ValidationResult
    """
    lang = language.lower()
    
    if "typescript" in lang or "ts" in lang:
        return validate_typescript(file_path)
    elif "rust" in lang:
        return validate_rust(file_path)
    elif "python" in lang or "py" in lang:
        return validate_python(file_path)
    else:
        return ValidationResult(False, error=f"Unsupported language: {language}")
