"""Regression coverage for data migration, where silent loss is unacceptable."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "migration", Path(__file__).parents[2] / "deploy/scripts/migrate.py"
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_copy_verifies_and_is_repeatable(tmp_path):
    source, target = tmp_path / "old", tmp_path / "new"
    source.mkdir()
    (source / "paper.pdf").write_bytes(b"paper content")
    first = migration.copy_verified(source, target)
    assert migration.copy_verified(source, target) == first
    assert (target / "paper.pdf").read_bytes() == b"paper content"


def test_conflicting_data_is_never_overwritten(tmp_path):
    source, target = tmp_path / "old", tmp_path / "new"
    source.mkdir()
    target.mkdir()
    (source / "history.json").write_text("old")
    (target / "history.json").write_text("new")
    with pytest.raises(ValueError, match="overwrite"):
        migration.copy_verified(source, target)
    assert (target / "history.json").read_text() == "new"


def test_rebases_windows_paths_only_when_file_was_migrated(tmp_path):
    (tmp_path / "papers").mkdir()
    (tmp_path / "papers/a.pdf").write_bytes(b"pdf")
    assert migration.rebase_path(
        r"D:\repo\.local\data\papers\a.pdf", "D:/repo/.local/data", tmp_path
    ) == str(tmp_path / "papers/a.pdf")
    with pytest.raises(FileNotFoundError):
        migration.rebase_path("D:/repo/.local/data/missing.pdf", "D:/repo/.local/data", tmp_path)
    assert migration.rebase_path("D:/other/a.pdf", "D:/repo/.local/data", tmp_path) == "D:/other/a.pdf"


def test_rebase_rejects_parent_traversal(tmp_path):
    with pytest.raises(ValueError, match="Invalid stored path"):
        migration.rebase_path("D:/repo/data/../secret", "D:/repo/data", tmp_path)


def test_copy_rejects_destination_link_outside_data(tmp_path):
    source, target, outside = tmp_path / "old", tmp_path / "new", tmp_path / "outside"
    source.mkdir()
    target.mkdir()
    outside.mkdir()
    (source / "papers").mkdir()
    (source / "papers/a.pdf").write_bytes(b"pdf")
    (target / "papers").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        migration.copy_verified(source, target)
    assert not (outside / "a.pdf").exists()
