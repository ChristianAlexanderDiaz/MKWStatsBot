"""OCR sub-modules for the MKW Stats Bot OCR processor."""

from .name_resolver import NameResolver, extract_score_from_corrupted_token
from .score_pairer import ScorePairer
from .team_splitter import TeamSplitter

__all__ = [
    "NameResolver",
    "ScorePairer",
    "TeamSplitter",
    "extract_score_from_corrupted_token",
]
