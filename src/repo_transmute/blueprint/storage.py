"""Save and load blueprints."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from repo_transmute.blueprint.extractor import Blueprint, Function, DataStructure


def save_blueprint(
    blueprint: Blueprint,
    output_dir: Path,
    version: Optional[str] = None,
    last_modified: Optional[str] = None,
) -> Path:
    """Save blueprint to YAML file.

    Args:
        blueprint: Extracted blueprint
        output_dir: Where to save
        version: Optional version string
        last_modified: ISO-8601 timestamp of the last git commit
                      (used for deduplication — skip re-indexing if unchanged)

    Returns:
        Path to saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "version": version or "1.0",
        "generated": datetime.utcnow().isoformat() + "Z",
        "last_modified": last_modified,  # git commit time or None
        "source": {
            "repo": blueprint.repo,
            "language": blueprint.language,
        },
        "blueprint": {
            "functions": [
                {
                    "name": f.name,
                    "signature": f.signature,
                    "file": f.file,
                    "line": f.line,
                    "async": f.async_flag,
                    "body": f.body if hasattr(f, "body") else "",
                    "docstring": f.docstring if hasattr(f, "docstring") else None,
                    "decorators": f.decorators if hasattr(f, "decorators") else [],
                }
                for f in blueprint.functions
            ],
            "data_structures": [
                {
                    "name": ds.name,
                    "type": ds.type,
                    "file": ds.file,
                    "line": ds.line,
                    "fields": ds.fields,
                    "docstring": ds.docstring if hasattr(ds, "docstring") else None,
                    "methods": [
                        {
                            "name": m.name,
                            "signature": m.signature,
                            "file": m.file,
                            "line": m.line,
                        }
                        for m in ds.methods
                    ] if hasattr(ds, "methods") else [],
                }
                for ds in blueprint.data_structures
            ],
        },
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
            async_flag=f.get("async", False),
            body=f.get("body", ""),
            docstring=f.get("docstring"),
            decorators=f.get("decorators", []),
        )
        for f in data.get("blueprint", {}).get("functions", [])
    ]

    data_structures = [
        DataStructure(
            name=ds["name"],
            type=ds["type"],
            file=ds["file"],
            line=ds["line"],
            fields=ds.get("fields", []),
            docstring=ds.get("docstring"),
            methods=[
                Function(
                    name=m["name"],
                    signature=m["signature"],
                    file=m["file"],
                    line=m["line"],
                )
                for m in ds.get("methods", [])
            ] if ds.get("methods") else [],
        )
        for ds in data.get("blueprint", {}).get("data_structures", [])
    ]

    return Blueprint(
        repo=data["source"]["repo"],
        language=data["source"]["language"],
        functions=functions,
        data_structures=data_structures,
    )


def get_blueprint_last_modified(path: Path) -> Optional[str]:
    """Read last_modified from a saved blueprint YAML file.

    Args:
        path: Path to the .yaml file

    Returns:
        ISO-8601 timestamp string, or None if not present
    """
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data.get("last_modified")  # type: ignore[return-value]
    except Exception:
        return None
