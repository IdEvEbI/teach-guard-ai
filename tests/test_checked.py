"""确认逐字稿：按确认记录改专名，不覆盖 raw。"""

from __future__ import annotations

import json
from pathlib import Path

from teach_guard.checked import apply_confirmed_terms, replace_heard, write_checked


def test_replace_heard_ascii_word_boundary() -> None:
    text, count = replace_heard("KNN 与 KN 分类", "KN", "KNN")
    assert count == 1
    assert text == "KNN 与 KNN 分类"


def test_apply_confirmed_terms_near_clock() -> None:
    segments = [
        {"start": 0.0, "end": 2.0, "text": "开场"},
        {"start": 550.0, "end": 554.0, "text": "KN 分类"},
        {"start": 610.0, "end": 614.0, "text": "CRT决策数"},
    ]
    copied, applied = apply_confirmed_terms(
        segments,
        [
            {"clock": "00:09:10", "heard": "KN", "canonical": "KNN"},
            {"clock": "00:10:10", "heard": "CRT决策数", "canonical": "CART决策树"},
        ],
    )
    assert copied[1]["text"] == "KNN 分类"
    assert copied[2]["text"] == "CART决策树"
    assert copied[0]["text"] == "开场"
    assert [item["replacements"] for item in applied] == [1, 1]


def test_write_checked_leaves_raw_untouched(tmp_path: Path) -> None:
    raw = tmp_path / "clip.raw.json"
    raw.write_text(
        json.dumps(
            {
                "segments": [
                    {"start": 0.0, "end": 2.0, "text": "波士顿防价预测"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    original = raw.read_text(encoding="utf-8")
    confirm = tmp_path / "clip.confirm.json"
    confirm.write_text(
        json.dumps(
            {
                "terms": [
                    {
                        "clock": "00:00:00",
                        "heard": "波士顿防价预测",
                        "canonical": "波士顿房价预测",
                    }
                ],
                "opening": {"today_goal": "missing_must_fix"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = write_checked(raw, confirm, tmp_path, "clip")
    assert raw.read_text(encoding="utf-8") == original
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["raw_untouched"] is True
    assert payload["segments"][0]["text"] == "波士顿房价预测"
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert "波士顿房价预测" in markdown
    assert "不覆盖证据层" in markdown
