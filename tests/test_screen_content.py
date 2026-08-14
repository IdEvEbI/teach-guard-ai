"""共屏主体词：滤边栏、Jaccard、超过 2 分钟的停住。"""

from __future__ import annotations

from teach_guard.screen_content import (
    HOLD_SECONDS,
    content_holds,
    content_tokens,
    is_chrome_text,
    same_content,
    unique_content_frames,
)


def test_is_chrome_text_drops_menu_clock_and_ime() -> None:
    assert is_chrome_text("文件(F)")
    assert is_chrome_text("08:44")
    assert is_chrome_text("2026/5/8")
    assert is_chrome_text("1. 算法 2. 算 3. 酸 4. 蒜 5. 苏安")
    assert is_chrome_text("自动保存:关闭。DESKTOP-CI18TDS")
    assert is_chrome_text("www.example.com")
    assert not is_chrome_text("机器学习算法分类：")
    assert not is_chrome_text("CART决策树")


def test_content_tokens_keep_lesson_words() -> None:
    tokens = content_tokens(
        [
            "文件(F)",
            "机器学习(ML)",
            "CART决策树",
            "08:44",
            "1. 算法 2. 算 3. 酸",
        ]
    )
    assert tokens == frozenset({"机器学习(ML)", "CART决策树"})


def test_same_content_ignores_chrome_drift() -> None:
    first = content_tokens(["机器学习算法分类：", "文件(F)", "08:42"])
    second = content_tokens(["机器学习算法分类：", "文件(F)", "08:43", "画布1"])
    assert same_content(first, second)


def test_unique_content_frames_collapse_chrome_only_changes() -> None:
    frames = [
        {"clock": "00:02:10", "seconds": 130, "texts": ["机器学习算法分类：", "08:42"]},
        {"clock": "00:02:20", "seconds": 140, "texts": ["机器学习算法分类：", "08:43"]},
        {"clock": "00:06:50", "seconds": 410, "texts": ["有监督算法", "无监督算法"]},
    ]
    unique = unique_content_frames(frames)
    assert [item["clock"] for item in unique] == ["00:02:10", "00:06:50"]


def test_content_holds_over_two_minutes() -> None:
    frames = [
        {"clock": "00:02:10", "seconds": 130, "texts": ["机器学习算法分类："]},
        {"clock": "00:02:20", "seconds": 140, "texts": ["机器学习算法分类：", "08:43"]},
        {"clock": "00:06:50", "seconds": 410, "texts": ["有监督算法"]},
    ]
    holds = content_holds(frames)
    assert len(holds) == 1
    assert holds[0]["start"] == "00:02:10"
    assert holds[0]["end"] == "00:06:50"
    assert holds[0]["seconds"] == 280
    assert holds[0]["seconds"] > HOLD_SECONDS


def test_content_holds_include_tail_until_last_seconds() -> None:
    frames = [{"clock": "00:10:00", "seconds": 600, "texts": ["今日目标"]}]
    holds = content_holds(frames, last_seconds=780)
    assert holds[0]["seconds"] == 180
    assert holds[0]["end"] == "00:13:00"


def test_empty_ocr_does_not_split_a_hold() -> None:
    frames = [
        {"clock": "00:00:00", "seconds": 0, "texts": ["机器学习算法分类："]},
        {"clock": "00:01:00", "seconds": 60, "texts": ["文件(F)", "08:44"]},
        {"clock": "00:03:00", "seconds": 180, "texts": ["机器学习算法分类：", "08:45"]},
    ]
    unique = unique_content_frames(frames)
    assert [item["clock"] for item in unique] == ["00:00:00"]
    holds = content_holds(frames, last_seconds=180)
    assert holds[0]["seconds"] == 180
