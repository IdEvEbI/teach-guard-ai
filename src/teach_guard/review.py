"""单视频精查报告：现场结构、概念观察、合格线 / 水平线 / 待回放。不打分。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from teach_guard.lesson_type import TYPE_LABELS, normalize_lesson_type
from teach_guard.llm import LlmConfigError, chat_json, llm_model
from teach_guard.punctuate import prompts_dir
from teach_guard.transcribe import format_clock

PROMPT_FILES = (
    "system_tone.md",
    "knowledge_cases.md",
    "structure_single.md",
    "coach_feedback.md",
)
EXIT_REVIEW_FAILED = 9
REVIEW_TIMEOUT = 180.0

JsonComplete = Callable[..., dict[str, Any]]


class ReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReviewResult:
    markdown_path: Path
    json_path: Path
    prompt_version: str
    model: str


def _prompt_version_tag(text: str) -> str:
    version = "v0.1"
    for line in text.splitlines():
        if line.startswith("- **版本**："):
            version = line.split("：", 1)[1].strip()
            break
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{version}+{digest}"


def load_review_prompt() -> tuple[str, str]:
    chunks: list[str] = []
    missing: list[str] = []
    for name in PROMPT_FILES:
        path = prompts_dir() / name
        if not path.is_file():
            path = Path.cwd() / "prompts" / name
        if not path.is_file():
            missing.append(name)
            continue
        chunks.append(path.read_text(encoding="utf-8").strip())
    if missing:
        joined = "、".join(missing)
        raise ReviewError(f"找不到建议报告提示词：{joined}")
    text = "\n\n".join(chunks)
    return text, _prompt_version_tag(text)


def compact_transcript(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in segments:
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        clock = format_clock(float(item.get("start", 0)))
        lines.append(f"[{clock}] {text}")
    return "\n".join(lines)


def duration_seconds(segments: list[dict[str, Any]]) -> float:
    if not segments:
        return 0.0
    return float(segments[-1].get("end", 0))


def without_blackboard(text: str) -> str:
    """改法禁止默认板书；模型若仍写出则换成共屏。"""
    return text.replace("板书", "共屏")


def keep_cited(items: Any, *, fix_key: str = "fix") -> list[dict[str, str]]:
    """合格线必须同时有条目、时间锚和摘句。"""
    kept: list[dict[str, str]] = []
    if not isinstance(items, list):
        return kept
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("item") or "").strip()
        clock = str(item.get("clock") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if not title or not clock or not quote:
            continue
        kept.append(
            {
                "item": without_blackboard(title),
                "clock": clock,
                "quote": quote,
                "fix": without_blackboard(str(item.get(fix_key) or item.get("suggestion") or "").strip()),
            }
        )
    return kept


def normalize_notes(items: Any, *, note_key: str) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    if not isinstance(items, list):
        return notes
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("item") or "").strip()
        if not title:
            continue
        notes.append(
            {
                "item": without_blackboard(title),
                "clock": str(item.get("clock") or "").strip(),
                "quote": str(item.get("quote") or "").strip(),
                "note": without_blackboard(str(item.get(note_key) or item.get("note") or "").strip()),
            }
        )
    return notes


def normalize_asr_suspects(items: Any) -> list[dict[str, str]]:
    suspects: list[dict[str, str]] = []
    if not isinstance(items, list):
        return suspects
    for item in items:
        if not isinstance(item, dict):
            continue
        heard = str(item.get("heard") or "").strip()
        if not heard:
            continue
        suspects.append(
            {
                "clock": str(item.get("clock") or "").strip(),
                "heard": heard,
                "likely": str(item.get("likely") or "").strip(),
            }
        )
    return suspects


def normalize_modules(items: Any) -> list[dict[str, str]]:
    modules: list[dict[str, str]] = []
    if not isinstance(items, list):
        return modules
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        modules.append(
            {
                "title": title,
                "start": str(item.get("start") or "").strip(),
                "end": str(item.get("end") or "").strip(),
                "note": without_blackboard(str(item.get("note") or "").strip()),
            }
        )
    return modules


def _string_list(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [without_blackboard(str(item).strip()) for item in items if str(item).strip()]


def _build_user_payload(
    *,
    source_name: str,
    type_payload: dict[str, Any],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    lesson_type = normalize_lesson_type(str(type_payload.get("lesson_type") or ""))
    return {
        "filename": source_name,
        "duration": format_clock(duration_seconds(segments)),
        "lesson_type": lesson_type,
        "type_label": TYPE_LABELS.get(lesson_type, lesson_type),
        "type_delivery": str(type_payload.get("delivery") or "").strip(),
        "ruler": str(type_payload.get("ruler") or "").strip(),
        "type_reasons": type_payload.get("reasons") or [],
        "transcript": compact_transcript(segments),
    }


def render_report_markdown(payload: dict[str, Any]) -> str:
    lesson_type = str(payload.get("lesson_type") or "other")
    label = TYPE_LABELS.get(lesson_type, lesson_type)
    lines = [
        "# 精查报告",
        "",
        f"- 课型：`{lesson_type}`（{label}）",
        f"- 对照专文：{payload.get('ruler') or '（无）'}",
        f"- 时长：{payload.get('duration') or '（未知）'}",
        f"- 主交付：{payload.get('delivery') or '（未写）'}",
        f"- 本段覆盖：{payload.get('coverage') or '（未写）'}",
        f"- 模型：`{payload.get('model') or ''}`",
        f"- 提示词：{payload.get('prompt_version') or ''}",
        "",
        "## 结论摘要",
        "",
        str(payload.get("summary") or "（未写摘要。）").strip(),
        "",
        "## 现场结构",
        "",
    ]
    structure = payload.get("structure") if isinstance(payload.get("structure"), dict) else {}
    modules = structure.get("modules") if isinstance(structure, dict) else []
    if isinstance(modules, list) and modules:
        for item in modules:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            start = str(item.get("start") or "").strip()
            end = str(item.get("end") or "").strip()
            note = str(item.get("note") or "").strip()
            clock = " – ".join(part for part in (start, end) if part)
            head = f"- **{title}**"
            if clock:
                head += f"（{clock}）"
            if note:
                head += f"：{note}"
            lines.append(head)
        lines.append("")
    else:
        lines.append("- （未写出模块切分。）")
        lines.append("")
    for key, heading in (("why", "Why"), ("what", "What"), ("how", "How")):
        text = str(structure.get(key) or "").strip() if isinstance(structure, dict) else ""
        lines.append(f"- {heading}：{text or '（稿上未形成可核对的口头表述。）'}")
    note = str(structure.get("structure_note") or "").strip() if isinstance(structure, dict) else ""
    if note:
        lines.extend(["", note])
    lines.extend(["", "## 合格线（必须改）", ""])
    must_fix = payload.get("must_fix") if isinstance(payload.get("must_fix"), list) else []
    if must_fix:
        for item in must_fix:
            if not isinstance(item, dict):
                continue
            lines.append(f"### {item.get('item')}")
            lines.append("")
            lines.append(f"- 摘句：[{item.get('clock')}] {item.get('quote')}")
            fix = str(item.get("fix") or "").strip()
            if fix:
                lines.append(f"- 改法：{fix}")
            lines.append("")
    else:
        lines.append("本段稿上没有足以写成必须改的摘句。")
        lines.append("")
    lines.extend(["## 水平线（锦上添花）", ""])
    nice = payload.get("nice_to_have") if isinstance(payload.get("nice_to_have"), list) else []
    if nice:
        for item in nice:
            if not isinstance(item, dict):
                continue
            title = str(item.get("item") or "").strip()
            clock = str(item.get("clock") or "").strip()
            quote = str(item.get("quote") or "").strip()
            suggestion = str(item.get("note") or "").strip()
            head = f"- **{title}**"
            if clock:
                head += f"（[{clock}]）"
            lines.append(head)
            if quote:
                lines.append(f"  - 摘句：{quote}")
            if suggestion:
                lines.append(f"  - 建议：{suggestion}")
        lines.append("")
    else:
        lines.append("- （无。）")
        lines.append("")
    lines.extend(["## 待回放确认", ""])
    playback = payload.get("playback") if isinstance(payload.get("playback"), list) else []
    if playback:
        for item in playback:
            text = str(item).strip()
            if text:
                lines.append(f"- {text}")
    else:
        lines.append("- （无。）")
    lines.append("")
    concepts = payload.get("concepts") if isinstance(payload.get("concepts"), list) else []
    lines.extend(["## 概念与示例", ""])
    if concepts:
        for item in concepts:
            if not isinstance(item, dict):
                continue
            title = str(item.get("item") or "").strip()
            clock = str(item.get("clock") or "").strip()
            quote = str(item.get("quote") or "").strip()
            note = str(item.get("note") or "").strip()
            head = f"- **{title}**"
            if clock:
                head += f"（[{clock}]）"
            lines.append(head)
            if quote:
                lines.append(f"  - 摘句：{quote}")
            if note:
                lines.append(f"  - {note}")
        lines.append("")
    else:
        lines.append("- （无单独条目。）")
        lines.append("")
    suspects = payload.get("asr_suspects") if isinstance(payload.get("asr_suspects"), list) else []
    lines.extend(["## 疑似 ASR", ""])
    if suspects:
        for item in suspects:
            if not isinstance(item, dict):
                continue
            heard = str(item.get("heard") or "").strip()
            likely = str(item.get("likely") or "").strip()
            clock = str(item.get("clock") or "").strip()
            piece = heard
            if likely:
                piece += f" → {likely}"
            if clock:
                piece += f"（[{clock}]）"
            lines.append(f"- {piece}。稿上原词保留；不要当成老师合格线问题。")
        lines.append("")
    else:
        lines.append("- （模型未标出。）")
        lines.append("")
    return "\n".join(lines)


def write_review(
    punct_json_path: Path,
    type_json_path: Path,
    run_dir: Path,
    stem: str,
    *,
    source_name: str,
    complete: JsonComplete | None = None,
) -> ReviewResult:
    try:
        punct = json.loads(punct_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"建议报告失败：无法读取标点稿 {punct_json_path.name}") from exc
    try:
        type_payload = json.loads(type_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"建议报告失败：无法读取课型判定 {type_json_path.name}") from exc
    if not isinstance(type_payload, dict):
        raise ReviewError("建议报告失败：课型判定不是 JSON 对象。")

    segments = list(punct.get("segments") or [])
    system, prompt_version = load_review_prompt()
    user = json.dumps(
        _build_user_payload(source_name=source_name, type_payload=type_payload, segments=segments),
        ensure_ascii=False,
        indent=2,
    )
    model = llm_model()
    try:
        if complete is None:
            raw = chat_json(system=system, user=user, timeout=REVIEW_TIMEOUT)
        else:
            raw = complete(system=system, user=user)
    except LlmConfigError:
        raise
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        raise ReviewError(detail if "失败" in detail else f"建议报告失败：{detail}") from exc
    if not isinstance(raw, dict):
        raise ReviewError("建议报告失败：模型返回不是 JSON 对象。")

    lesson_type = normalize_lesson_type(str(type_payload.get("lesson_type") or raw.get("lesson_type") or ""))
    structure_raw = raw.get("structure") if isinstance(raw.get("structure"), dict) else {}
    parsed: dict[str, Any] = {
        "lesson_type": lesson_type,
        "ruler": str(raw.get("ruler") or type_payload.get("ruler") or "").strip(),
        "duration": format_clock(duration_seconds(segments)),
        "delivery": without_blackboard(str(raw.get("delivery") or type_payload.get("delivery") or "").strip()),
        "coverage": without_blackboard(str(raw.get("coverage") or "").strip()),
        "summary": without_blackboard(str(raw.get("summary") or "").strip()),
        "structure": {
            "modules": normalize_modules(structure_raw.get("modules") if isinstance(structure_raw, dict) else []),
            "why": without_blackboard(str(structure_raw.get("why") or "").strip()) if isinstance(structure_raw, dict) else "",
            "what": without_blackboard(str(structure_raw.get("what") or "").strip()) if isinstance(structure_raw, dict) else "",
            "how": without_blackboard(str(structure_raw.get("how") or "").strip()) if isinstance(structure_raw, dict) else "",
            "structure_note": (
                without_blackboard(str(structure_raw.get("structure_note") or "").strip())
                if isinstance(structure_raw, dict)
                else ""
            ),
        },
        "must_fix": keep_cited(raw.get("must_fix")),
        "nice_to_have": normalize_notes(raw.get("nice_to_have"), note_key="suggestion"),
        "playback": _string_list(raw.get("playback")),
        "concepts": normalize_notes(raw.get("concepts"), note_key="note"),
        "asr_suspects": normalize_asr_suspects(raw.get("asr_suspects")),
        "model": model,
        "prompt_files": list(PROMPT_FILES),
        "prompt_version": prompt_version,
        "filename": source_name,
    }

    json_path = run_dir / f"{stem}.report.json"
    markdown_path = run_dir / f"{stem}.report.md"
    json_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_report_markdown(parsed), encoding="utf-8")
    return ReviewResult(
        markdown_path=markdown_path,
        json_path=json_path,
        prompt_version=prompt_version,
        model=model,
    )
