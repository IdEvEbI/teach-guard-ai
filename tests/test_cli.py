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
    assert "--type" in result.stdout
    assert "--punctuate" in result.stdout
    assert "--yes" in result.stdout
    assert "--wait-seconds" in result.stdout
    assert "sf=stage_first" in result.stdout


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
    assert (run_dir / "clip.raw.md").is_file()
    assert (run_dir / "clip.type.md").is_file()
    assert (run_dir / "clip.report.md").is_file()
    assert (run_dir / "clip.screen.md").is_file()
    assert not (run_dir / "clip.punct.md").is_file()


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
    assert steps["transcribe"] == "done"
    assert steps["punctuate"] == "skipped"
    assert steps["snapshot"] == "skipped"
    assert steps["screen_ocr"] == "done"
    assert steps["lesson_type"] == "done"
    assert steps["confirm"] == "done"
    assert steps["checked"] == "done"
    assert steps["review"] == "done"
    assert "transcript_punct_md" not in data["artifacts"]
    assert "screen_md" in data["artifacts"]
    assert "confirm_md" in data["artifacts"]
    assert "transcript_checked_md" in data["artifacts"]
    assert "report_md" in data["artifacts"]
    assert data["models"]["llm"]["status"] == "not_run" or data["models"]["llm"]["status"] == "done"
    assert data["prompts"]["versions"].get("review") == "stub"
    assert data["prompts"]["versions"].get("confirm") == "stub"
    assert (run_dir / "clip.raw.md").is_file()
    assert (run_dir / "clip.type.md").is_file()
    assert (run_dir / "clip.report.md").is_file()
    assert "已创建运行目录" in result.stdout
    assert "已写出原始逐字稿" in result.stdout
    assert "跳过标点" in result.stdout
    assert "已写出课型判定" in result.stdout
    assert "已写出建议报告" in result.stdout


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
    assert (run_dir / "00.介绍(了解).raw.md").is_file()
    assert (run_dir / "00.介绍(了解).type.md").is_file()
    assert (run_dir / "00.介绍(了解).report.md").is_file()
    assert (run_dir / "00.介绍(了解).screen.md").is_file()


@pytest.mark.no_stub_transcribe
def test_inspect_asr_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from teach_guard.transcribe import EXIT_ASR_MISSING, AsrMissingError

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AsrMissingError()

    monkeypatch.setattr("teach_guard.cli.transcribe_audio", boom)
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"fake-media")
    result = runner.invoke(app, ["inspect", str(source), "--output", str(tmp_path / "out")])
    assert result.exit_code == EXIT_ASR_MISSING
    assert "mlx-whisper" in result.stdout + result.stderr


def test_inspect_skips_extract_and_transcribe_when_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"fake-media")
    output_root = tmp_path / "out"
    first = runner.invoke(app, ["inspect", str(source), "--output", str(output_root)])
    assert first.exit_code == 0

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("复用运行目录时不应再次转写")

    monkeypatch.setattr("teach_guard.cli.transcribe_audio", boom)
    monkeypatch.setattr("teach_guard.cli.punctuate_transcript", boom)
    monkeypatch.setattr("teach_guard.cli.classify_lesson_type", boom)
    monkeypatch.setattr("teach_guard.cli.capture_snapshots", boom)
    monkeypatch.setattr("teach_guard.cli.ocr_snapshots", boom)
    second = runner.invoke(app, ["inspect", str(source), "--output", str(output_root), "--yes"])
    assert second.exit_code == 0
    assert "复用运行目录" in second.stdout
    assert "跳过转写" in second.stdout
    assert "已有音轨" in second.stdout
    assert "跳过标点" in second.stdout
    assert "跳过识别" in second.stdout
    assert "已写出建议报告" in second.stdout
    data = json.loads((output_root / "clip" / "manifest.json").read_text(encoding="utf-8"))
    steps = {step["id"]: step["status"] for step in data["steps"]}
    assert steps["lesson_type"] == "skipped"
    assert steps["screen_ocr"] == "skipped"
    assert steps["snapshot"] == "skipped"
    assert steps["confirm"] == "skipped"
    assert steps["checked"] == "done"
    assert steps["review"] == "done"


def test_inspect_type_override(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"fake-media")
    result = runner.invoke(
        app,
        ["inspect", str(source), "--output", str(tmp_path / "out"), "--type", "sf"],
    )
    assert result.exit_code == 0
    data = json.loads((tmp_path / "out" / "clip" / "clip.type.json").read_text(encoding="utf-8"))
    assert data["lesson_type"] == "stage_first"
    assert data["overridden"] is True
    assert "覆盖课型" in result.stdout
    assert (tmp_path / "out" / "clip" / "clip.report.md").is_file()


def test_inspect_rejects_unknown_type(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"fake-media")
    result = runner.invoke(
        app,
        ["inspect", str(source), "--output", str(tmp_path / "out"), "--type", "feedback"],
    )
    assert result.exit_code != 0
    assert "课型必须是" in result.stdout + result.stderr


@pytest.mark.no_stub_confirm
def test_inspect_missing_llm_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from teach_guard.llm import EXIT_LLM_CONFIG

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"fake-media")
    result = runner.invoke(app, ["inspect", str(source), "--output", str(tmp_path / "out")])
    assert result.exit_code == EXIT_LLM_CONFIG
    assert "LLM_API_KEY" in result.stdout + result.stderr
    combined = result.stdout + result.stderr
    assert "sk-" not in combined
