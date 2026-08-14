"""确认草稿：只送逐字稿；开场三项可逐条问。"""

from __future__ import annotations

import json

from teach_guard.confirm import (
    OFFSCREEN_TERM_LIMIT,
    apply_confirm_answers,
    draft_confirm,
    normalize_confirm_terms,
    render_confirm_markdown,
)


def test_apply_confirm_auto_prefers_screen() -> None:
    answers = apply_confirm_answers(
        {
            "terms": [
                {
                    "clock": "00:10:10",
                    "heard": "CRT决策数",
                    "screen": "CART决策树",
                    "snapshot": "snapshot/00-10-10.jpg",
                }
            ],
            "opening_needed": ["self_intro", "class_norms", "today_goal"],
        },
        lesson_type="stage_first",
        auto=True,
    )
    assert answers["terms"][0]["canonical"] == "CART决策树"
    assert answers["opening"]["self_intro"] == "missing_must_fix"
    assert answers["opening"]["today_goal"] == "missing_must_fix"


def test_apply_confirm_empty_screen_auto_keeps_heard() -> None:
    answers = apply_confirm_answers(
        {
            "terms": [
                {
                    "clock": "00:21:32",
                    "heard": "DeFi打遍",
                    "screen": "",
                    "snapshot": "",
                }
            ],
            "opening_needed": [],
        },
        lesson_type="practice",
        auto=True,
    )
    assert answers["terms"][0]["canonical"] == "DeFi打遍"
    assert answers["terms"][0]["source"] == "auto"


def test_apply_confirm_empty_screen_user_can_correct() -> None:
    def ask(_prompt: str) -> str:
        assert "画面未读到对应词" in _prompt
        return "Dify 答辩"

    answers = apply_confirm_answers(
        {
            "terms": [
                {
                    "clock": "00:21:32",
                    "heard": "DeFi打遍",
                    "screen": "",
                    "snapshot": "",
                }
            ],
            "opening_needed": [],
        },
        lesson_type="practice",
        auto=False,
        ask=ask,
    )
    assert answers["terms"][0]["canonical"] == "Dify 答辩"
    assert answers["terms"][0]["source"] == "user"


def test_apply_confirm_empty_enter_uses_screen() -> None:
    def ask(_prompt: str) -> str:
        return ""

    answers = apply_confirm_answers(
        {
            "terms": [
                {
                    "clock": "00:10:10",
                    "heard": "CRT决策数",
                    "screen": "CART决策树",
                    "snapshot": "snapshot/00-10-10.jpg",
                }
            ],
            "opening_needed": [],
        },
        lesson_type="practice",
        auto=False,
        ask=ask,
    )
    assert answers["terms"][0]["canonical"] == "CART决策树"


def test_draft_confirm_sends_transcript_only() -> None:
    captured: dict[str, str] = {}

    def complete(*, system: str, user: str) -> dict:
        del system
        captured["user"] = user
        return {"terms": [{"heard": "CRT决策数", "screen": "CART决策树"}], "opening_needed": ["today_goal"]}

    draft = draft_confirm(
        source_name="clip.avi",
        lesson_type="stage_first",
        segments=[{"start": 0.0, "end": 2.0, "text": "今天了解即可。"}],
        complete=complete,
    )
    payload = json.loads(captured["user"])
    assert "screen" not in payload
    assert "今天了解即可" in payload["transcript"]
    assert draft["terms"] == []
    assert draft["opening_needed"] == ["today_goal"]


def test_normalize_confirm_terms_dedupes_heard_and_caps_offscreen() -> None:
    items = [
        {"clock": "00:09:17", "heard": "CRT", "screen": "CART决策树", "snapshot": "a.jpg"},
        {"clock": "00:10:10", "heard": "CRT", "screen": "CART决策树", "snapshot": "b.jpg"},
        {"clock": "00:00:33", "heard": "扣子和DeFi", "screen": "", "snapshot": ""},
        {"clock": "00:03:10", "heard": "小米架步枪", "screen": "", "snapshot": ""},
        {"clock": "00:06:23", "heard": "多摩碳", "screen": "", "snapshot": ""},
        {"clock": "00:09:53", "heard": "近诸者赤", "screen": "", "snapshot": ""},
        {"clock": "00:11:37", "heard": "集思管异", "screen": "", "snapshot": ""},
        {"clock": "00:14:45", "heard": "剧类", "screen": "", "snapshot": ""},
        {"clock": "00:16:45", "heard": "能够让我思路不", "screen": "", "snapshot": ""},
    ]
    terms = normalize_confirm_terms(items)
    assert [item["heard"] for item in terms if item["screen"]] == ["CRT"]
    offscreen = [item["heard"] for item in terms if not item["screen"]]
    assert offscreen == ["扣子和DeFi", "小米架步枪", "多摩碳", "近诸者赤", "集思管异"]
    assert len(offscreen) == OFFSCREEN_TERM_LIMIT


def test_apply_confirm_ask_opening_choice() -> None:
    replies = iter(["2", "1", "3"])

    def ask(_prompt: str) -> str:
        return next(replies)

    answers = apply_confirm_answers(
        {
            "terms": [],
            "opening_needed": ["self_intro", "class_norms", "today_goal"],
        },
        lesson_type="stage_first",
        auto=False,
        ask=ask,
    )
    assert answers["terms"] == []
    assert answers["opening"]["self_intro"] == "prior_stage_short"
    assert answers["opening"]["class_norms"] == "missing_must_fix"
    assert answers["opening"]["today_goal"] == "not_in_this_recording"


def test_apply_confirm_accept_screen_skips_prompt_when_screen_has_term() -> None:
    asked: list[str] = []
    notes: list[str] = []

    def ask(prompt: str) -> str:
        asked.append(prompt)
        if "自我介绍" in prompt:
            return "2"
        return ""

    def notify(message: str) -> None:
        notes.append(message)

    answers = apply_confirm_answers(
        {
            "terms": [
                {
                    "clock": "00:10:10",
                    "heard": "CRT决策数",
                    "screen": "CART决策树",
                    "snapshot": "snapshot/00-10-10.jpg",
                },
                {
                    "clock": "00:21:32",
                    "heard": "DeFi打遍",
                    "screen": "",
                    "snapshot": "",
                },
            ],
            "opening_needed": ["self_intro"],
        },
        lesson_type="stage_first",
        auto=False,
        accept_screen=True,
        ask=ask,
        notify=notify,
    )
    assert answers["terms"][0]["canonical"] == "CART决策树"
    assert answers["terms"][0]["source"] == "screen"
    assert "已采用画面用词" in notes[0]
    assert answers["terms"][1]["canonical"] == "DeFi打遍"
    assert len(asked) == 2
    assert "DeFi打遍" in asked[0]
    assert "自我介绍" in asked[1]
    assert answers["opening"]["self_intro"] == "prior_stage_short"


def test_render_confirm_markdown_lists_terms() -> None:
    markdown = render_confirm_markdown(
        {
            "auto": True,
            "model": "stub",
            "terms": [{"clock": "00:10:10", "heard": "CRT", "canonical": "CART"}],
            "opening": {"self_intro": "missing_must_fix"},
        }
    )
    assert "CRT" in markdown
    assert "CART" in markdown
    assert "自我介绍" in markdown
    assert "非交互（--yes）" in markdown


def test_render_confirm_markdown_accept_screen_mode() -> None:
    markdown = render_confirm_markdown({"auto": False, "accept_screen": True, "terms": [], "opening": {}})
    assert "画面用词已自动采用" in markdown
