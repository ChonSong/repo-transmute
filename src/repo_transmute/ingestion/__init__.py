"""Ingestion module - clone, detect, parse repos."""

from repo_transmute.ingestion.clone import clone_repo
from repo_transmute.ingestion.detector import detect_language
from repo_transmute.ingestion.walker import walk_source_files

__all__ = ["clone_repo", "detect_language", "walk_source_files"]
