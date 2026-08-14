"""从视频按固定间隔截图，供 OCR 与人工确认对照。"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from teach_guard.extract import FfmpegMissingError, classify_media
from teach_guard.transcribe import format_clock

SNAPSHOT_DIRNAME = "snapshot"
INTERVAL_SECONDS = 10.0
EXIT_SNAPSHOT_FAILED = 10


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotResult:
    directory: Path
    frames: list[Path]
    skipped: bool


def snapshot_dir(run_dir: Path) -> Path:
    return run_dir / SNAPSHOT_DIRNAME


def existing_snapshots(run_dir: Path) -> SnapshotResult | None:
    directory = snapshot_dir(run_dir)
    if not directory.is_dir():
        return None
    frames = sorted(path for path in directory.glob("*.jpg") if path.is_file() and path.stat().st_size > 0)
    return SnapshotResult(directory=directory, frames=frames, skipped=True)


def frame_clock(path: Path) -> str:
    stem = path.stem
    if stem.isdigit():
        return format_clock(float(int(stem)))
    return format_clock(0)


def capture_snapshots(source: Path, run_dir: Path, *, interval: float = INTERVAL_SECONDS) -> SnapshotResult:
    directory = snapshot_dir(run_dir)
    if classify_media(source) != "video":
        directory.mkdir(parents=True, exist_ok=True)
        return SnapshotResult(directory=directory, frames=[], skipped=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FfmpegMissingError()

    directory.mkdir(parents=True, exist_ok=True)
    for leftover in directory.glob("*.jpg"):
        leftover.unlink()

    pattern = directory / "tmp_%05d.jpg"
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            f"fps=1/{interval}",
            "-q:v",
            "4",
            str(pattern),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    tmp_frames = sorted(directory.glob("tmp_*.jpg"))
    if completed.returncode != 0 or not tmp_frames:
        detail = (completed.stderr or completed.stdout or "ffmpeg 未写出截图").strip()
        raise SnapshotError(f"截图失败：{detail}")

    frames: list[Path] = []
    for index, tmp in enumerate(tmp_frames):
        dest = directory / f"{int(index * interval):05d}.jpg"
        tmp.replace(dest)
        frames.append(dest)
    return SnapshotResult(directory=directory, frames=frames, skipped=False)
