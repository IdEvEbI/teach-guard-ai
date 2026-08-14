"""从视频按固定间隔截图，供 OCR 与人工确认对照。"""

from __future__ import annotations

import hashlib
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


def clock_stem(seconds: float) -> str:
    return format_clock(seconds).replace(":", "-")


def parse_clock_stem(stem: str) -> int:
    if stem.isdigit():
        return int(stem)
    parts = stem.replace(":", "-").split("-")
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return 0


def is_clock_named(path: Path) -> bool:
    parts = path.stem.replace(":", "-").split("-")
    return len(parts) == 3 and all(part.isdigit() for part in parts)


def existing_snapshots(run_dir: Path) -> SnapshotResult | None:
    directory = snapshot_dir(run_dir)
    if not directory.is_dir():
        return None
    frames = sorted(path for path in directory.glob("*.jpg") if path.is_file() and path.stat().st_size > 0)
    if not frames:
        return SnapshotResult(directory=directory, frames=[], skipped=True)
    if not all(is_clock_named(path) for path in frames):
        return None
    return SnapshotResult(directory=directory, frames=frames, skipped=True)


def frame_seconds(path: Path) -> int:
    return parse_clock_stem(path.stem)


def frame_clock(path: Path) -> str:
    return format_clock(float(frame_seconds(path)))


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def keep_changed_frames(tmp_frames: list[Path], directory: Path, *, interval: float) -> list[Path]:
    """按时间命名；与上一张保留帧哈希相同则删除。"""
    kept: list[Path] = []
    prev_digest: str | None = None
    for index, tmp in enumerate(tmp_frames):
        digest = file_digest(tmp)
        dest = directory / f"{clock_stem(index * interval)}.jpg"
        if prev_digest is not None and digest == prev_digest:
            tmp.unlink(missing_ok=True)
            continue
        if dest.exists() and dest.resolve() != tmp.resolve():
            dest.unlink()
        tmp.replace(dest)
        kept.append(dest)
        prev_digest = digest
    return kept


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

    frames = keep_changed_frames(tmp_frames, directory, interval=interval)
    if not frames:
        raise SnapshotError("截图失败：去重后没有留下任何帧。")
    return SnapshotResult(directory=directory, frames=frames, skipped=False)
