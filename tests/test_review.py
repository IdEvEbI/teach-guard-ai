"""建议报告：无摘句不得写入合格线。"""

from __future__ import annotations

import json
from pathlib import Path

from teach_guard.review import (
    compact_transcript,
    keep_cited,
    render_report_markdown,
    without_blackboard,
    write_review,
)


def test_without_blackboard_rewrites_fix_language() -> None:
    assert without_blackboard("对照板书确认字号。") == "对照共屏确认字号。"


def test_keep_cited_drops_items_without_quote() -> None:
    kept = keep_cited(
        [
            {
                "item": "缺就业必要性",
                "clock": "00:01:00",
                "quote": "本阶段很重要",
                "fix": "先讲培养链位置。",
            },
            {"item": "无摘句", "clock": "", "quote": "", "fix": "不要写进合格线。"},
            {"item": "只有时间", "clock": "00:02:00", "quote": "", "fix": "仍应丢弃。"},
        ]
    )
    assert [item["item"] for item in kept] == ["缺就业必要性"]


def test_compact_transcript_uses_start_clock() -> None:
    text = compact_transcript(
        [
            {"start": 5.2, "end": 8.0, "text": "本阶段一共四天。"},
            {"start": 12.0, "end": 14.0, "text": "  "},
        ]
    )
    assert text == "[00:00:05] 本阶段一共四天。"


def test_render_report_splits_must_and_nice() -> None:
    markdown = render_report_markdown(
        {
            "lesson_type": "stage_first",
            "ruler": "004",
            "duration": "00:25:00",
            "delivery": "建立四天地图，了解即可。",
            "coverage": "只覆盖「学什么」。",
            "summary": "本段是阶段地图。",
            "structure": {
                "modules": [
                    {
                        "title": "阶段地位",
                        "start": "00:00:00",
                        "end": "00:08:00",
                        "note": "讲培养链位置。",
                    }
                ],
                "why": "就业需要机器学习。",
                "what": "四天学什么。",
                "how": "了解即可。",
                "structure_note": "主线清楚。",
            },
            "must_fix": [
                {
                    "item": "阶段末成果只停留在口头",
                    "clock": "00:10:00",
                    "quote": "学完就能做很多东西",
                    "fix": "共屏演示阶段末结果。",
                }
            ],
            "nice_to_have": [
                {
                    "item": "时长略超参考",
                    "clock": "",
                    "quote": "",
                    "note": "「学什么」约 25 分钟，可收一收各天展开。",
                }
            ],
            "playback": ["本段未出现自我介绍，待回放下一段。"],
            "concepts": [],
            "asr_suspects": [{"clock": "00:08:00", "heard": "K 近林", "likely": "K 近邻"}],
            "model": "stub",
            "prompt_version": "v0.1",
        }
    )
    assert "## 合格线（必须改）" in markdown
    assert "## 水平线（锦上添花）" in markdown
    assert "只覆盖「学什么」" in markdown
    assert "不要当成老师合格线问题" in markdown
    assert "板书" not in markdown


def test_write_review_drops_uncited_must_fix(tmp_path: Path) -> None:
    punct = tmp_path / "clip.punct.json"
    punct.write_text(
        json.dumps(
            {
                "segments": [
                    {"start": 0.0, "end": 4.0, "text": "本阶段课程设计一共是四天。"},
                    {"start": 20.0, "end": 24.0, "text": "了解即可，不要深挖。"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    typed = tmp_path / "clip.type.json"
    typed.write_text(
        json.dumps(
            {
                "lesson_type": "stage_first",
                "delivery": "建立四天地图，了解即可。",
                "ruler": "004",
                "reasons": ["开篇讲四天"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def complete(*, system: str, user: str) -> dict[str, object]:
        assert "对事不对人" in system
        payload = json.loads(user)
        assert payload["lesson_type"] == "stage_first"
        assert "[00:00:00] 本阶段课程设计一共是四天。" in payload["transcript"]
        return {
            "summary": "本段只覆盖学什么。",
            "delivery": "建立四天地图。",
            "coverage": "只覆盖「学什么」。",
            "structure": {
                "modules": [
                    {
                        "title": "四天地图",
                        "start": "00:00:00",
                        "end": "00:00:24",
                        "note": "了解即可。",
                    }
                ],
                "why": "",
                "what": "四天学什么。",
                "how": "了解即可。",
                "structure_note": "主线清楚。",
            },
            "must_fix": [
                {
                    "item": "编造的缺口",
                    "clock": "",
                    "quote": "",
                    "fix": "不应出现在报告里。",
                }
            ],
            "nice_to_have": [{"item": "时长观察", "suggestion": "可再收一收。"}],
            "playback": ["未出现自我介绍，待回放。"],
            "concepts": [],
            "asr_suspects": [],
        }

    result = write_review(
        punct,
        typed,
        tmp_path,
        "clip",
        source_name="大纲介绍.avi",
        complete=complete,
    )
    data = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert data["must_fix"] == []
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "编造的缺口" not in markdown
    assert "未出现自我介绍" in markdown
    assert "只覆盖「学什么」" in markdown
