"""截图间隔与画面词表。"""

from __future__ import annotations

import json
from pathlib import Path

from teach_guard.screen_ocr import ocr_snapshots, render_screen_markdown
from teach_guard.snapshot import clock_stem, frame_clock, keep_changed_frames


def test_frame_clock_from_filename() -> None:
    assert frame_clock(Path("00-10-00.jpg")) == "00:10:00"
    assert frame_clock(Path("00000.jpg")) == "00:00:00"
    assert clock_stem(610) == "00-10-10"


def test_keep_changed_frames_drops_adjacent_hash_dupes(tmp_path: Path) -> None:
    first = tmp_path / "tmp_00001.jpg"
    second = tmp_path / "tmp_00002.jpg"
    third = tmp_path / "tmp_00003.jpg"
    first.write_bytes(b"slide-a")
    second.write_bytes(b"slide-a")
    third.write_bytes(b"slide-b")

    kept = keep_changed_frames([first, second, third], tmp_path, interval=10)
    names = [path.name for path in kept]
    assert names == ["00-00-00.jpg", "00-00-20.jpg"]
    assert not second.exists()
    assert (tmp_path / "00-00-00.jpg").read_bytes() == b"slide-a"
    assert (tmp_path / "00-00-20.jpg").read_bytes() == b"slide-b"


def test_ocr_snapshots_skips_duplicate_text(tmp_path: Path) -> None:
    first = tmp_path / "00-00-00.jpg"
    second = tmp_path / "00-00-10.jpg"
    first.write_bytes(b"fake")
    second.write_bytes(b"fake")

    def engine(path: Path) -> list[str]:
        del path
        return ["机器学习(ML)", "CART决策树"]

    result = ocr_snapshots([first, second], tmp_path, "clip", engine=engine)
    assert result.frame_count == 1
    assert result.duplicate_count == 1
    assert first.exists()
    assert not second.exists()
    assert (tmp_path / "snapshot" / "duplicate" / "00-00-10.jpg").is_file()
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "CART决策树" in markdown
    assert "不改逐字稿" in markdown


def test_ocr_snapshots_collapses_chrome_drift(tmp_path: Path) -> None:
    first = tmp_path / "00-00-00.jpg"
    second = tmp_path / "00-00-10.jpg"
    third = tmp_path / "00-03-00.jpg"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    third.write_bytes(b"c")

    replies = iter(
        [
            ["机器学习算法分类：", "文件(F)", "08:42"],
            ["机器学习算法分类：", "文件(F)", "08:43"],
            ["有监督算法", "无监督算法"],
        ]
    )

    def engine(_path: Path) -> list[str]:
        return list(next(replies))

    result = ocr_snapshots([first, second, third], tmp_path, "clip", engine=engine)
    assert result.frame_count == 2
    assert result.duplicate_count == 1
    assert not second.exists()
    assert (tmp_path / "snapshot" / "duplicate" / "00-00-10.jpg").is_file()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["content_holds"][0]["seconds"] == 180
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "长时间画面静止" in markdown
    assert "## 帧" in markdown


def test_render_screen_markdown_empty() -> None:
    markdown = render_screen_markdown({"engine": "rapidocr", "frames": []})
    assert "无截图" in markdown
