"""本机 mlx-whisper 转写：只出带时间的原始逐字稿，不补标点、不改原词。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
DEFAULT_WHISPER_LANGUAGE = "zh"

EXIT_ASR_MISSING = 4
EXIT_TRANSCRIBE_FAILED = 5


class AsrMissingError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "未安装 mlx-whisper（转写需要本机 Apple Silicon 环境，可用 uv sync --group asr 安装）"
        )


class TranscribeError(RuntimeError):
    pass


@dataclass(frozen=True)
class TranscribeResult:
    markdown_path: Path
    json_path: Path
    model: str


def whisper_model() -> str:
    return os.environ.get("WHISPER_MODEL", DEFAULT_WHISPER_MODEL)


def whisper_language() -> str:
    return os.environ.get("WHISPER_LANGUAGE", DEFAULT_WHISPER_LANGUAGE)


def _friendly_transcribe_error(exc: BaseException) -> str:
    detail = str(exc).strip() or exc.__class__.__name__
    if "socksio" in detail.lower() or "socks proxy" in detail.lower():
        return (
            "转写失败：当前环境使用了 SOCKS 代理，但未安装 httpx 的 socks 支持。"
            "请执行 uv sync --group asr 后重试（依赖组已包含 httpx[socks]）。"
        )
    return f"转写失败：{detail}"


def format_clock(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def render_raw_markdown(
    *,
    segments: list[dict[str, Any]],
    model: str,
    language: str,
) -> str:
    lines = [
        "# 原始逐字稿（未补标点）",
        "",
        "- 引擎：mlx-whisper",
        f"- 模型：`{model}`",
        f"- 语言：{language}",
        "- 本文件保持识别原词，不在本步改写数字、型号或专名。标点是后续步骤。",
        "",
        "## 片段",
        "",
    ]
    if not segments:
        lines.append("（没有识别到片段。）")
        lines.append("")
        return "\n".join(lines)

    for item in segments:
        start = format_clock(float(item.get("start", 0)))
        end = format_clock(float(item.get("end", 0)))
        text = str(item.get("text", "")).strip()
        lines.append(f"[{start} – {end}] {text}")
        lines.append("")
    return "\n".join(lines)


def load_transcript_if_present(run_dir: Path, stem: str) -> TranscribeResult | None:
    json_path = run_dir / f"{stem}.raw.json"
    markdown_path = run_dir / f"{stem}.raw.md"
    if not json_path.is_file() or not markdown_path.is_file():
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    model = str(payload.get("model") or "unknown")
    return TranscribeResult(markdown_path=markdown_path, json_path=json_path, model=model)


def transcribe_audio(audio_path: Path, run_dir: Path, stem: str) -> TranscribeResult:
    try:
        import mlx_whisper
    except ImportError as exc:
        raise AsrMissingError() from exc

    model = whisper_model()
    language = whisper_language()
    try:
        raw = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=model,
            language=language,
            verbose=False,
        )
    except Exception as exc:  # noqa: BLE001 — 转成明确的转写失败
        raise TranscribeError(_friendly_transcribe_error(exc)) from exc

    segments = list(raw.get("segments") or [])
    payload = {
        "model": model,
        "language": raw.get("language") or language,
        "text": raw.get("text") or "",
        "segments": [
            {
                "start": float(item.get("start", 0)),
                "end": float(item.get("end", 0)),
                "text": str(item.get("text", "")),
            }
            for item in segments
        ],
    }
    json_path = run_dir / f"{stem}.raw.json"
    markdown_path = run_dir / f"{stem}.raw.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_raw_markdown(segments=payload["segments"], model=model, language=payload["language"]),
        encoding="utf-8",
    )
    return TranscribeResult(markdown_path=markdown_path, json_path=json_path, model=model)
