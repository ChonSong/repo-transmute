#!/usr/bin/env python3
"""Test Hermes gateway migration call."""

import json
import subprocess
import tempfile
import os

# Read a small component
comp_file = '/opt/data/hermes-workspace/src/components/ui/switch.tsx'
with open(comp_file) as f:
    source = f.read()

prompt = f'''Migrate this component to standard React SPA with Vite conventions.
- Use lucide-react for icons
- Tailwind CSS
- Export as default
- TypeScript interfaces for props

SOURCE:
{source[:1000]}

Generate ONLY the migrated code in a TypeScript code block.'''

# Write to temp file
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    payload = {
        'model': 'MiniMax-M2.7',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens': 4000,
    }
    json.dump(payload, f)
    temp_file = f.name

cmd = f"ssh -i /opt/data/container_key -o StrictHostKeyChecking=no sean@localhost 'curl -sf http://127.0.0.1:8642/v1/chat/completions -H \"Content-Type: application/json\" -d @-' < {temp_file}"
result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
print(f'Return code: {result.returncode}')
print(f'Stdout length: {len(result.stdout)}')
if result.returncode == 0:
    data = json.loads(result.stdout)
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    print(f'Content length: {len(content)}')
    print(f'Content preview: {content[:300]}')
else:
    print(f'Stderr: {result.stderr[:300]}')

os.unlink(temp_file)
