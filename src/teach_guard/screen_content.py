"""从 RapidOCR 词里取出共屏主体，判断画面是否长时间未推进。"""

from __future__ import annotations

import re
from typing import Any

from teach_guard.transcribe import format_clock

JACCARD_THRESHOLD = 0.85
HOLD_SECONDS = 120

_CHROME_EXACT = {
    "100%",
    "Q 搜索",
    "此电脑",
    "回收站",
    "控制面板",
    "已编辑",
    "自动保存",
    "画布1",
}
_CHROME_MARKERS = (
    "自动保存",
    "DESKTOP-",
    "www.",
    "http://",
    "https://",
    "file://",
    "file:///",
    ".xmind",
    "Ctrl+",
    "主题('",
    "主题（",
    "主题:",
    "主题：",
)
_MENU_SHORTCUT = re.compile(r".+\([A-Z]\)$")
_CLOCK = re.compile(r"^\d{1,2}:\d{2}$")
_DATE = re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")
_IME_BLOCK = re.compile(r"1\.\s*\S+.+\d\.\s*\S+")
_NOISE = re.compile(r"^[\W_×口<>]+$")
_CANVAS = re.compile(r"^画布\d*$")


def is_chrome_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value or len(value) <= 1:
        return True
    if value in _CHROME_EXACT:
        return True
    if _CLOCK.match(value) or _DATE.match(value) or _MENU_SHORTCUT.match(value):
        return True
    if _CANVAS.match(value) or _NOISE.match(value):
        return True
    if _IME_BLOCK.search(value):
        return True
    lowered = value.lower()
    return any(marker.lower() in lowered or marker in value for marker in _CHROME_MARKERS)


def content_tokens(texts: list[str] | tuple[str, ...] | None) -> frozenset[str]:
    kept: list[str] = []
    for item in texts or []:
        value = str(item).strip()
        if not value or is_chrome_text(value):
            continue
        kept.append(value)
    return frozenset(kept)


def token_jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def same_content(left: frozenset[str], right: frozenset[str], *, threshold: float = JACCARD_THRESHOLD) -> bool:
    return token_jaccard(left, right) >= threshold


def unique_content_frames(
    frames: list[dict[str, Any]],
    *,
    threshold: float = JACCARD_THRESHOLD,
) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    previous: frozenset[str] | None = None
    for item in frames:
        if not isinstance(item, dict):
            continue
        texts = item.get("texts") if isinstance(item.get("texts"), list) else []
        tokens = content_tokens([str(text) for text in texts])
        if previous is not None:
            if not tokens or same_content(previous, tokens, threshold=threshold):
                continue
        unique.append(item)
        previous = tokens
    return unique


def content_holds(
    frames: list[dict[str, Any]],
    *,
    last_seconds: int | None = None,
    threshold: float = JACCARD_THRESHOLD,
    hold_seconds: int = HOLD_SECONDS,
) -> list[dict[str, Any]]:
    unique = unique_content_frames(frames, threshold=threshold)
    if not unique:
        return []
    times = [int(item.get("seconds") or 0) for item in unique]
    clocks = [str(item.get("clock") or format_clock(float(seconds))) for item, seconds in zip(unique, times)]
    edges = list(zip(times, times[1:], clocks, clocks[1:]))
    if last_seconds is not None and last_seconds > times[-1]:
        edges.append((times[-1], last_seconds, clocks[-1], format_clock(float(last_seconds))))
    holds: list[dict[str, Any]] = []
    for start, end, start_clock, end_clock in edges:
        gap = int(end) - int(start)
        if gap <= hold_seconds:
            continue
        holds.append(
            {
                "start": start_clock,
                "end": end_clock,
                "seconds": gap,
            }
        )
    return holds


def hold_suggestion(hold: dict[str, Any]) -> str:
    seconds = int(hold.get("seconds") or 0)
    minutes, remain = divmod(seconds, 60)
    span = f"{minutes} 分 {remain} 秒" if minutes else f"{remain} 秒"
    start = str(hold.get("start") or "")
    end = str(hold.get("end") or "")
    return (
        f"从 {start} 到 {end}（约 {span}）主画面处于静止，共屏主体词几乎没有变化。"
        "讲解结构图或讲义时，可把下一节点及时点出来，避免只靠口述。"
    )


def hold_notes(holds: list[dict[str, Any]]) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    for item in holds:
        notes.append(
            {
                "item": "长时间画面静止",
                "clock": str(item.get("start") or ""),
                "quote": "",
                "note": hold_suggestion(item),
            }
        )
    return notes
