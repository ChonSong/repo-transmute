"""LLM-based transpiler using MiniMax or z.ai GLM models."""

import os
import re
from pathlib import Path
from typing import Optional

import yaml
import requests

from repo_transmute.transpiler.prompts import build_transpile_prompt


# Default to MiniMax M2.7
DEFAULT_MODEL = "MiniMax-M2.7"


class Transpiler:
    """Transpile blueprints to target languages via LLM."""
    
    def __init__(self, model: str = DEFAULT_MODEL):
        """Initialize transpiler.
        
        Args:
            model: LLM model to use (default: MiniMax-M2.7)
        """
        self.model = model
        
    def transpile(
        self,
        blueprint_path: Path,
        target_lang: str = "typescript",
        output_dir: Optional[Path] = None
    ) -> str:
        """Transpile a blueprint to target language."""
        # Load blueprint
        with open(blueprint_path) as f:
            blueprint = yaml.safe_load(f)
        
        # Build prompt
        source_lang = blueprint.get("source", {}).get("language", "python")
        prompt = build_transpile_prompt(blueprint, source_lang, target_lang)
        
        # Call LLM
        if "MiniMax" in self.model:
            result = self._call_minimax(prompt)
        else:
            result = self._call_zai(prompt)
        
        # Save if output_dir provided
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
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 8192,
            "temperature": 0.3
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=180)
        response.raise_for_status()
        
        result = response.json()
        
        # Get the message content
        message = result["choices"][0]["message"]
        
        # MiniMax puts response in content field (may include thinking)
        raw_content = message.get("content", "")
        
        # Clean up thinking tags and extract actual code
        content = self._clean_thinking(raw_content)
        
        if not content:
            raise ValueError(f"Empty response from MiniMax: {result}")
        
        return content
    
    def _clean_thinking(self, text: str) -> str:
        """Remove thinking tags and extract actual response."""
        # Remove thinking blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        text = re.sub(r"<think>.*", "", text)
        
        # Also check for other common patterns
        text = re.sub(r"Here'?s?\s+(the\s+)?(requested|requested|generated)\s+.*?:\s*\n", "", text, flags=re.IGNORECASE)
        
        # Strip leading/trailing whitespace
        text = text.strip()
        
        # If still starts with thinking-like content, try to find code blocks
        if text.startswith("We have") or text.startswith("The user") or text.startswith("Below") or text.startswith("Here") or "#" not in text[:50]:
            # Find the first code block
            match = re.search(r"```[\w]*\n(.*?)```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()
        
        return text
    
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
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 8192,
            "temperature": 0.3
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=180)
        response.raise_for_status()
        
        result = response.json()
        
        # z.ai returns content normally
        message = result["choices"][0]["message"]
        content = message.get("content", "")
        
        # Clean up any markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[-1].strip() == "```":
                content = "\n".join(lines[1:-1])
            else:
                content = "\n".join(lines[1:])
        
        return content
    
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
