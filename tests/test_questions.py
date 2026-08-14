"""提问与留白观察。"""

from __future__ import annotations

from teach_guard.questions import (
    attach_wait,
    frequency_label,
    harvest_empty_questions,
    wait_seconds_threshold,
)


def test_wait_seconds_threshold_default(monkeypatch) -> None:
    monkeypatch.delenv("WAIT_SECONDS", raising=False)
    assert wait_seconds_threshold() == 2.0
    monkeypatch.setenv("WAIT_SECONDS", "3.5")
    assert wait_seconds_threshold() == 3.5
    assert wait_seconds_threshold(1.0) == 1.0


def test_harvest_empty_questions() -> None:
    segments = [
        {"start": 8.0, "end": 9.0, "text": "能跟上我思路吧"},
        {"start": 20.0, "end": 21.0, "text": "是不是"},
        {"start": 30.0, "end": 31.0, "text": "接着往下聊"},
    ]
    found = harvest_empty_questions(segments)
    quotes = [item["quote"] for item in found]
    assert "是不是" in quotes
    assert "接着往下聊" not in quotes


def test_attach_wait_uses_gap_after() -> None:
    segments = [
        {"start": 10.0, "end": 12.0, "text": "你觉得一样吗"},
        {"start": 15.5, "end": 16.0, "text": "不一样吗"},
    ]
    attached = attach_wait(
        [{"clock": "00:00:10", "quote": "你觉得一样吗"}],
        segments,
        threshold=2.0,
    )
    assert attached[0]["waited"] is True
    assert attached[0]["gap_after"] == 3.5


def test_frequency_label() -> None:
    assert frequency_label(0, 100) == "0 次"
    assert "每" in frequency_label(5, 1500)
