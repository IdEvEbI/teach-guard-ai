"""原始逐字稿渲染与转写落盘。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from teach_guard.transcribe import format_clock, render_raw_markdown, transcribe_audio


def test_format_clock() -> None:
    assert format_clock(0) == "00:00:00"
    assert format_clock(75) == "00:01:15"
    assert format_clock(3723) == "01:02:03"


def test_render_raw_markdown_keeps_original_tokens() -> None:
    markdown = render_raw_markdown(
        segments=[{"start": 0, "end": 4.2, "text": " 老师说 DeepSeek 8b 模型 "}],
        model="mlx-community/whisper-large-v3-turbo",
        language="zh",
    )
    assert "未补标点" in markdown
    assert "DeepSeek 8b" in markdown
    assert "[00:00:00 – 00:00:04]" in markdown


def test_transcribe_audio_writes_raw_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = SimpleNamespace(
        transcribe=lambda *_args, **_kwargs: {
            "text": "老师说 DeepSeek 8b 模型",
            "language": "zh",
            "segments": [{"start": 0.0, "end": 2.0, "text": "老师说 DeepSeek 8b 模型"}],
        }
    )
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake)
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"x")

    result = transcribe_audio(audio, tmp_path, "clip")

    assert result.markdown_path.is_file()
    assert result.json_path.is_file()
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "DeepSeek 8b" in markdown
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["segments"][0]["text"] == "老师说 DeepSeek 8b 模型"