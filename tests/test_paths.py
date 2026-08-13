"""输入 / 输出路径解析。"""

from pathlib import Path

import pytest

from teach_guard.paths import resolve_input_file


def test_resolve_existing_path(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"x")
    assert resolve_input_file(source) == source


def test_resolve_under_default_input_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INPUT_DIR", raising=False)
    nested = tmp_path / "data" / "input" / "clip.mp4"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"x")
    assert resolve_input_file(Path("clip.mp4")).resolve() == nested.resolve()
