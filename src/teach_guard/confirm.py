"""把稿上疑词与开场缺口变成可逐条确认的问题，确认后再出报告。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from teach_guard.llm import LlmConfigError, chat_json, llm_model
from teach_guard.punctuate import prompts_dir
from teach_guard.review import compact_transcript, duration_seconds
from teach_guard.transcribe import format_clock

PROMPT_FILE = "confirm.md"
EXIT_CONFIRM_FAILED = 13

AskFn = Callable[[str], str]
JsonComplete = Callable[..., dict[str, Any]]

OPENING_FIELDS = (
    ("self_intro", "自我介绍"),
    ("class_norms", "班级约定"),
    ("today_goal", "今日目标"),
)

OPENING_CHOICES = {
    "1": "missing_must_fix",
    "2": "prior_stage_short",
    "3": "not_in_this_recording",
}

OPENING_LABELS = {
    "missing_must_fix": "当天没有，需要补",
    "prior_stage_short": "已带过前一阶段，用短话术即可",
    "not_in_this_recording": "有，但这段录像没截到",
}


class ConfirmError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConfirmResult:
    json_path: Path
    markdown_path: Path
    auto: bool
    prompt_version: str
    model: str


def _prompt_version(text: str) -> str:
    version = "v0.1"
    for line in text.splitlines():
        if line.startswith("- **版本**："):
            version = line.split("：", 1)[1].strip()
            break
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    return f"{version}+{digest}"


def load_confirm_prompt() -> tuple[str, str]:
    path = prompts_dir() / PROMPT_FILE
    if not path.is_file():
        path = Path.cwd() / "prompts" / PROMPT_FILE
    if not path.is_file():
        raise ConfirmError(f"找不到确认提示词：{PROMPT_FILE}")
    text = path.read_text(encoding="utf-8")
    return text, _prompt_version(text)


def load_confirm_if_present(run_dir: Path, stem: str) -> ConfirmResult | None:
    json_path = run_dir / f"{stem}.confirm.json"
    markdown_path = run_dir / f"{stem}.confirm.md"
    if not json_path.is_file() or not markdown_path.is_file():
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return ConfirmResult(
        json_path=json_path,
        markdown_path=markdown_path,
        auto=bool(payload.get("auto")),
        prompt_version=str(payload.get("prompt_version") or "unknown"),
        model=str(payload.get("model") or "unknown"),
    )


def render_confirm_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 确认记录",
        "",
        f"- 方式：{'非交互（--yes）' if payload.get('auto') else 'CLI 逐条确认'}",
        f"- 模型：`{payload.get('model') or ''}`",
        "",
        "## 专名",
        "",
    ]
    terms = payload.get("terms") if isinstance(payload.get("terms"), list) else []
    if terms:
        for item in terms:
            if not isinstance(item, dict):
                continue
            clock = str(item.get("clock") or "").strip()
            heard = str(item.get("heard") or "").strip()
            canonical = str(item.get("canonical") or "").strip()
            lines.append(f"- [{clock}] 稿上「{heard}」→ 确认为「{canonical}」")
    else:
        lines.append("- （无。）")
    lines.append("")
    opening = payload.get("opening") if isinstance(payload.get("opening"), dict) else {}
    if opening:
        lines.extend(["## 开场三项", ""])
        for key, label in OPENING_FIELDS:
            choice = str(opening.get(key) or "").strip()
            lines.append(f"- {label}：{OPENING_LABELS.get(choice, choice or '（未问）')}")
        lines.append("")
    return "\n".join(lines)


def _screen_excerpt(screen: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(screen, dict):
        return []
    frames = screen.get("frames") if isinstance(screen.get("frames"), list) else []
    excerpt: list[dict[str, Any]] = []
    for item in frames:
        if not isinstance(item, dict):
            continue
        texts = [str(text).strip() for text in (item.get("texts") or []) if str(text).strip()]
        if not texts:
            continue
        excerpt.append({"clock": item.get("clock"), "file": item.get("file"), "texts": texts[:12]})
    return excerpt


def draft_confirm(
    *,
    source_name: str,
    lesson_type: str,
    segments: list[dict[str, Any]],
    screen: dict[str, Any] | None,
    complete: JsonComplete | None = None,
) -> dict[str, Any]:
    system, prompt_version = load_confirm_prompt()
    user = json.dumps(
        {
            "filename": source_name,
            "lesson_type": lesson_type,
            "duration": format_clock(duration_seconds(segments)),
            "transcript": compact_transcript(segments),
            "screen": _screen_excerpt(screen),
        },
        ensure_ascii=False,
        indent=2,
    )
    completer = complete or chat_json
    try:
        raw = completer(system=system, user=user)
    except LlmConfigError:
        raise
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        raise ConfirmError(detail if "失败" in detail else f"确认草稿失败：{detail}") from exc
    if not isinstance(raw, dict):
        raise ConfirmError("确认草稿失败：模型返回不是 JSON 对象。")
    terms: list[dict[str, str]] = []
    for item in raw.get("terms") or []:
        if not isinstance(item, dict):
            continue
        heard = str(item.get("heard") or "").strip()
        if not heard:
            continue
        terms.append(
            {
                "clock": str(item.get("clock") or "").strip(),
                "heard": heard,
                "screen": str(item.get("screen") or "").strip(),
                "snapshot": str(item.get("snapshot") or "").strip(),
            }
        )
    opening_needed = [str(item).strip() for item in (raw.get("opening_needed") or []) if str(item).strip()]
    return {"terms": terms, "opening_needed": opening_needed, "prompt_version": prompt_version}


def _ask_term(item: dict[str, str], ask: AskFn) -> dict[str, str]:
    screen = item.get("screen") or ""
    default = screen or item["heard"]
    hint = f"画面：{screen}" if screen else "画面未读到对应词"
    snapshot = f" 截图 {item['snapshot']}" if item.get("snapshot") else ""
    prompt = (
        f"[{item.get('clock') or '？'}] 稿上是「{item['heard']}」。{hint}{snapshot}。\n"
        f"确认后的写法（直接回车则用「{default}」）："
    )
    answer = ask(prompt).strip() or default
    return {
        "clock": item.get("clock") or "",
        "heard": item["heard"],
        "canonical": answer,
        "source": "screen" if answer == screen else "user",
    }


def _ask_opening(field_key: str, label: str, ask: AskFn) -> str:
    prompt = (
        f"本段稿上没有「{label}」。当天是？\n"
        "1. 确实没有，需要补（合格线）\n"
        "2. 老师已带过前一阶段，用短话术即可\n"
        "3. 有，但这段录像没截到\n"
        "请输入 1 / 2 / 3："
    )
    while True:
        answer = ask(prompt).strip() or "1"
        if answer in OPENING_CHOICES:
            return OPENING_CHOICES[answer]
        prompt = "请输入 1、2 或 3："


def apply_confirm_answers(
    draft: dict[str, Any],
    *,
    lesson_type: str,
    auto: bool,
    ask: AskFn | None = None,
) -> dict[str, Any]:
    terms: list[dict[str, str]] = []
    for item in draft.get("terms") or []:
        if not isinstance(item, dict):
            continue
        if auto or ask is None:
            canonical = str(item.get("screen") or item.get("heard") or "").strip()
            terms.append(
                {
                    "clock": str(item.get("clock") or ""),
                    "heard": str(item.get("heard") or ""),
                    "canonical": canonical,
                    "source": "screen" if item.get("screen") else "auto",
                }
            )
        else:
            terms.append(_ask_term(item, ask))

    opening: dict[str, str] = {}
    if lesson_type == "stage_first":
        needed = {str(item) for item in (draft.get("opening_needed") or [])}
        for key, label in OPENING_FIELDS:
            if needed and key not in needed:
                continue
            if auto or ask is None:
                opening[key] = "missing_must_fix"
            else:
                opening[key] = _ask_opening(key, label, ask)
    return {"terms": terms, "opening": opening}


def write_confirm(
    run_dir: Path,
    stem: str,
    *,
    source_name: str,
    lesson_type: str,
    segments: list[dict[str, Any]],
    screen: dict[str, Any] | None,
    auto: bool,
    ask: AskFn | None = None,
    complete: JsonComplete | None = None,
) -> ConfirmResult:
    draft = draft_confirm(
        source_name=source_name,
        lesson_type=lesson_type,
        segments=segments,
        screen=screen,
        complete=complete,
    )
    answers = apply_confirm_answers(draft, lesson_type=lesson_type, auto=auto, ask=ask)
    payload = {
        "auto": auto,
        "lesson_type": lesson_type,
        "filename": source_name,
        "terms": answers["terms"],
        "opening": answers["opening"],
        "model": "stub" if complete is not None else llm_model(),
        "prompt": PROMPT_FILE,
        "prompt_version": draft["prompt_version"],
    }
    json_path = run_dir / f"{stem}.confirm.json"
    markdown_path = run_dir / f"{stem}.confirm.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_confirm_markdown(payload), encoding="utf-8")
    return ConfirmResult(
        json_path=json_path,
        markdown_path=markdown_path,
        auto=auto,
        prompt_version=str(payload["prompt_version"]),
        model=str(payload["model"]),
    )
