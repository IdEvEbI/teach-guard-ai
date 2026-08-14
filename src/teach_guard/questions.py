"""从逐字稿时间轴观察老师发出的提问与空问。不判断学员是否接住。"""

from __future__ import annotations

import os
from typing import Any

from teach_guard.transcribe import format_clock

DEFAULT_WAIT_SECONDS = 2.0
WAIT_ENV = "WAIT_SECONDS"

EMPTY_MARKERS = (
    "听懂了吗",
    "听明白了吗",
    "明白了吗",
    "清楚了吗",
    "懂了吗",
    "能跟上吗",
    "跟上了吗",
    "有没有问题",
    "是还不是",
    "对不对",
    "好不好",
    "是不是",
    "对吧",
    "是吧",
    "对吗",
)


def wait_seconds_threshold(override: float | None = None) -> float:
    if override is not None:
        return max(0.0, float(override))
    raw = os.environ.get(WAIT_ENV, str(DEFAULT_WAIT_SECONDS)).strip() or str(DEFAULT_WAIT_SECONDS)
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_WAIT_SECONDS


def parse_clock_seconds(clock: str) -> float | None:
    parts = str(clock or "").strip().split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        return None


def gap_after_seconds(segments: list[dict[str, Any]]) -> list[float]:
    gaps: list[float] = []
    for index, item in enumerate(segments):
        end = float(item.get("end") or 0)
        if index + 1 >= len(segments):
            gaps.append(0.0)
            continue
        nxt = float(segments[index + 1].get("start") or 0)
        gaps.append(max(0.0, nxt - end))
    return gaps


def nearest_segment_index(segments: list[dict[str, Any]], clock: str) -> int | None:
    center = parse_clock_seconds(clock)
    if center is None or not segments:
        return None
    best = 0
    best_delta = abs(float(segments[0].get("start") or 0) - center)
    for index, item in enumerate(segments[1:], start=1):
        delta = abs(float(item.get("start") or 0) - center)
        if delta < best_delta:
            best = index
            best_delta = delta
    return best


def harvest_empty_questions(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in segments:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        hit = next((marker for marker in EMPTY_MARKERS if marker in text), None)
        if not hit:
            continue
        clock = format_clock(float(item.get("start") or 0))
        key = (clock, text)
        if key in seen:
            continue
        seen.add(key)
        found.append({"clock": clock, "quote": text, "marker": hit})
    return found


def attach_wait(
    items: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    *,
    threshold: float,
) -> list[dict[str, Any]]:
    gaps = gap_after_seconds(segments)
    attached: list[dict[str, Any]] = []
    for item in items:
        clock = str(item.get("clock") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if not quote:
            continue
        index = nearest_segment_index(segments, clock) if clock else None
        gap = gaps[index] if index is not None else 0.0
        attached.append(
            {
                "clock": clock or (format_clock(float(segments[index].get("start") or 0)) if index is not None else ""),
                "quote": quote,
                "gap_after": round(gap, 1),
                "waited": gap + 1e-9 >= threshold,
            }
        )
    return attached


def merge_empty_questions(
    harvested: list[dict[str, Any]],
    from_model: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    *,
    threshold: float,
) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    for item in harvested:
        combined.append({"clock": item["clock"], "quote": item["quote"]})
    for item in from_model:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or item.get("text") or "").strip()
        if not quote:
            continue
        combined.append({"clock": str(item.get("clock") or "").strip(), "quote": quote})
    return attach_wait(_unique_by_clock_quote(combined), segments, threshold=threshold)


def normalize_specific_questions(
    items: Any,
    segments: list[dict[str, Any]],
    *,
    threshold: float,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return collected
    for item in items:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or item.get("text") or "").strip()
        if not quote:
            continue
        collected.append({"clock": str(item.get("clock") or "").strip(), "quote": quote})
    return attach_wait(_unique_by_clock_quote(collected), segments, threshold=threshold)


def _unique_by_clock_quote(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = (item.get("clock") or "", item.get("quote") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def frequency_label(count: int, duration: float) -> str:
    if count <= 0 or duration <= 0:
        return f"{count} 次"
    minutes = duration / 60.0
    per = minutes / count
    return f"{count} 次，约每 {per:.1f} 分钟一次"


def build_questions_payload(
    segments: list[dict[str, Any]],
    raw: dict[str, Any],
    *,
    threshold: float,
) -> dict[str, Any]:
    duration = 0.0
    if segments:
        duration = float(segments[-1].get("end") or 0)
    model_block = raw.get("questions") if isinstance(raw.get("questions"), dict) else {}
    specific = normalize_specific_questions(
        model_block.get("specific") if isinstance(model_block, dict) else [],
        segments,
        threshold=threshold,
    )
    empty = merge_empty_questions(
        harvest_empty_questions(segments),
        list(model_block.get("empty") or []) if isinstance(model_block, dict) else [],
        segments,
        threshold=threshold,
    )
    return {
        "wait_seconds": threshold,
        "specific": specific,
        "empty": empty,
        "specific_count": len(specific),
        "empty_count": len(empty),
        "empty_frequency": frequency_label(len(empty), duration),
        "duration": format_clock(duration),
    }
