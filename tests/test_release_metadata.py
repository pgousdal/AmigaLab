from pathlib import Path
from scripts.preservation.version import __version__


def test_authoritative_release_version():
    assert __version__ == "0.2.0"


def test_release_notes_and_changelog_match_version():
    root = Path(__file__).parents[1]
    assert "## [0.2.0] - 2026-08-04" in (root / "CHANGELOG.md").read_text()
    assert "AmigaLab v0.2.0" in (root / "docs/releases/v0.2.0.md").read_text()

