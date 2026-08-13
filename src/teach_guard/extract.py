"""从视频抽音轨；输入已是音频则跳过。"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}

EXIT_FFMPEG_MISSING = 2
EXIT_EXTRACT_FAILED = 3


class FfmpegMissingError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("未找到 ffmpeg（抽视频音轨时需要，可用 brew install ffmpeg 安装）")


class ExtractError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractResult:
    audio_path: Path
    skipped: bool


def classify_media(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


def existing_audio_path(run_dir: Path, stem: str) -> Path | None:
    for suffix in (".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg", ".opus"):
        candidate = run_dir / f"{stem}{suffix}"
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate
    return None


def extract_audio(source: Path, run_dir: Path) -> ExtractResult:
    if classify_media(source) == "audio":
        dest = run_dir / f"{source.stem}{source.suffix.lower()}"
        shutil.copy2(source, dest)
        return ExtractResult(audio_path=dest, skipped=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FfmpegMissingError()

    dest = run_dir / f"{source.stem}.mp3"
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vn",
            "-acodec",
            "libmp3lame",
            "-q:a",
            "2",
            str(dest),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not dest.is_file():
        detail = (completed.stderr or completed.stdout or "ffmpeg 未写出音频").strip()
        raise ExtractError(f"抽轨失败：{detail}")
    return ExtractResult(audio_path=dest, skipped=False)
