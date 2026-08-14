"""单视频精查报告：现场结构、概念观察、合格线 / 水平线、言行底线、提问与留白。不打分。"""

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
from teach_guard.questions import build_questions_payload, wait_seconds_threshold
from teach_guard.transcribe import format_clock

PROMPT_FILES = (
    "system_tone.md",
    "knowledge_cases.md",
    "structure_single.md",
    "conduct.md",
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


INTERNAL_JARGON = (
    "confirm.opening",
    "confirm.terms",
    "prior_stage_short",
    "missing_must_fix",
    "not_in_this_recording",
    "wait_seconds",
)

CONDUCT_CATEGORIES = (
    ("vulgar", "低俗用语"),
    ("disparage_student", "贬低或侮辱学员"),
    ("disparage_course", "贬低学科或课程"),
    ("disparage_teacher", "贬低前面授课老师"),
)

FORCE_LABELS = {
    "design": "设计",
    "communication": "沟通",
    "expression": "表达",
}

LEARN_WHAT_LAYERS = (
    ("chain", "培养链与就业关系"),
    ("outcome", "阶段末成果"),
    ("days", "各天预期"),
)

LEARN_WHAT_STATUS = {
    "covered": "已覆盖",
    "partial": "只讲到一部分",
    "missing": "当天没有",
}

OPENING_LABELS = {
    "self_intro": "自我介绍",
    "class_norms": "班级约定",
    "today_goal": "今日目标",
}

OPENING_SHARED = {
    "prior_stage_short": "{names}已带过前一阶段，本段用短话术收束即可",
    "missing_must_fix": "{names}当天没有，需要补",
    "not_in_this_recording": "{names}这段录像没有拍到",
}

TODAY_GOAL_COVERAGE = {
    "prior_stage_short": "今日目标可用短话术点明",
    "missing_must_fix": "今日目标当天没有，需要补",
    "not_in_this_recording": "今日目标这段录像没有拍到",
}


def strip_internal_jargon(text: str) -> str:
    """报告给人读，去掉内部字段名和代号。"""
    kept: list[str] = []
    chunk = ""
    for char in without_blackboard(text):
        chunk += char
        if char in "。！？":
            piece = chunk.strip()
            if piece and not any(token in piece for token in INTERNAL_JARGON):
                kept.append(piece)
            chunk = ""
    tail = chunk.strip()
    if tail and not any(token in tail for token in INTERNAL_JARGON):
        kept.append(tail)
    return "".join(kept)


def rewrite_coverage(
    *,
    lesson_type: str,
    opening: dict[str, Any] | None,
    model_coverage: str,
) -> str:
    cleaned = strip_internal_jargon(model_coverage)
    if lesson_type != "stage_first":
        return cleaned
    cleaned = _drop_opening_sentences(cleaned)
    if not cleaned:
        cleaned = "本段覆盖了阶段第一课开场的「学什么」。"
    elif not cleaned.endswith(("。", "！", "？")):
        cleaned += "。"
    bits = _opening_coverage_bits(opening if isinstance(opening, dict) else {})
    if not bits:
        return cleaned
    return cleaned + "；".join(bits) + "。"


def _drop_opening_sentences(text: str) -> str:
    """开场三项以确认为准，去掉模型自己写的自我介绍 / 班级约定 / 今日目标句，避免重复。"""
    markers = ("自我介绍", "班级约定", "今日目标")
    kept: list[str] = []
    chunk = ""
    for char in text:
        chunk += char
        if char in "。！？":
            piece = chunk.strip()
            if piece and not any(marker in piece for marker in markers):
                kept.append(piece)
            chunk = ""
    tail = chunk.strip()
    if tail and not any(marker in tail for marker in markers):
        kept.append(tail)
    return "".join(kept)


def _opening_coverage_bits(opening: dict[str, Any]) -> list[str]:
    bits: list[str] = []
    intro = str(opening.get("self_intro") or "").strip()
    norms = str(opening.get("class_norms") or "").strip()
    if intro and intro == norms and intro in OPENING_SHARED:
        bits.append(OPENING_SHARED[intro].format(names="自我介绍和班级约定"))
    else:
        for key in ("self_intro", "class_norms"):
            choice = str(opening.get(key) or "").strip()
            template = OPENING_SHARED.get(choice)
            if template:
                bits.append(template.format(names=OPENING_LABELS[key]))
    goal = str(opening.get("today_goal") or "").strip()
    phrase = TODAY_GOAL_COVERAGE.get(goal)
    if phrase:
        bits.append(phrase)
    return bits


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
                "force": _normalize_force(str(item.get("force") or item.get("dimension") or "")),
            }
        )
    return kept


def _normalize_force(raw: str) -> str:
    text = raw.strip().lower()
    aliases = {
        "design": "design",
        "设计": "design",
        "设计力": "design",
        "communication": "communication",
        "沟通": "communication",
        "沟通力": "communication",
        "expression": "expression",
        "表达": "expression",
        "表达力": "expression",
    }
    return aliases.get(text, aliases.get(raw.strip(), ""))


def normalize_learn_what(items: Any) -> list[dict[str, str]]:
    by_layer: dict[str, dict[str, str]] = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            layer = str(item.get("layer") or "").strip()
            if layer not in {key for key, _label in LEARN_WHAT_LAYERS}:
                continue
            status = str(item.get("status") or "").strip()
            if status not in LEARN_WHAT_STATUS:
                status = "partial" if str(item.get("note") or "").strip() else ""
            by_layer[layer] = {
                "layer": layer,
                "status": status,
                "note": without_blackboard(str(item.get("note") or "").strip()),
                "clock": str(item.get("clock") or "").strip(),
                "quote": str(item.get("quote") or "").strip(),
            }
    return [
        by_layer.get(key) or {"layer": key, "status": "", "note": "", "clock": "", "quote": ""}
        for key, _label in LEARN_WHAT_LAYERS
    ]


def keep_cited_quotes(items: Any, *, title: str) -> list[dict[str, str]]:
    """言行底线必须有时间锚和摘句；类别名由程序写入。"""
    kept: list[dict[str, str]] = []
    if not isinstance(items, list):
        return kept
    for item in items:
        if not isinstance(item, dict):
            continue
        clock = str(item.get("clock") or "").strip()
        quote = str(item.get("quote") or "").strip()
        if not clock or not quote:
            continue
        kept.append(
            {
                "item": title,
                "clock": clock,
                "quote": quote,
                "fix": without_blackboard(str(item.get("fix") or item.get("suggestion") or "").strip()),
            }
        )
    return kept


def normalize_conduct(raw: Any) -> dict[str, list[dict[str, str]]]:
    data = raw if isinstance(raw, dict) else {}
    return {key: keep_cited_quotes(data.get(key), title=label) for key, label in CONDUCT_CATEGORIES}


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


def _slim_confirm(confirm: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(confirm, dict):
        return {"terms": [], "opening": {}}
    terms = confirm.get("terms") if isinstance(confirm.get("terms"), list) else []
    opening = confirm.get("opening") if isinstance(confirm.get("opening"), dict) else {}
    kept: list[dict[str, str]] = []
    for item in terms:
        if not isinstance(item, dict):
            continue
        heard = str(item.get("heard") or "").strip()
        canonical = str(item.get("canonical") or "").strip()
        if not heard:
            continue
        kept.append(
            {
                "clock": str(item.get("clock") or "").strip(),
                "heard": heard,
                "canonical": canonical,
            }
        )
    return {"terms": kept, "opening": dict(opening)}


def _build_user_payload(
    *,
    source_name: str,
    type_payload: dict[str, Any],
    segments: list[dict[str, Any]],
    confirm: dict[str, Any] | None = None,
    wait_seconds: float = 2.0,
) -> dict[str, Any]:
    lesson_type = normalize_lesson_type(str(type_payload.get("lesson_type") or ""))
    slim = _slim_confirm(confirm)
    return {
        "filename": source_name,
        "duration": format_clock(duration_seconds(segments)),
        "lesson_type": lesson_type,
        "type_label": TYPE_LABELS.get(lesson_type, lesson_type),
        "type_delivery": str(type_payload.get("delivery") or "").strip(),
        "ruler": str(type_payload.get("ruler") or "").strip(),
        "type_reasons": type_payload.get("reasons") or [],
        "transcript": compact_transcript(segments),
        "confirm": slim,
        "wait_seconds": wait_seconds,
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
    learn_what = structure.get("learn_what") if isinstance(structure, dict) else []
    if isinstance(learn_what, list) and any(isinstance(item, dict) and str(item.get("note") or item.get("status") or "").strip() for item in learn_what):
        lines.extend(["", "**「学什么」三层**", ""])
        for index, (key, label) in enumerate(LEARN_WHAT_LAYERS, start=1):
            row = next((item for item in learn_what if isinstance(item, dict) and item.get("layer") == key), {})
            status = LEARN_WHAT_STATUS.get(str(row.get("status") or ""), "")
            detail = str(row.get("note") or "").strip()
            clock = str(row.get("clock") or "").strip()
            quote = str(row.get("quote") or "").strip()
            bits = [part for part in (status, detail) if part]
            line = f"{index}. {label}：{'；'.join(bits) if bits else '（未写。）'}"
            if clock and quote:
                line += f" 摘句：[{clock}] {quote}"
            lines.append(line)
        lines.append("")
    lines.extend(["", "## 合格线（必须改）", ""])
    must_fix = payload.get("must_fix") if isinstance(payload.get("must_fix"), list) else []
    if must_fix:
        for index, item in enumerate(must_fix, start=1):
            if not isinstance(item, dict):
                continue
            force = FORCE_LABELS.get(str(item.get("force") or ""), "")
            title = str(item.get("item") or "").strip()
            head = f"（{force}）{title}" if force else title
            lines.append(f"{index}. **{head}**")
            lines.append(f"   - 摘句：[{item.get('clock')}] {item.get('quote')}")
            fix = str(item.get("fix") or "").strip()
            if fix:
                lines.append(f"   - 改法：{fix}")
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
    lines.extend(["## 言行底线", ""])
    lines.append(
        "所有课型都检查下面四类话术：低俗用语、贬低或侮辱学员、嫌弃本学科或本课程、嫌弃前面授课老师。"
        "只依据逐字稿原句。没有摘句就不写成必须改。"
    )
    lines.append("")
    conduct = payload.get("conduct") if isinstance(payload.get("conduct"), dict) else {}
    for index, (key, label) in enumerate(CONDUCT_CATEGORIES, start=1):
        raw_items = conduct.get(key) if isinstance(conduct, dict) else []
        items = raw_items if isinstance(raw_items, list) else []
        cited = [
            item
            for item in items
            if isinstance(item, dict) and str(item.get("clock") or "").strip() and str(item.get("quote") or "").strip()
        ]
        if not cited:
            lines.append(f"{index}. {label}：本段逐字稿上未发现这类话术。")
            continue
        lines.append(f"{index}. {label}：")
        for item in cited:
            lines.append(f"   - 摘句：[{item.get('clock')}] {item.get('quote')}")
            fix = str(item.get("fix") or "").strip()
            if fix:
                lines.append(f"     改法：{fix}")
    lines.append("")
    questions = payload.get("questions") if isinstance(payload.get("questions"), dict) else {}
    lines.extend(["## 提问与留白", ""])
    wait = questions.get("wait_seconds") if isinstance(questions, dict) else None
    duration = str((questions or {}).get("duration") or payload.get("duration") or "").strip()
    wait_label = _wait_seconds_label(wait)
    lines.append(
        f"本段时长 {duration or '（未知）'}。"
        "下面分开列出设问、具体提问和空问，方便对照录像。"
        "设问是老师自问自答、用来带方向，不算必须改。"
        f"具体提问之后停顿达到 {wait_label} 秒，记为给学员留出了回答时间。"
        "在共屏上写字、画图造成的停顿不算。"
        "录音里通常听不清学员回答，因此不判断课堂上有没有形成问答。"
    )
    lines.append("")
    rhetorical = questions.get("rhetorical") if isinstance(questions, dict) else []
    rhetorical_count = questions.get("rhetorical_count") if isinstance(questions, dict) else None
    lines.append(f"### 设问（{rhetorical_count if rhetorical_count is not None else len(rhetorical or [])} 次）")
    lines.append("")
    if isinstance(rhetorical, list) and rhetorical:
        for item in rhetorical:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote") or "").strip()
            clock = str(item.get("clock") or "").strip()
            if not quote:
                continue
            head = f"- [{clock}] {quote}" if clock else f"- {quote}"
            ending = "" if quote.endswith(("。", "？", "!", "！", "?", "…")) else "。"
            lines.append(f"{head}{ending} 这是设问，用来带方向；老师接着自己讲了下去。")
        lines.append("")
    else:
        lines.append("本段稿上没有列出设问。")
        lines.append("")
    specific = questions.get("specific") if isinstance(questions, dict) else []
    specific_count = questions.get("specific_count") if isinstance(questions, dict) else None
    lines.append(f"### 具体提问（{specific_count if specific_count is not None else len(specific or [])} 次）")
    lines.append("")
    if isinstance(specific, list) and specific:
        for item in specific:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote") or "").strip()
            clock = str(item.get("clock") or "").strip()
            if not quote:
                continue
            waited = bool(item.get("waited"))
            gap = item.get("gap_after")
            wait_note = (
                "提问之后有停顿，给学员留出了回答时间"
                if waited
                else "提问之后几乎没有停顿"
            )
            if gap is not None and gap != "":
                wait_note += f"（间隔 {gap} 秒）"
            head = f"- [{clock}] {quote}" if clock else f"- {quote}"
            ending = "" if quote.endswith(("。", "？", "!", "！", "?", "…")) else "。"
            lines.append(f"{head}{ending} {wait_note}。")
        lines.append("")
    else:
        lines.append("本段稿上没有列出具体提问。")
        lines.append("")
    empty = questions.get("empty") if isinstance(questions, dict) else []
    empty_freq = str((questions or {}).get("empty_frequency") or "").strip()
    lines.append(f"### 空问（{empty_freq or '0 次'}）")
    lines.append("")
    if isinstance(empty, list) and empty:
        for item in empty:
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote") or "").strip()
            clock = str(item.get("clock") or "").strip()
            if not quote:
                continue
            head = f"- [{clock}] {quote}" if clock else f"- {quote}"
            lines.append(head)
        lines.append("")
    else:
        lines.append("本段稿上没有列出空问。")
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
    return "\n".join(lines)


def _wait_seconds_label(wait: Any) -> str:
    if wait is None or wait == "":
        return "2"
    try:
        value = float(wait)
    except (TypeError, ValueError):
        return str(wait)
    if value.is_integer():
        return str(int(value))
    return str(wait)


def write_review(
    transcript_json_path: Path,
    type_json_path: Path,
    run_dir: Path,
    stem: str,
    *,
    source_name: str,
    confirm_json_path: Path | None = None,
    wait_seconds: float | None = None,
    complete: JsonComplete | None = None,
) -> ReviewResult:
    try:
        punct = json.loads(transcript_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"建议报告失败：无法读取逐字稿 {transcript_json_path.name}") from exc
    try:
        type_payload = json.loads(type_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewError(f"建议报告失败：无法读取课型判定 {type_json_path.name}") from exc
    if not isinstance(type_payload, dict):
        raise ReviewError("建议报告失败：课型判定不是 JSON 对象。")

    confirm: dict[str, Any] | None = None
    if confirm_json_path is not None and confirm_json_path.is_file():
        try:
            loaded = json.loads(confirm_json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            confirm = loaded

    segments = list(punct.get("segments") or [])
    threshold = wait_seconds_threshold(wait_seconds)
    system, prompt_version = load_review_prompt()
    user = json.dumps(
        _build_user_payload(
            source_name=source_name,
            type_payload=type_payload,
            segments=segments,
            confirm=confirm,
            wait_seconds=threshold,
        ),
        ensure_ascii=False,
        indent=2,
    )
    model = llm_model()
    try:
        if complete is None:
            raw = chat_json(system=system, user=user, timeout=REVIEW_TIMEOUT, max_tokens=8192)
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
        "coverage": rewrite_coverage(
            lesson_type=lesson_type,
            opening=_slim_confirm(confirm)["opening"],
            model_coverage=str(raw.get("coverage") or "").strip(),
        ),
        "summary": strip_internal_jargon(str(raw.get("summary") or "").strip()),
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
            "learn_what": normalize_learn_what(
                structure_raw.get("learn_what") if isinstance(structure_raw, dict) else []
            ),
        },
        "must_fix": keep_cited(raw.get("must_fix")),
        "nice_to_have": normalize_notes(raw.get("nice_to_have"), note_key="suggestion"),
        "concepts": normalize_notes(raw.get("concepts"), note_key="note"),
        "questions": build_questions_payload(segments, raw, threshold=threshold),
        "conduct": normalize_conduct(raw.get("conduct")),
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
