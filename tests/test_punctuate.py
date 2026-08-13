"""标点：不改词、批次切分、改词则回退原文。"""

from __future__ import annotations

import json
from pathlib import Path

from teach_guard.punctuate import (
    chunk_segments,
    punctuate_transcript,
    render_punct_markdown,
    tokens_preserved,
)


def test_tokens_preserved_allows_punctuation_only() -> None:
    original = "老师说 DeepSeek 8b 模型"
    assert tokens_preserved(original, "老师说 DeepSeek 8b 模型。")
    assert tokens_preserved(original, "老师说，DeepSeek 8b 模型。")
    assert not tokens_preserved(original, "老师说 DeepSeek 7b 模型。")
    assert not tokens_preserved("来个叫逻辑图向右", "来一个逻辑图，向右展开。")


def test_chunk_segments_by_time_and_count() -> None:
    segments = [{"start": float(i), "end": float(i) + 0.5, "text": str(i)} for i in range(10)]
    batches = chunk_segments(segments, max_seconds=4, max_count=4)
    assert [len(batch) for batch in batches] == [4, 4, 2]


def test_render_punct_markdown_keeps_clock_and_tokens() -> None:
    markdown = render_punct_markdown(
        segments=[{"start": 5.76, "end": 8.28, "text": "我在这里边写下机器学习。"}],
        model="deepseek-v4-flash",
        prompt_version="v0.1+abc",
    )
    assert "不改词" in markdown
    assert "[00:00:05 – 00:00:08]" in markdown
    assert "写下机器学习" in markdown


def test_punctuate_transcript_keeps_original_on_rewrite(tmp_path: Path) -> None:
    raw = tmp_path / "clip.raw.json"
    raw.write_text(
        json.dumps(
            {
                "model": "stub",
                "language": "zh",
                "segments": [
                    {"start": 0.0, "end": 2.0, "text": "老师说 DeepSeek 8b 模型"},
                    {"start": 2.0, "end": 4.0, "text": "来个叫逻辑图向右"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def complete(*, system: str, user: str) -> dict[str, object]:
        del system
        payload = json.loads(user)
        texts = {
            1: "老师说 DeepSeek 7b 模型。",
            2: "来个叫逻辑图向右。",
        }
        return {
            "segments": [
                {"i": item["i"], "text": texts[int(item["i"])]} for item in payload["segments"]
            ]
        }

    result = punctuate_transcript(raw, tmp_path, "clip", complete=complete)
    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["segments"][0]["text"] == "老师说 DeepSeek 8b 模型"
    assert data["segments"][0]["punctuated"] is False
    assert data["segments"][1]["text"] == "来个叫逻辑图向右。"
    assert data["segments"][1]["punctuated"] is True
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "DeepSeek 8b" in markdown
    assert "逻辑图向右" in markdown
