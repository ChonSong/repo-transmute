"""V2 vision module — visual analysis, scoring, diff generation."""

from repo_transmute.v2.vision.analyzer import analyze_layout, match_components
from repo_transmute.v2.vision.scorer import score_similarity
from repo_transmute.v2.vision.diff_generator import generate_visual_diff

__all__ = ['analyze_layout', 'match_components', 'score_similarity', 'generate_visual_diff']
