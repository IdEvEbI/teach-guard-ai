"""确认草稿：自动接受画面用词；开场三项可逐条问。"""

from __future__ import annotations

from teach_guard.confirm import apply_confirm_answers, render_confirm_markdown


def test_apply_confirm_auto_prefers_screen() -> None:
    answers = apply_confirm_answers(
        {
            "terms": [
                {
                    "clock": "00:10:10",
                    "heard": "CRT决策数",
                    "screen": "CART决策树",
                    "snapshot": "snapshot/00600.jpg",
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


def test_apply_confirm_ask_opening_choice() -> None:
    replies = iter(["CART", "2", "1", "3"])

    def ask(_prompt: str) -> str:
        return next(replies)

    answers = apply_confirm_answers(
        {
            "terms": [{"clock": "00:01:00", "heard": "近林", "screen": "近邻", "snapshot": ""}],
            "opening_needed": ["self_intro", "class_norms", "today_goal"],
        },
        lesson_type="stage_first",
        auto=False,
        ask=ask,
    )
    assert answers["terms"][0]["canonical"] == "CART"
    assert answers["opening"]["self_intro"] == "prior_stage_short"
    assert answers["opening"]["class_norms"] == "missing_must_fix"
    assert answers["opening"]["today_goal"] == "not_in_this_recording"


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
