"""CLI 最小入口测试。"""

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from teach_guard.cli import app

runner = CliRunner()


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "教学守护" in result.stdout


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_inspect_help() -> None:
    result = runner.invoke(app, ["inspect", "--help"])
    assert result.exit_code == 0
    assert "视频或音频" in result.stdout
    assert "data/input" in result.stdout
    assert "data/output" in result.stdout


def test_inspect_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", str(tmp_path / "missing.mp4")])
    assert result.exit_code != 0
    assert "找不到输入文件" in result.stdout + result.stderr


def test_inspect_resolves_default_input_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INPUT_DIR", raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    source = tmp_path / "data" / "input" / "clip.mp3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fake-media")

    result = runner.invoke(app, ["inspect", "clip.mp3"])

    assert result.exit_code == 0
    run_dir = tmp_path / "data" / "output" / "clip"
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "clip.mp3").is_file()


def test_inspect_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp3"
    payload = b"fake-media"
    source.write_bytes(payload)
    output_root = tmp_path / "output"

    result = runner.invoke(app, ["inspect", str(source), "--output", str(output_root)])

    assert result.exit_code == 0
    run_dir = output_root / "clip"
    data = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert data["command"] == "inspect"
    assert data["input"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert data["models"]["asr"]["size"] == "large-v3-turbo"
    assert data["models"]["llm"]["provider"] == "deepseek"
    steps = {step["id"]: step["status"] for step in data["steps"]}
    assert steps["extract_audio"] == "skipped"
    assert steps["transcribe"] == "pending"
    assert "audio" in data["artifacts"]
    assert "已创建运行目录" in result.stdout
    assert "已跳过抽轨" in result.stdout


def test_inspect_mirrors_nested_input_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INPUT_DIR", raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    source = tmp_path / "data" / "input" / "01_课" / "day01" / "00.介绍(了解).mp3"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"fake-media")

    result = runner.invoke(app, ["inspect", str(source)])

    assert result.exit_code == 0
    run_dir = tmp_path / "data" / "output" / "01_课" / "day01" / "00.介绍(了解)"
    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "00.介绍(了解).mp3").is_file()
