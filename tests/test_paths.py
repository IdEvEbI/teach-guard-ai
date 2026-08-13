"""输入 / 输出路径解析。"""

from pathlib import Path

import pytest

from teach_guard.paths import output_run_dir, resolve_input_file


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


def test_output_run_dir_mirrors_input_tree(tmp_path: Path) -> None:
    source = tmp_path / "data" / "input" / "01_课" / "day01" / "00.介绍(了解).avi"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"x")
    expected = tmp_path / "data" / "output" / "01_课" / "day01" / "00.介绍(了解)"
    assert (
        output_run_dir(source, tmp_path / "data" / "output", tmp_path / "data" / "input") == expected
    )


def test_output_run_dir_outside_input_uses_stem(tmp_path: Path) -> None:
    source = tmp_path / "elsewhere" / "clip.mp4"
    source.parent.mkdir()
    source.write_bytes(b"x")
    assert output_run_dir(source, tmp_path / "out", tmp_path / "data" / "input") == tmp_path / "out" / "clip"
