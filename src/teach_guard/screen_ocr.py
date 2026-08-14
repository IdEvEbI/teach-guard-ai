"""用 RapidOCR 读共屏截图，写出带时间的画面词表。不改逐字稿。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from teach_guard.snapshot import INTERVAL_SECONDS, frame_clock, frame_seconds
from teach_guard.transcribe import format_clock

EXIT_OCR_MISSING = 11
EXIT_OCR_FAILED = 12

OcrEngine = Callable[[Path], list[str]]
_ENGINE: Any = None


class OcrMissingError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("未安装 RapidOCR（画面词表需要，可用 uv sync --group ocr 安装）")


class OcrError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScreenOcrResult:
    json_path: Path
    markdown_path: Path
    frame_count: int
    engine: str


def load_screen_if_present(run_dir: Path, stem: str) -> ScreenOcrResult | None:
    json_path = run_dir / f"{stem}.screen.json"
    markdown_path = run_dir / f"{stem}.screen.md"
    if not json_path.is_file() or not markdown_path.is_file():
        return None
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    frames = payload.get("frames") if isinstance(payload, dict) else None
    count = len(frames) if isinstance(frames, list) else 0
    return ScreenOcrResult(
        json_path=json_path,
        markdown_path=markdown_path,
        frame_count=count,
        engine=str(payload.get("engine") or "rapidocr") if isinstance(payload, dict) else "rapidocr",
    )


def _fingerprint(path: Path) -> str:
    try:
        from PIL import Image
    except ImportError:
        return f"size:{path.stat().st_size}"
    with Image.open(path) as image:
        small = image.convert("L").resize((16, 16))
        pixels = list(small.getdata())
    average = sum(pixels) / max(len(pixels), 1)
    return "".join("1" if pixel > average else "0" for pixel in pixels)


def _rapidocr_engine(path: Path) -> list[str]:
    global _ENGINE
    try:
        from rapidocr import RapidOCR
    except ImportError as exc:
        raise OcrMissingError() from exc
    if _ENGINE is None:
        _ENGINE = RapidOCR()
    result = _ENGINE(str(path))
    rows: Any
    if isinstance(result, dict):
        rows = result.get("txts") or result.get("texts") or []
        if rows:
            return [str(item).strip() for item in rows if str(item).strip()]
        rows = result.get("result") or []
    elif hasattr(result, "txts"):
        rows = getattr(result, "txts") or []
        return [str(item).strip() for item in rows if str(item).strip()]
    else:
        rows = result
    texts: list[str] = []
    if not isinstance(rows, list):
        return texts
    for item in rows:
        if isinstance(item, str) and item.strip():
            texts.append(item.strip())
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            text = str(item[1]).strip()
            if text:
                texts.append(text)
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("txt") or "").strip()
            if text:
                texts.append(text)
    return texts


def render_screen_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 画面词表",
        "",
        f"- 引擎：{payload.get('engine') or 'rapidocr'}",
        f"- 间隔：{payload.get('interval_seconds') or INTERVAL_SECONDS} 秒",
        f"- 帧数：{len(payload.get('frames') or [])}",
        "",
        "本文件只记录共屏上认出的字，不改逐字稿，不是评课。",
        "",
    ]
    frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []
    if not frames:
        lines.append("（无截图或输入已是音频。）")
        lines.append("")
        return "\n".join(lines)
    for item in frames:
        if not isinstance(item, dict):
            continue
        clock = str(item.get("clock") or "").strip()
        file_name = str(item.get("file") or "").strip()
        texts = item.get("texts") if isinstance(item.get("texts"), list) else []
        joined = " / ".join(str(text).strip() for text in texts if str(text).strip()) or "（未识别到文字。）"
        lines.append(f"- [{clock}] `{file_name}`：{joined}")
    lines.append("")
    return "\n".join(lines)


def ocr_snapshots(
    frames: list[Path],
    run_dir: Path,
    stem: str,
    *,
    engine: OcrEngine | None = None,
    interval: float = INTERVAL_SECONDS,
) -> ScreenOcrResult:
    reader = engine or _rapidocr_engine
    unique: list[dict[str, Any]] = []
    seen: str | None = None
    try:
        for path in frames:
            texts = reader(path)
            fingerprint = " | ".join(texts) or _fingerprint(path)
            if fingerprint == seen:
                continue
            seen = fingerprint
            unique.append(
                {
                    "clock": frame_clock(path),
                    "seconds": frame_seconds(path),
                    "file": f"snapshot/{path.name}",
                    "texts": texts,
                }
            )
    except OcrMissingError:
        raise
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).strip() or exc.__class__.__name__
        raise OcrError(detail if "失败" in detail else f"画面识别失败：{detail}") from exc

    payload = {
        "engine": "rapidocr",
        "interval_seconds": interval,
        "frames": unique,
        "duration": format_clock(float(unique[-1]["seconds"])) if unique else "00:00:00",
    }
    json_path = run_dir / f"{stem}.screen.json"
    markdown_path = run_dir / f"{stem}.screen.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_screen_markdown(payload), encoding="utf-8")
    return ScreenOcrResult(
        json_path=json_path,
        markdown_path=markdown_path,
        frame_count=len(unique),
        engine="rapidocr",
    )
