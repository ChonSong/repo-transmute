"""Migration runner - migrates hermes-workspace components to agent-os format."""

import json
import os
import sys
import re
import time
from pathlib import Path

# Load .env
env_path = Path('/opt/data/.env')
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, _, value = line.partition('=')
            os.environ[key.strip()] = value.strip()

sys.path.insert(0, '/opt/data/repo-transmute-v2/src')

from repo_transmute.v2.models import (
    ComponentDef, TargetStack, Framework, StyleApproach,
    ComponentType
)
from repo_transmute.v2.ingest.detector import detect_framework


def migrate_component_with_llm(comp, model='minimax/minimax-m2.7'):
    """Generate migrated code using OpenRouter API."""
    import httpx
    
    # Truncate very long components
    source_code = comp.full_source
    if len(source_code) > 3000:
        source_code = source_code[:3000] + '\n\n// ... (truncated for brevity)'
    
    prompt = f"""You are an expert React/TypeScript developer migrating components from a TanStack Start + Tailwind codebase to a standard React SPA with Vite.

SOURCE COMPONENT (from hermes-workspace):
Filename: {comp.file}
Type: {comp.component_type.value}

SOURCE CODE:
{source_code}

TARGET CONVENTIONS:
- Standard React SPA with Vite (no SSR, no TanStack Router)
- Use react-router-dom for routing
- Tailwind CSS for styling (keep existing Tailwind classes)
- Use lucide-react for icons (replace any icon library imports)
- Functional components with explicit TypeScript types
- Props defined as interfaces
- Import paths should use @/ alias
- No Electron-specific code
- Use standard fetch/axios for API calls
- Export as default export

IMPORT CONVERSION RULES:
- @tanstack imports -> react-router-dom or remove
- electron imports -> remove
- ~/ -> @/
- Keep Tailwind classes as-is

Generate ONLY the migrated component code in a TypeScript code block."""

    api_key = os.environ.get('OPENROUTER_API_KEY', '')
    
    try:
        response = httpx.post(
            'https://openrouter.ai/api/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://github.com/ChonSong/repo-transmute',
                'X-Title': 'repo-transmute-v2',
            },
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.1,
                'max_tokens': 4000,
            },
            timeout=120,
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('choices', [{}])[0].get('message', {}).get('content', '')
        else:
            print(f'API error {response.status_code}: {response.text[:100]}', file=sys.stderr)
            return ''
    except Exception as e:
        print(f'LLM failed: {e}', file=sys.stderr)
        return ''


def extract_code(text):
    """Extract code from markdown code blocks."""
    pattern = r'```(?:typescript|tsx|ts)?\s*\n(.*?)```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def main():
    source_dir = Path('/opt/data/hermes-workspace')
    output_dir = Path('/opt/data/repo-transmute-v2/data/migrated')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    framework, style = detect_framework(source_dir)
    
    key_dirs = [
        'src/screens/chat',
        'src/screens/dashboard',
        'src/screens/mcp',
        'src/screens/settings',
        'src/screens/agents',
        'src/components/ui',
    ]
    
    key_components = []
    for dir_path in key_dirs:
        full_path = source_dir / dir_path
        if full_path.exists():
            for tsx_file in full_path.rglob('*.tsx'):
                try:
                    content = tsx_file.read_text()
                    if len(content) < 200:
                        continue
                    if '.test.' in str(tsx_file):
                        continue
                    rel_path = str(tsx_file.relative_to(source_dir))
                    comp = ComponentDef(
                        name=tsx_file.stem,
                        file=rel_path,
                        line=1,
                        full_source=content,
                        framework=framework,
                        component_type=ComponentType.COMPONENT if 'components' in rel_path else ComponentType.PAGE,
                        css_approach=style,
                    )
                    key_components.append(comp)
                except Exception as e:
                    print(f'Failed: {tsx_file}: {e}')
    
    print(f'Found {len(key_components)} components to migrate')
    
    migrated = {}
    for i, comp in enumerate(key_components):
        print(f'[{i+1}/{len(key_components)}] Migrating {comp.name} ({comp.file})...')
        
        result = migrate_component_with_llm(comp)
        if result:
            code = extract_code(result)
            if len(code) > 50:
                output_file = output_dir / f'{comp.name}.tsx'
                output_file.write_text(code)
                migrated[comp.name] = {'source': comp.file, 'target': str(output_file), 'chars': len(code)}
                print(f'  -> Saved ({len(code)} chars)')
                time.sleep(2)
            else:
                print(f'  -> Too short, skipped')
        else:
            print(f'  -> FAILED')
            time.sleep(2)
    
    report = output_dir / 'migration_report.json'
    report.write_text(json.dumps({'total': len(key_components), 'migrated': len(migrated), 'components': migrated}, indent=2))
    print(f'Done! {len(migrated)}/{len(key_components)} migrated')


if __name__ == '__main__':
    main()
