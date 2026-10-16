"""Weak-evidence cues (validator v2): intent/exam phrases count as exposure; the same verbs describing work do not."""
import pytest

from matcher.validate import _WEAK


@pytest.mark.parametrize("text,weak", [
    ("Preparing for the AWS exam", True), ("Studying for CKA", True), ("Plans to learn Rust", True),
    ("Enrolled in a Kotlin course", True), ("Watched tutorials about Angular", True),
    ("Preparing financial statements in Excel", False), ("Studying user behaviour with SQL", False),
    ("Built Rust services", False),
])
def test_weak_cue(text, weak):
    assert bool(_WEAK.search(text)) is weak
