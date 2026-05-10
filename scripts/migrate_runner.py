"""Migration runner - migrates hermes-workspace components to agent-os format.

Uses local Hermes Agent gateway (port 8642) for LLM calls - no external API credits needed.
"""

import json
import os
import sys
import re
import time
import subprocess
import tempfile
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


def migrate_component_with_llm(comp, model='MiniMax-M2.7'):
    """Generate migrated code using local Hermes Agent gateway."""
    
    # Truncate very long components
    source_code = comp.full_source
    if len(source_code) > 4000:
        source_code = source_code[:4000] + '\n\n// ... (truncated, full component available on request)'
    
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
- @hugeicons/react -> lucide-react
- @base-ui/react -> standalone React implementations
- Keep Tailwind classes as-is

Generate ONLY the migrated component code in a TypeScript code block. No explanations."""

    # Write prompt to temp file and use curl via SSH
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        payload = {
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.1,
            'max_tokens': 6000,
        }
        json.dump(payload, f)
        temp_file = f.name
    
    try:
        # SSH to host and call Hermes gateway
        cmd = f"ssh -i /opt/data/container_key -o StrictHostKeyChecking=no sean@localhost 'curl -sf http://127.0.0.1:8642/v1/chat/completions -H \"Content-Type: application/json\" -d @-' < {temp_file}"
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            return content
        else:
            print(f'Hermes error {result.returncode}: {result.stderr[:100]}', file=sys.stderr)
            return ''
    except Exception as e:
        print(f'LLM failed: {e}', file=sys.stderr)
        return ''
    finally:
        os.unlink(temp_file)


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
    
    # Prioritize key screens and UI components
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
            for tsx_file in sorted(full_path.rglob('*.tsx')):
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
    print(f'Using local Hermes gateway (no external API credits needed)')
    
    migrated = {}
    failed = []
    
    for i, comp in enumerate(key_components):
        print(f'[{i+1}/{len(key_components)}] Migrating {comp.name} ({comp.file})...')
        
        result = migrate_component_with_llm(comp)
        if result:
            code = extract_code(result)
            if len(code) > 50:
                output_file = output_dir / f'{comp.name}.tsx'
                output_file.write_text(code)
                migrated[comp.name] = {
                    'source': comp.file,
                    'target': str(output_file),
                    'chars': len(code),
                    'source_chars': len(comp.full_source),
                }
                print(f'  -> Saved ({len(code)} chars from {len(comp.full_source)} source)')
                time.sleep(2)
            else:
                print(f'  -> Too short ({len(code)} chars), skipped')
                failed.append(comp.name)
        else:
            print(f'  -> FAILED (no response)')
            failed.append(comp.name)
            time.sleep(2)
    
    # Save migration report
    report = output_dir / 'migration_report.json'
    report.write_text(json.dumps({
        'total': len(key_components),
        'migrated': len(migrated),
        'failed': len(failed),
        'components': migrated,
        'failed_list': failed,
    }, indent=2))
    
    print(f'\nMigration complete!')
    print(f'  Migrated: {len(migrated)}/{len(key_components)}')
    print(f'  Failed: {len(failed)}')
    print(f'Report saved to {report}')
    
    # Summary of migrated files
    if migrated:
        print(f'\nMigrated components:')
        for name, info in sorted(migrated.items()):
            print(f'  {name}: {info["source"]} -> {info["target"]} ({info["chars"]} chars)')


if __name__ == '__main__':
    main()
