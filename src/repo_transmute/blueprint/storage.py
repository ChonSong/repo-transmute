"""Save and load blueprints."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from repo_transmute.blueprint.extractor import Blueprint, Function, DataStructure


def save_blueprint(
    blueprint: Blueprint,
    output_dir: Path,
    version: Optional[str] = None
) -> Path:
    """Save blueprint to YAML file.
    
    Args:
        blueprint: Extracted blueprint
        output_dir: Where to save
        version: Optional version string
        
    Returns:
        Path to saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    data = {
        "version": version or "1.0",
        "generated": datetime.utcnow().isoformat() + "Z",
        "source": {
            "repo": blueprint.repo,
            "language": blueprint.language
        },
        "blueprint": {
            "functions": [
                {
                    "name": f.name,
                    "signature": f.signature,
                    "file": f.file,
                    "line": f.line,
                    "async": f.async_flag,
                    "body": f.body if hasattr(f, 'body') else "",
                    "docstring": f.docstring if hasattr(f, 'docstring') else None,
                    "decorators": f.decorators if hasattr(f, 'decorators') else []
                }
                for f in blueprint.functions
            ],
            "data_structures": [
                {
                    "name": ds.name,
                    "type": ds.type,
                    "file": ds.file,
                    "line": ds.line,
                    "fields": ds.fields
                }
                for ds in blueprint.data_structures
            ]
        }
    }
    
    # Create safe filename
    safe_name = blueprint.repo.replace("/", "__")
    filename = f"{safe_name}.yaml"
    filepath = output_dir / filename
    
    with open(filepath, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    return filepath


def load_blueprint(path: Path) -> Blueprint:
    """Load blueprint from YAML."""
    with open(path) as f:
        data = yaml.safe_load(f)
    
    functions = [
        Function(
            name=f["name"],
            signature=f["signature"],
            file=f["file"],
            line=f["line"],
            async_flag=f.get("async", False)
        )
        for f in data.get("blueprint", {}).get("functions", [])
    ]
    
    data_structures = [
        DataStructure(
            name=ds["name"],
            type=ds["type"],
            file=ds["file"],
            line=ds["line"],
            fields=ds.get("fields", [])
        )
        for ds in data.get("blueprint", {}).get("data_structures", [])
    ]
    
    return Blueprint(
        repo=data["source"]["repo"],
        language=data["source"]["language"],
        functions=functions,
        data_structures=data_structures
    )
