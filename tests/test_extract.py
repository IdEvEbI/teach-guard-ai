"""抽轨：跳过音频、缺 ffmpeg、真实短视频。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from teach_guard.cli import app
from teach_guard.extract import EXIT_EXTRACT_FAILED, EXIT_FFMPEG_MISSING, classify_media

runner = CliRunner()


def test_classify_media() -> None:
    assert classify_media(Path("a.mp3")) == "audio"
    assert classify_media(Path("a.MP4")) == "video"
    assert classify_media(Path("a.bin")) == "unknown"


def test_inspect_video_without_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"not-a-video")
    monkeypatch.setattr("teach_guard.extract.shutil.which", lambda _name: None)

    result = runner.invoke(app, ["inspect", str(source), "--output", str(tmp_path / "out")])

    assert result.exit_code == EXIT_FFMPEG_MISSING
    assert "未找到 ffmpeg" in result.stdout + result.stderr
    data = json.loads(next((tmp_path / "out").glob("*/manifest.json")).read_text(encoding="utf-8"))
    assert data["steps"][0]["status"] == "failed"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="本机未安装 ffmpeg")
def test_inspect_invalid_video_fails_extract(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"not-a-video")

    result = runner.invoke(app, ["inspect", str(source), "--output", str(tmp_path / "out")])

    assert result.exit_code == EXIT_EXTRACT_FAILED
    assert "抽轨失败" in result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="本机未安装 ffmpeg")
def test_inspect_extracts_tiny_video(tmp_path: Path) -> None:
    video = tmp_path / "tiny.mp4"
    made = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=0.3",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=16x16:d=0.3",
            "-shortest",
            str(video),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if made.returncode != 0:
        pytest.skip(f"无法生成测试视频：{made.stderr}")

    result = runner.invoke(app, ["inspect", str(video), "--output", str(tmp_path / "out")])

    assert result.exit_code == 0
    run_dir = tmp_path / "out" / "tiny"
    audio = run_dir / "tiny.mp3"
    assert audio.is_file()
    data = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert data["steps"][0]["status"] == "done"
    assert data["artifacts"]["audio"].endswith("tiny.mp3")
    assert "已抽出音轨" in result.stdout
