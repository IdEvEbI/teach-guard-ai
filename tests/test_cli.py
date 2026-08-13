"""CLI 最小入口测试。"""

import hashlib
import json
from pathlib import Path

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


def test_inspect_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", str(tmp_path / "missing.mp4")])
    assert result.exit_code != 0


def test_inspect_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    payload = b"fake-media"
    source.write_bytes(payload)
    output_root = tmp_path / "output"

    result = runner.invoke(app, ["inspect", str(source), "--output", str(output_root)])

    assert result.exit_code == 0
    manifests = list(output_root.glob("*/manifest.json"))
    assert len(manifests) == 1
    data = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert data["command"] == "inspect"
    assert data["input"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert data["models"]["asr"]["size"] == "large-v3-turbo"
    assert data["models"]["llm"]["provider"] == "deepseek"
    assert {step["id"] for step in data["steps"]} >= {
        "extract_audio",
        "transcribe",
        "punctuate",
        "lesson_type",
        "review",
    }
    assert all(step["status"] == "pending" for step in data["steps"])
    assert "已创建运行目录" in result.stdout
