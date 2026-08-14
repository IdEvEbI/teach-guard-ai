"""用 RapidOCR 读共屏截图，写出带时间的画面词表。不改逐字稿。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from teach_guard.screen_content import content_holds, content_tokens, same_content
from teach_guard.snapshot import INTERVAL_SECONDS, frame_clock, frame_seconds, move_to_duplicate
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
    duplicate_count: int = 0


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
        "本文件只记录共屏上认出的字，不改逐字稿，不是评课。词表按主体词去重：菜单、时钟、输入法候选不参与比较。主体未变的截图在 `snapshot/duplicate/`，供人工核对。",
        "",
    ]
    holds = payload.get("content_holds") if isinstance(payload.get("content_holds"), list) else []
    if holds:
        lines.append("## 长时间画面静止")
        lines.append("")
        for item in holds:
            if not isinstance(item, dict):
                continue
            start = str(item.get("start") or "").strip()
            end = str(item.get("end") or "").strip()
            seconds = int(item.get("seconds") or 0)
            lines.append(f"- {start} – {end}（{seconds} 秒）")
        lines.append("")
    frames = payload.get("frames") if isinstance(payload.get("frames"), list) else []
    if frames:
        lines.append("## 帧")
        lines.append("")
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
    duplicate_count = 0
    previous_tokens: frozenset[str] | None = None
    previous_empty_key: str | None = None
    last_seconds = frame_seconds(frames[-1]) if frames else 0
    try:
        for path in frames:
            texts = reader(path)
            tokens = content_tokens(texts)
            empty_key = "" if tokens else (_fingerprint(path))
            skip = False
            if previous_tokens is not None and tokens and same_content(previous_tokens, tokens):
                skip = True
            elif previous_tokens is not None and previous_tokens and not tokens:
                skip = True
            elif previous_tokens is not None and not tokens and not previous_tokens and empty_key == previous_empty_key:
                skip = True
            if skip:
                move_to_duplicate(path, run_dir)
                duplicate_count += 1
                continue
            previous_tokens = tokens
            previous_empty_key = empty_key
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

    holds = content_holds(unique, last_seconds=last_seconds)
    payload = {
        "engine": "rapidocr",
        "interval_seconds": interval,
        "frames": unique,
        "content_holds": holds,
        "duration": format_clock(float(last_seconds)) if frames else "00:00:00",
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
        duplicate_count=duplicate_count,
    )
