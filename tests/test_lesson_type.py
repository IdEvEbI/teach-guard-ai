"""课型识别：阶段第一课不是简介类。"""

from __future__ import annotations

import json
from pathlib import Path

from teach_guard.lesson_type import (
    classify_lesson_type,
    duration_seconds,
    head_segments,
    load_type_if_present,
    normalize_lesson_type,
    parse_cli_lesson_type,
    render_type_markdown,
)


def test_normalize_and_parse() -> None:
    assert parse_cli_lesson_type("stage_first") == "stage_first"
    assert parse_cli_lesson_type("Stage-First") == "stage_first"
    assert normalize_lesson_type("intro") == "intro"
    assert normalize_lesson_type("encyclopedia") == "other"


def test_parse_cli_rejects_unknown() -> None:
    try:
        parse_cli_lesson_type("feedback")
    except ValueError as exc:
        assert "intro" in str(exc)
    else:
        raise AssertionError("应当拒绝未知课型")


def test_head_segments_stops_at_two_minutes() -> None:
    segments = [
        {"start": 0.0, "end": 10.0, "text": "a"},
        {"start": 50.0, "end": 60.0, "text": "b"},
        {"start": 120.0, "end": 130.0, "text": "c"},
        {"start": 200.0, "end": 210.0, "text": "d"},
    ]
    head = head_segments(segments, seconds=120)
    assert [item["text"] for item in head] == ["a", "b"]
    assert duration_seconds(segments) == 210.0


def test_classify_stage_first_not_intro(tmp_path: Path) -> None:
    punct = tmp_path / "clip.punct.json"
    punct.write_text(
        json.dumps(
            {
                "segments": [
                    {"start": 0.0, "end": 4.0, "text": "好，接下来我们来简单介绍一下关于机器学习这个阶段。"},
                    {"start": 12.0, "end": 16.0, "text": "那么在这个阶段，我们的课程设计一共是四天。"},
                    {"start": 18.0, "end": 20.0, "text": "来个叫逻辑图向右。"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def complete(*, system: str, user: str) -> dict[str, object]:
        del system
        payload = json.loads(user)
        assert "大纲介绍" in payload["filename"]
        assert payload["head_segments"][0]["text"].startswith("好")
        return {
            "lesson_type": "stage_first",
            "confidence": "high",
            "delivery": "建立四天机器学习阶段地图，了解即可。",
            "ruler": "004",
            "reasons": ["开篇说明本阶段一共四天"],
            "not_type": "intro",
            "not_reason": "这是阶段地图，不是模块前用语铺垫。",
        }

    result = classify_lesson_type(
        punct,
        tmp_path,
        "clip",
        source_name="00.机器学习_大纲介绍(了解).avi",
        complete=complete,
    )
    assert result.lesson_type == "stage_first"
    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["not_type"] == "intro"
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "阶段第一课" in markdown
    assert "不是 `intro`" in markdown


def test_classify_override_skips_model(tmp_path: Path) -> None:
    punct = tmp_path / "clip.punct.json"
    punct.write_text(json.dumps({"segments": [{"start": 0, "end": 1, "text": "x"}]}), encoding="utf-8")

    def boom(*, system: str, user: str) -> dict[str, object]:
        del system, user
        raise AssertionError("覆盖课型时不应调用模型")

    result = classify_lesson_type(
        punct,
        tmp_path,
        "clip",
        source_name="x.mp3",
        override="practice",
        complete=boom,
    )
    assert result.lesson_type == "practice"
    assert result.overridden is True


def test_render_type_markdown_includes_delivery() -> None:
    markdown = render_type_markdown(
        {
            "lesson_type": "stage_first",
            "confidence": "high",
            "delivery": "四天地图，了解即可",
            "ruler": "004",
            "reasons": ["开篇讲四天"],
            "overridden": False,
            "model": "stub",
            "prompt_version": "v0.1",
        }
    )
    assert "四天地图" in markdown
    assert "004" in markdown


def test_load_type_if_present(tmp_path: Path) -> None:
    json_path = tmp_path / "clip.type.json"
    markdown_path = tmp_path / "clip.type.md"
    json_path.write_text(
        json.dumps(
            {
                "lesson_type": "stage_first",
                "prompt_version": "v0.1+abc",
                "model": "stub",
                "overridden": False,
            }
        ),
        encoding="utf-8",
    )
    markdown_path.write_text("# 课型判定\n", encoding="utf-8")
    loaded = load_type_if_present(tmp_path, "clip")
    assert loaded is not None
    assert loaded.lesson_type == "stage_first"
    assert loaded.prompt_version == "v0.1+abc"
    assert load_type_if_present(tmp_path, "missing") is None
