# Adapted from team V2: agents/reader/__init__.py (feature/agent-integration @ a5a03ff)
"""Reader: any CV file (PDF, DOCX, scan, photo) -> clean text + sections."""

from .reader import ReaderError, ReaderResult, read_cv
from .sections import split_sections

__all__ = ["read_cv", "ReaderResult", "ReaderError", "split_sections"]
