"""识别单视频主类型；阶段第一课开场不是简介类。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from teach_guard.llm import LlmConfigError, chat_json, llm_model
from teach_guard.punctuate import prompts_dir
from teach_guard.transcribe import format_clock

PROMPT_FILE = "pedagogy_type.md"
EXIT_LESSON_TYPE_FAILED = 8
HEAD_SECONDS = 120.0

LESSON_TYPES = (
    "intro",
    "practice",
    "syntax",
    "case",
    "principle",
    "project",
    "stage_first",
    "other",
)

TYPE_LABELS = {
    "intro": "简介类",
    "practice": "实操类",
    "syntax": "代码语法类",
    "case": "案例类",
    "principle": "原理类",
    "project": "项目类",
    "stage_first": "阶段第一课开场",
    "other": "无法判定",
}

RULER_BY_TYPE = {
    "intro": "005",
    "practice": "006",
    "syntax": "007",
    "case": "008",
    "principle": "009",
    "project": "010",
    "stage_first": "004",
    "other": "",
}

JsonComplete = Callable[..., dict[str, Any]]


class LessonTypeError(RuntimeError):
    pass


@dataclass(frozen=True)
class LessonTypeResult:
    markdown_path: Path
    json_path: Path
    lesson_type: str
    prompt_version: str
    model: str
    overridden: bool


def load_type_prompt() -> tuple[str, str]:
    path = prompts_dir() / PROMPT_FILE
    if not path.is_file():
        path = Path.cwd() / "prompts" / PROMPT_FILE
    if not path.is_file():
        raise LessonTypeError(f"找不到课型提示词：{PROMPT_FILE}")
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    version = "v0.1"
    for line in text.splitlines():
        if line.startswith("- **版本**："):
            version = line.split("：", 1)[1].strip()
            break
    return text, f"{version}+{digest}"


TYPE_ALIASES = {
    "sf": "stage_first",
    "in": "intro",
    "pr": "practice",
    "sy": "syntax",
    "ca": "case",
    "pl": "principle",
    "pj": "project",
    "ot": "other",
}

TYPE_HELP = (
    "覆盖课型。短名：sf=stage_first，in=intro，pr=practice，sy=syntax，"
    "ca=case，pl=principle，pj=project，ot=other。也可用全名。"
)


def normalize_lesson_type(value: str | None) -> str:
    key = (value or "").strip().lower().replace("-", "_")
    key = TYPE_ALIASES.get(key, key)
    if key not in LESSON_TYPES:
        return "other"
    return key


def parse_cli_lesson_type(value: str) -> str:
    key = value.strip().lower().replace("-", "_")
    key = TYPE_ALIASES.get(key, key)
    if key not in LESSON_TYPES:
        allowed = "、".join(f"{short}={full}" for short, full in TYPE_ALIASES.items())
        raise ValueError(f"课型必须是：{allowed}")
    return key


def head_segments(segments: list[dict[str, Any]], *, seconds: float = HEAD_SECONDS) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    for item in segments:
        start = float(item.get("start", 0))
        if chosen and start >= seconds:
            break
        chosen.append(item)
    return chosen or segments[:8]


def duration_seconds(segments: list[dict[str, Any]]) -> float:
    if not segments:
        return 0.0
    return float(segments[-1].get("end", 0))


def render_type_markdown(payload: dict[str, Any]) -> str:
    lesson_type = str(payload.get("lesson_type") or "other")
    label = TYPE_LABELS.get(lesson_type, lesson_type)
    reasons = payload.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    lines = [
        "# 课型判定",
        "",
        f"- 主类型：`{lesson_type}`（{label}）",
        f"- 置信：{payload.get('confidence') or 'low'}",
        f"- 主交付假设：{payload.get('delivery') or '（未写）'}",
        f"- 对照专文：{payload.get('ruler') or '（无）'}",
        f"- 覆盖：{'是' if payload.get('overridden') else '否'}",
        f"- 模型：`{payload.get('model') or ''}`",
        f"- 提示词：`{PROMPT_FILE}` {payload.get('prompt_version') or ''}",
        "",
        "## 依据",
        "",
    ]
    if reasons:
        for item in reasons:
            text = str(item).strip()
            if text:
                lines.append(f"- {text}")
    else:
        lines.append("- （未写依据。）")
    lines.append("")
    not_type = str(payload.get("not_type") or "").strip()
    not_reason = str(payload.get("not_reason") or "").strip()
    if not_type or not_reason:
        lines.append("## 不是什么")
        lines.append("")
        if not_type:
            lines.append(f"- 不是 `{not_type}`")
        if not_reason:
            lines.append(f"- {not_reason}")
        lines.append("")
    return "\n".join(lines)


def _build_user_payload(*, source_name: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    head = head_segments(segments)
    return {
        "filename": source_name,
        "duration": format_clock(duration_seconds(segments)),
        "head_segments": [
            {
                "start": format_clock(float(item.get("start", 0))),
                "end": format_clock(float(item.get("end", 0))),
                "text": str(item.get("text", "")),
            }
            for item in head
        ],
    }


def load_type_if_present(run_dir: Path, stem: str) -> LessonTypeResult | None:
    json_path = run_dir / f"{stem}.type.json"
    markdown_path = run_dir / f"{stem}.type.md"
    if not json_path.is_file() or not markdown_path.is_file():
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    lesson_type = normalize_lesson_type(str(payload.get("lesson_type") or ""))
    return LessonTypeResult(
        markdown_path=markdown_path,
        json_path=json_path,
        lesson_type=lesson_type,
        prompt_version=str(payload.get("prompt_version") or "unknown"),
        model=str(payload.get("model") or "unknown"),
        overridden=bool(payload.get("overridden")),
    )


def classify_lesson_type(
    punct_json_path: Path,
    run_dir: Path,
    stem: str,
    *,
    source_name: str,
    override: str | None = None,
    complete: JsonComplete | None = None,
) -> LessonTypeResult:
    try:
        punct = json.loads(punct_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LessonTypeError(f"课型识别失败：无法读取标点稿 {punct_json_path.name}") from exc

    segments = list(punct.get("segments") or [])
    system, prompt_version = load_type_prompt()
    model = "override" if override else llm_model()
    overridden = override is not None

    if override is not None:
        lesson_type = parse_cli_lesson_type(override)
        parsed: dict[str, Any] = {
            "lesson_type": lesson_type,
            "confidence": "high",
            "delivery": "（维护者命令行覆盖）",
            "ruler": RULER_BY_TYPE.get(lesson_type, ""),
            "reasons": [f"命令行 --type {lesson_type}"],
            "not_type": "",
            "not_reason": "",
        }
    else:
        user = json.dumps(_build_user_payload(source_name=source_name, segments=segments), ensure_ascii=False, indent=2)
        completer = complete or chat_json
        try:
            raw = completer(system=system, user=user)
        except LlmConfigError:
            raise
        except Exception as exc:  # noqa: BLE001
            detail = str(exc).strip() or exc.__class__.__name__
            raise LessonTypeError(detail if "失败" in detail else f"课型识别失败：{detail}") from exc
        if not isinstance(raw, dict):
            raise LessonTypeError("课型识别失败：模型返回不是 JSON 对象。")
        lesson_type = normalize_lesson_type(str(raw.get("lesson_type") or ""))
        confidence = str(raw.get("confidence") or "low").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        if lesson_type == "other":
            confidence = "low"
        parsed = {
            "lesson_type": lesson_type,
            "confidence": confidence,
            "delivery": str(raw.get("delivery") or "").strip(),
            "ruler": str(raw.get("ruler") or RULER_BY_TYPE.get(lesson_type, "")).strip(),
            "reasons": raw.get("reasons") or [],
            "not_type": str(raw.get("not_type") or "").strip(),
            "not_reason": str(raw.get("not_reason") or "").strip(),
        }

    parsed["model"] = model
    parsed["prompt"] = PROMPT_FILE
    parsed["prompt_version"] = prompt_version
    parsed["overridden"] = overridden
    parsed["filename"] = source_name

    json_path = run_dir / f"{stem}.type.json"
    markdown_path = run_dir / f"{stem}.type.md"
    json_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_type_markdown(parsed), encoding="utf-8")
    return LessonTypeResult(
        markdown_path=markdown_path,
        json_path=json_path,
        lesson_type=str(parsed["lesson_type"]),
        prompt_version=prompt_version,
        model=model,
        overridden=overridden,
    )
