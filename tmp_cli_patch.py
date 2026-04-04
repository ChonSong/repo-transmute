import re

with open('src/repo_transmute/cli.py') as f:
    content = f.read()

old = '''            click.echo(f"=== Explain UID: {explain_uid} ===")
            click.echo(f"  Score: {explanation.get('score', 'N/A')}")
            if 'text' in explanation:
                click.echo(f"  Text:  {explanation['text'][:200]}")
            for k, v in explanation.items():
                if k not in ('score', 'text'):
                    click.echo(f"  {k}: {v}")'''

new = '''            if 'error' in explanation:
                click.echo(f"UID '{explain_uid}' not found in index.", err=True)
                return

            click.echo(f"=== UID: {explain_uid} ===")
            click.echo(f"  Name:     {explanation.get('name', 'N/A')}")
            click.echo(f"  Kind:     {explanation.get('kind', 'N/A')}")
            click.echo(f"  Repo:     {explanation.get('repo', 'N/A')}")
            click.echo(f"  Language: {explanation.get('language', 'N/A')}")
            click.echo(f"  Location: {explanation.get('file', 'N/A')}:{explanation.get('line', 'N/A')}")
            if explanation.get('signature'):
                click.echo(f"  Signature: {explanation['signature']}")
            score = explanation.get('score')
            if score is not None:
                click.echo(f"  Score:    {score:.4f}")
            if explanation.get('text'):
                click.echo(f"  Text:     {explanation['text'][:300]}")
            if explanation.get('docstring'):
                click.echo(f"  Docstring: {explanation['docstring'][:200]}")
            for k, v in explanation.items():
                if k not in ('id', 'name', 'kind', 'repo', 'language', 'file', 'line',
                             'signature', 'score', 'text', 'docstring'):
                    click.echo(f"  {k}: {v}")'''

if old in content:
    content = content.replace(old, new)
    with open('src/repo_transmute/cli.py', 'w') as f:
        f.write(content)
    print("Patched cli.py explain output successfully")
else:
    print("Pattern not found")
    idx = content.find('=== Explain UID:')
    if idx >= 0:
        print("Actual content:")
        print(repr(content[idx:idx+400]))