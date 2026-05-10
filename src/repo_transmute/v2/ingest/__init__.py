"""V2 ingest module — clone, detect, walk."""

from repo_transmute.v2.ingest.clone import clone_repo
from repo_transmute.v2.ingest.detector import detect_framework
from repo_transmute.v2.ingest.walker import walk_project

__all__ = ['clone_repo', 'detect_framework', 'walk_project']
