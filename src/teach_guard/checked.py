"""按确认记录改专名，写出确认逐字稿。不覆盖原始 .raw 产物。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from teach_guard.transcribe import format_clock

EXIT_CHECKED_FAILED = 14
CLOCK_WINDOW_SECONDS = 90.0


class CheckedError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckedResult:
    json_path: Path
    markdown_path: Path
    applied_count: int


def parse_clock_seconds(clock: str) -> float | None:
    parts = str(clock or "").strip().split(":")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def replace_heard(text: str, heard: str, canonical: str) -> tuple[str, int]:
    if not heard or heard == canonical or heard not in text:
        return text, 0
    if all(char.isascii() and (char.isalnum() or char in "._-+") for char in heard):
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(heard)}(?![A-Za-z0-9])")
        return pattern.subn(canonical, text)
    return text.replace(heard, canonical), text.count(heard)


def apply_confirmed_terms(
    segments: list[dict[str, Any]],
    terms: list[dict[str, Any]],
    *,
    window: float = CLOCK_WINDOW_SECONDS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    copied: list[dict[str, Any]] = [dict(item) for item in segments]
    applied: list[dict[str, Any]] = []
    ordered = sorted(
        (item for item in terms if isinstance(item, dict)),
        key=lambda item: len(str(item.get("heard") or "")),
        reverse=True,
    )
    for item in ordered:
        heard = str(item.get("heard") or "").strip()
        canonical = str(item.get("canonical") or "").strip()
        if not heard or not canonical or heard == canonical:
            continue
        clock = str(item.get("clock") or "").strip()
        center = parse_clock_seconds(clock)
        total = 0

        def run(indices: list[int]) -> int:
            count = 0
            for index in indices:
                text = str(copied[index].get("text") or "")
                new_text, n = replace_heard(text, heard, canonical)
                if n:
                    copied[index]["text"] = new_text
                    count += n
            return count

        nearby = [
            index
            for index, segment in enumerate(copied)
            if center is None or abs(float(segment.get("start") or 0) - center) <= window
        ]
        total = run(nearby)
        if total == 0:
            total = run(list(range(len(copied))))
        applied.append(
            {
                "clock": clock,
                "heard": heard,
                "canonical": canonical,
                "replacements": total,
            }
        )
    return copied, applied


def render_checked_markdown(
    *,
    segments: list[dict[str, Any]],
    applied: list[dict[str, Any]],
) -> str:
    lines = [
        "# 确认逐字稿",
        "",
        "- 本文件按确认记录替换已核对的专名，供报告模型阅读。",
        "- 原始识别仍以同目录 `.raw.md` 为准，本步不覆盖证据层。",
        "",
        "## 已替换",
        "",
    ]
    if applied:
        for item in applied:
            lines.append(
                f"- [{item.get('clock') or '？'}] 「{item.get('heard')}」→「{item.get('canonical')}」"
                f"（{item.get('replacements') or 0} 处）"
            )
    else:
        lines.append("- （确认记录里没有需要替换的专名。）")
    lines.extend(["", "## 片段", ""])
    if not segments:
        lines.append("（没有片段。）")
        lines.append("")
        return "\n".join(lines)
    for item in segments:
        start = format_clock(float(item.get("start", 0)))
        end = format_clock(float(item.get("end", 0)))
        text = str(item.get("text") or "").strip()
        lines.append(f"[{start} – {end}] {text}")
        lines.append("")
    return "\n".join(lines)


def write_checked(
    raw_json_path: Path,
    confirm_json_path: Path,
    run_dir: Path,
    stem: str,
) -> CheckedResult:
    try:
        raw = json.loads(raw_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckedError(f"确认逐字稿失败：无法读取原始逐字稿 {raw_json_path.name}") from exc
    try:
        confirm = json.loads(confirm_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckedError(f"确认逐字稿失败：无法读取确认记录 {confirm_json_path.name}") from exc
    if not isinstance(raw, dict):
        raise CheckedError("确认逐字稿失败：原始逐字稿不是 JSON 对象。")
    if not isinstance(confirm, dict):
        raise CheckedError("确认逐字稿失败：确认记录不是 JSON 对象。")

    segments = list(raw.get("segments") or [])
    terms = confirm.get("terms") if isinstance(confirm.get("terms"), list) else []
    copied, applied = apply_confirmed_terms(segments, list(terms))
    payload = {
        "source": "raw+confirm",
        "raw_untouched": True,
        "segments": copied,
        "applied": applied,
        "opening": confirm.get("opening") if isinstance(confirm.get("opening"), dict) else {},
    }
    json_path = run_dir / f"{stem}.checked.json"
    markdown_path = run_dir / f"{stem}.checked.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_checked_markdown(segments=copied, applied=applied), encoding="utf-8")
    return CheckedResult(
        json_path=json_path,
        markdown_path=markdown_path,
        applied_count=sum(int(item.get("replacements") or 0) for item in applied),
    )
