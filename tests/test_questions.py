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
        {"start": 22.0, "end": 23.0, "text": "你的参数10B是吧"},
        {"start": 30.0, "end": 31.0, "text": "接着往下聊"},
        {"start": 40.0, "end": 41.0, "text": "听懂了吗"},
    ]
    found = harvest_empty_questions(segments)
    quotes = [item["quote"] for item in found]
    assert "能跟上我思路吧" in quotes
    assert "听懂了吗" in quotes
    assert "是不是" not in quotes
    assert "你的参数10B是吧" not in quotes
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


def test_unwaited_specific_question_becomes_rhetorical() -> None:
    from teach_guard.questions import build_questions_payload

    segments = [
        {"start": 10.0, "end": 12.0, "text": "你觉得评估规则一样吗"},
        {"start": 12.0, "end": 14.0, "text": "其实不一样"},
        {"start": 40.0, "end": 42.0, "text": "能跟上我思路吧"},
    ]
    payload = build_questions_payload(
        segments,
        {
            "questions": {
                "specific": [{"clock": "00:00:10", "quote": "你觉得评估规则一样吗"}],
                "empty": [{"clock": "00:00:20", "quote": "是不是"}],
            }
        },
        threshold=2.0,
    )
    assert [item["quote"] for item in payload["rhetorical"]] == ["你觉得评估规则一样吗"]
    assert payload["specific"] == []
    quotes = [item["quote"] for item in payload["empty"]]
    assert "能跟上我思路吧" in quotes
    assert "是不是" not in quotes
