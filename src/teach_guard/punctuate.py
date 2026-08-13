"""给原始逐字稿补标点：不改词、不覆盖 raw 产物。"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from teach_guard.llm import LlmConfigError, chat_json, llm_model
from teach_guard.transcribe import format_clock

PROMPT_FILE = "punctuate.md"
EXIT_PUNCTUATE_FAILED = 7
MAX_BATCH_SECONDS = 180.0
MAX_BATCH_SEGMENTS = 60
_BATCH_RETRIES = 1


class PunctuateError(RuntimeError):
    pass


@dataclass(frozen=True)
class PunctuateResult:
    markdown_path: Path
    json_path: Path
    prompt_version: str
    model: str


JsonComplete = Callable[..., dict[str, Any]]
BatchProgress = Callable[[int, int], None]


def prompts_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "prompts"


def load_punctuate_prompt() -> tuple[str, str]:
    path = prompts_dir() / PROMPT_FILE
    if not path.is_file():
        path = Path.cwd() / "prompts" / PROMPT_FILE
    if not path.is_file():
        raise PunctuateError(f"找不到标点提示词：{PROMPT_FILE}")
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    version = "v0.1"
    for line in text.splitlines():
        if line.startswith("- **版本**："):
            version = line.split("：", 1)[1].strip()
            break
    return text, f"{version}+{digest}"


def comparable_tokens(text: str) -> str:
    """去掉空白与标点后的字符序列，用来判断模型有没有改词。"""
    return "".join(
        ch for ch in text if not ch.isspace() and not unicodedata.category(ch).startswith("P")
    )


def tokens_preserved(original: str, punctuated: str) -> bool:
    return comparable_tokens(original) == comparable_tokens(punctuated)


def chunk_segments(
    segments: list[dict[str, Any]],
    *,
    max_seconds: float = MAX_BATCH_SECONDS,
    max_count: int = MAX_BATCH_SEGMENTS,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    window_start: float | None = None
    for item in segments:
        start = float(item.get("start", 0))
        if not current:
            current = [item]
            window_start = start
            continue
        spanned = start - (window_start or start)
        if spanned >= max_seconds or len(current) >= max_count:
            batches.append(current)
            current = [item]
            window_start = start
        else:
            current.append(item)
    if current:
        batches.append(current)
    return batches


def render_punct_markdown(
    *,
    segments: list[dict[str, Any]],
    model: str,
    prompt_version: str,
) -> str:
    lines = [
        "# 标点逐字稿（不改词）",
        "",
        f"- 模型：`{model}`",
        f"- 提示词：`{PROMPT_FILE}` {prompt_version}",
        "- 本文件只补标点，不改写数字、型号、专名或工具口述。原始识别见同目录 `.raw.md`。",
        "",
        "## 片段",
        "",
    ]
    if not segments:
        lines.append("（没有片段。）")
        lines.append("")
        return "\n".join(lines)

    for item in segments:
        start = format_clock(float(item.get("start", 0)))
        end = format_clock(float(item.get("end", 0)))
        text = str(item.get("text", "")).strip()
        lines.append(f"[{start} – {end}] {text}")
        lines.append("")
    return "\n".join(lines)


def _parse_batch_texts(payload: dict[str, Any], expected: int) -> list[str | None]:
    raw_items = payload.get("segments")
    if not isinstance(raw_items, list):
        raise PunctuateError("标点失败：模型返回里没有 segments 数组。")
    by_index: dict[int, str] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item["i"])
        except (KeyError, TypeError, ValueError):
            continue
        text = item.get("text")
        if isinstance(text, str):
            by_index[index] = text
    return [by_index.get(i) for i in range(1, expected + 1)]


def _punctuate_batch(
    batch: list[dict[str, Any]],
    *,
    system: str,
    complete: JsonComplete,
) -> list[dict[str, Any]]:
    numbered = [
        {
            "i": i,
            "start": format_clock(float(item.get("start", 0))),
            "end": format_clock(float(item.get("end", 0))),
            "text": str(item.get("text", "")),
        }
        for i, item in enumerate(batch, start=1)
    ]
    user = json.dumps({"segments": numbered}, ensure_ascii=False, indent=2)
    last_error: Exception | None = None
    texts: list[str | None] | None = None
    for _ in range(_BATCH_RETRIES + 1):
        try:
            payload = complete(system=system, user=user)
            texts = _parse_batch_texts(payload, len(batch))
            break
        except LlmConfigError:
            raise
        except Exception as exc:  # noqa: BLE001 — 批次内重试一次
            last_error = exc
    if texts is None:
        detail = str(last_error).strip() if last_error else "未知错误"
        raise PunctuateError(detail if detail.startswith("调用大模型失败") else f"标点失败：{detail}")

    result: list[dict[str, Any]] = []
    for original, punctuated in zip(batch, texts, strict=True):
        source_text = str(original.get("text", ""))
        if punctuated is None or not tokens_preserved(source_text, punctuated):
            result.append(
                {
                    "start": float(original.get("start", 0)),
                    "end": float(original.get("end", 0)),
                    "text": source_text,
                    "punctuated": False,
                }
            )
        else:
            result.append(
                {
                    "start": float(original.get("start", 0)),
                    "end": float(original.get("end", 0)),
                    "text": punctuated.strip(),
                    "punctuated": True,
                }
            )
    return result


def punctuate_transcript(
    raw_json_path: Path,
    run_dir: Path,
    stem: str,
    *,
    complete: JsonComplete | None = None,
    on_batch: BatchProgress | None = None,
) -> PunctuateResult:
    try:
        payload = json.loads(raw_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PunctuateError(f"标点失败：无法读取原始逐字稿 {raw_json_path.name}") from exc

    segments = list(payload.get("segments") or [])
    system, prompt_version = load_punctuate_prompt()
    completer = complete or chat_json
    model = llm_model()
    punctuated: list[dict[str, Any]] = []
    batches = chunk_segments(segments)
    try:
        for index, batch in enumerate(batches, start=1):
            if on_batch is not None:
                on_batch(index, len(batches))
            punctuated.extend(_punctuate_batch(batch, system=system, complete=completer))
    except LlmConfigError:
        raise
    except PunctuateError:
        raise
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        raise PunctuateError(detail if "失败" in detail else f"标点失败：{detail}") from exc

    json_path = run_dir / f"{stem}.punct.json"
    markdown_path = run_dir / f"{stem}.punct.md"
    json_path.write_text(
        json.dumps(
            {
                "model": model,
                "prompt": PROMPT_FILE,
                "prompt_version": prompt_version,
                "segments": punctuated,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_punct_markdown(segments=punctuated, model=model, prompt_version=prompt_version),
        encoding="utf-8",
    )
    return PunctuateResult(
        markdown_path=markdown_path,
        json_path=json_path,
        prompt_version=prompt_version,
        model=model,
    )
