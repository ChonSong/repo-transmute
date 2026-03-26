"""LLM-based transpiler using MiniMax or z.ai GLM models."""

import os
import re
from pathlib import Path
from typing import Optional

import yaml
import requests

from repo_transmute.transpiler.prompts import build_transpile_prompt


DEFAULT_MODEL = "MiniMax-M2.7"

KNOWN_BUILTINS = {
    "console", "Math", "Date", "JSON", "Array", "Object", "String", "Number",
    "Boolean", "RegExp", "Map", "Set", "WeakMap", "WeakSet", "Promise", "Error",
    "TypeError", "RangeError", "SyntaxError", "ReferenceError", "fetch", "URL",
    "URLSearchParams", "AbortController", "AbortSignal", "ArrayBuffer", "DataView",
    "Float32Array", "Float64Array", "Int8Array", "Int16Array", "Int32Array",
    "Uint8Array", "Uint16Array", "Uint32Array", "Uint8ClampedArray",
    "Symbol", "BigInt", "Proxy", "Reflect", "WebSocket", "Event", "EventTarget",
    "BroadcastChannel", "MessageChannel", "MessagePort", "Worker", "Crypto",
    "crypto", "navigator", "window", "document", "location", "history", "localStorage",
    "sessionStorage", "indexedDB", "performance", "requestAnimationFrame",
    "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "process", "Buffer", "setImmediate",
    "global", "globalThis", "Infinity", "NaN", "undefined", "parseInt", "parseFloat",
    "isNaN", "isFinite", "encodeURI", "decodeURI", "encodeURIComponent",
    "decodeURIComponent", "eval", "Function",
}

KNOWN_NPM_PACKAGES = {
    "react", "react-dom", "next", "axios", "swr", "zustand", "jotai",
    "trpc", "zod", "yup", "date-fns", "lodash", "uuid", "clsx",
    "class-variance-authority", "tailwind-merge", "cva",
    "vitest", "jest", "@testing-library/react", "@testing-library/dom",
    "express", "fastify", "koa", "hono", "ws", "socket.io",
    "dotenv", "yargs", "commander", "chalk", "ora", "prompts",
    "openai", "anthropic", "@google/generative-ai",
    "langchain", "llamaindex", "mysql", "pg", "better-sqlite3", "prisma",
    "typeorm", "drizzle-orm",
    "asyncio", "aiohttp", "fastapi", "uvicorn", "pydantic",
    "numpy", "pandas", "torch", "tensorflow", "jax",
    "async",  # async npm package
}


class Transpiler:
    """Transpile blueprints to target languages via LLM."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model

    def transpile(
        self,
        blueprint_path: Path,
        target_lang: str = "typescript",
        output_dir: Optional[Path] = None
    ) -> str:
        """Transpile a blueprint to target language."""
        with open(blueprint_path) as f:
            blueprint = yaml.safe_load(f)

        source_lang = blueprint.get("source", {}).get("language", "python")
        prompt = build_transpile_prompt(blueprint, source_lang, target_lang)

        if "MiniMax" in self.model:
            result = self._call_minimax(prompt)
        else:
            result = self._call_zai(prompt)

        result = self._post_clean(result, target_lang)

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            source_repo = blueprint.get("source", {}).get("repo", "unknown")
            ext = "ts" if target_lang == "typescript" else target_lang[:2]
            output_file = output_dir / f"{source_repo.replace('/', '__')}_{target_lang}.{ext}"
            output_file.write_text(result)

        return result

    def _call_minimax(self, prompt: str) -> str:
        """Call MiniMax API."""
        api_key = os.environ.get("MINIMAX_API_KEY")
        if not api_key:
            raise ValueError("No API key found. Set MINIMAX_API_KEY")

        url = "https://api.minimax.io/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8192,
            "temperature": 0.1
        }

        response = requests.post(url, headers=headers, json=data, timeout=180)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

    def _call_zai(self, prompt: str) -> str:
        """Call z.ai API (GLM models)."""
        api_key = os.environ.get("ZAI_API_KEY")
        if not api_key:
            raise ValueError("No API key found. Set ZAI_API_KEY")

        url = "https://api.z.ai/api/coding/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 8192,
            "temperature": 0.1
        }

        response = requests.post(url, headers=headers, json=data, timeout=180)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        if content.startswith("```"):
            lines = content.split("\n")
            if lines[-1].strip() == "```":
                content = "\n".join(lines[1:-1])
            else:
                content = "\n".join(lines[1:])
        return content

    def _post_clean(self, text: str, target_lang: str) -> str:
        """Clean LLM output: strip thinking tags, markdown fences, invalid imports, docstring cruft."""
        original = text

        # Step 1: Strip markdown code fences
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1])
            elif len(lines) > 1:
                text = "\n".join(lines[1:])

        # Step 2: Strip thinking tags
        text = re.sub(r"<thought>[\s\S]*?</thought>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[/THOUGHT\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<thinking>[\s\S]*?</thinking>", "", text, flags=re.IGNORECASE)

        # Step 3: Strip leading narrative cruft before first code
        lines = text.split("\n")
        STOP_KEYWORDS = [
            "export", "import", "function", "const", "let", "var",
            "class", "interface", "type", "enum", "namespace",
            "//", "/*", "///", "// filename:", "---FILE_SEPARATOR---",
        ]
        while lines:
            first = lines[0].strip()
            if not first:
                lines.pop(0)
                continue
            if any(first.startswith(kw) for kw in STOP_KEYWORDS):
                break
            if re.match(r"^//\s*filename:", first):
                break
            lines.pop(0)
        text = "\n".join(lines)

        # Step 4: Strip embedded Python docstrings and narrative cruft
        text = re.sub(r'"""[\s\S]*?"""', "", text)
        text = re.sub(r"'''[\s\S]*?'''", "", text)
        text = re.sub(r"(?m)^#.*CPython.*\n", "", text)
        text = re.sub(r"(?m)^#.*type:\s*ignore.*\n", "", text)
        text = re.sub(r'(?m)^\"\"\".*?\"\"\"\s*\n', "", text)
        text = re.sub(r"(?m)^'''.*'''\s*\n", "", text)

        # Step 5: Fix invented imports (JS/TS targets only)
        if target_lang in ("typescript", "javascript", "ts", "js", "tsx"):
            text = self._fix_invalid_imports(text)

        # Step 6: Remove Python-only syntax lines from TS output
        if target_lang in ("typescript", "ts", "tsx"):
            lines = text.split("\n")
            fixed_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    fixed_lines.append(line)
                    continue
                # Skip Python-only constructs
                if re.match(r"^__(?:all|debug|doc)__\s*=", stripped): continue
                if re.match(r"^from\s+\S+\s+import", stripped): continue
                if stripped.startswith("import ") and not stripped.startswith('import "'):
                    # Python bare import (import x, not import "x")
                    # JS imports always have quotes: import "foo"
                    continue
                if stripped == "```":
                    continue
                fixed_lines.append(line)
            text = "\n".join(fixed_lines)

        # Step 7: Final trim
        text = text.strip()

        # Step 8: Sanity check
        if not text:
            raise ValueError(f"Output was emptied by cleaning. Original had {len(original)} chars.")

        code_indicators = [
            "function", "class", "interface", "type ", "const ", "let ", "var ",
            "export", "import", "return", "=>", "async", "await",
            "enum ", "namespace ", "///",
        ]
        has_code = any(tok in text for tok in code_indicators)
        is_meaningful_length = len(text) >= 20
        if not has_code and not is_meaningful_length:
            raise ValueError(
                f"Output appears to be gibberish (no code tokens, {len(text)} chars). "
                f"Original had {len(original)} chars."
            )

        return text

    def _fix_invalid_imports(self, text: str) -> str:
        """Remove Python-only import statements; validate JS import module names.

        Python imports have no quotes around module names:
          import os, sys         (bare, no quotes)
          from os import path    (from, no quotes)

        JS imports always have quoted module paths:
          import "react"                       (side-effect)
          import React from "react"             (default)
          import { useState } from "react"       (named)
          import * as foo from "lodash"         (namespace)
          import React, { useState } from "react" (default + named)

        Any line with an unquoted 'import X' (no quotes at all after 'import')
        is treated as Python and removed. JS imports always have quotes.
        """
        result_lines = []
        for raw_line in text.split("\n"):
            stripped = raw_line.strip()

            # --- Step 1: Python from...import (always remove) ---
            #   from os import path
            #   from .utils import func
            if stripped.startswith("from ") and " import " in stripped:
                result_lines.append(f"// ⚠️ Removed Python import: {stripped[:60]}")
                continue

            # --- Step 2: Python bare import (always remove) ---
            #   import os
            #   import sys, os
            #   import foo as bar
            # JS bare imports always have a quoted string, e.g. import "foo"
            # So "import " followed by a word (no quote) = Python
            if stripped.startswith("import "):
                # Check if this is actually a JS import with a quoted module name
                # JS: import "react"  OR  import React from "react"
                is_js = (
                    stripped.startswith('import "')          # import "module"
                    or re.search(r'^import\s+\w+\s+from\s+"', stripped)  # import X from "Y"
                    or re.search(r'^import\s+\*\s+as\s+\w+\s+from\s+"', stripped)  # import * as X from "Y"
                    or re.search(r'^import\s+\{[^}]+\}\s+from\s+"', stripped)  # import { X } from "Y"
                    or re.search(r'^import\s+\w+\s*,\s*\{', stripped)  # import X, { Y } from "Z"
                )
                if not is_js:
                    result_lines.append(f"// ⚠️ Removed Python import: {stripped[:60]}")
                    continue

            # --- Step 3: JS import — check if module name is valid ---
            js_match = re.match(
                r'^import\s+(?:(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)'
                r'(?:\s*,\s*(?:\{[^}]*\}|\*\s+as\s+\w+|\w+))*'
                r'\s+from\s+)?["\']([^"\']+)["\']',
                stripped
            )
            if js_match:
                module_name = js_match.group(1)
                if self._is_invalid_import(module_name):
                    result_lines.append(f"// ⚠️ Removed invalid import: {module_name}")
                    continue

            result_lines.append(raw_line)

        return "\n".join(result_lines)

    def _is_invalid_import(self, module_name: str) -> bool:
        """Check if a JS/TS import module name is definitely invalid."""
        # Strip scoped prefix: @scope/package -> package
        if module_name.startswith("@"):
            module_name = "/".join(module_name.split("/")[1:]) if "/" in module_name else module_name
        # Strip path suffix: lodash/map -> lodash
        module_name = module_name.split("/")[0]
        if not module_name:
            return True

        if module_name.lower() in KNOWN_BUILTINS:
            return False
        if module_name.lower() in KNOWN_NPM_PACKAGES:
            return False

        # Definitely invalid: Python stdlib and fake packages
        INVALID = {
            "json",  # JSON is a global, not a module
            "regex", "re",  # RegExp is built-in
            "system", "sys", "os", "builtins",  # Python stdlib
            "functools", "itertools", "collections", "dataclasses",
            "typing", "types", "inspect", "ast", "io", "contextlib",
        }
        if module_name.lower() in INVALID:
            return True

        return False

    def transpile_string(
        self,
        blueprint_yaml: str,
        target_lang: str = "typescript"
    ) -> str:
        """Transpile from YAML string."""
        import io
        blueprint = yaml.safe_load(io.StringIO(blueprint_yaml))
        prompt = build_transpile_prompt(blueprint, "python", target_lang)
        if "MiniMax" in self.model:
            return self._call_minimax(prompt)
        return self._call_zai(prompt)


def transpile_with_llm(
    blueprint_path: Path,
    target_lang: str = "typescript",
    output_dir: Optional[Path] = None,
    model: str = DEFAULT_MODEL
) -> str:
    """Convenience function for transpilation."""
    transpiler = Transpiler(model=model)
    return transpiler.transpile(blueprint_path, target_lang, output_dir)
