"""截图间隔与画面词表。"""

from __future__ import annotations

from pathlib import Path

from teach_guard.screen_ocr import ocr_snapshots, render_screen_markdown
from teach_guard.snapshot import frame_clock


def test_frame_clock_from_filename() -> None:
    assert frame_clock(Path("00600.jpg")) == "00:10:00"
    assert frame_clock(Path("00000.jpg")) == "00:00:00"


def test_ocr_snapshots_skips_duplicate_text(tmp_path: Path) -> None:
    first = tmp_path / "00000.jpg"
    second = tmp_path / "00010.jpg"
    first.write_bytes(b"fake")
    second.write_bytes(b"fake")

    def engine(path: Path) -> list[str]:
        del path
        return ["机器学习(ML)", "CART决策树"]

    result = ocr_snapshots([first, second], tmp_path, "clip", engine=engine)
    assert result.frame_count == 1
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "CART决策树" in markdown
    assert "不改逐字稿" in markdown


def test_render_screen_markdown_empty() -> None:
    markdown = render_screen_markdown({"engine": "rapidocr", "frames": []})
    assert "无截图" in markdown
