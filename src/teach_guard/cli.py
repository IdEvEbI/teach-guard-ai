"""教学守护 AI 助手 · 命令行入口。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer

from teach_guard import __version__
from teach_guard.extract import (
    EXIT_EXTRACT_FAILED,
    EXIT_FFMPEG_MISSING,
    ExtractError,
    FfmpegMissingError,
    extract_audio,
)
from teach_guard.inspect_run import mark_step, prepare_inspect_run, set_artifact
from teach_guard.paths import DEFAULT_INPUT_DIR, DEFAULT_OUTPUT_DIR, get_output_dir, resolve_input_file

app = typer.Typer(
    no_args_is_help=True,
    help="教学守护 AI 助手：检查授课视频并生成报告。",
)


@app.command()
def version() -> None:
    """打印版本号。"""
    typer.echo(__version__)


@app.command()
def check() -> None:
    """检查本机是否具备后续流水线所需的基础环境。"""
    python_ok = sys.version_info >= (3, 12)
    ffmpeg_path = shutil.which("ffmpeg")

    typer.echo(f"Python {sys.version.split()[0]} （要求 >= 3.12）：{'通过' if python_ok else '未通过'}")
    typer.echo(
        f"ffmpeg：{'已找到 ' + ffmpeg_path if ffmpeg_path else '未找到（单视频抽轨时需要，可用 brew install ffmpeg 安装）'}"
    )

    if not python_ok:
        raise typer.Exit(code=1)


@app.command()
def inspect(
    source: Annotated[
        Path,
        typer.Argument(
            help=f"视频或音频文件。相对路径会先看当前目录，再看 {DEFAULT_INPUT_DIR}/。",
        ),
    ],
    output_root: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help=f"产物根目录，默认 {DEFAULT_OUTPUT_DIR}/。",
        ),
    ] = None,
) -> None:
    """为单个视频抽音轨并写入运行清单。转写与建议尚未实现。"""
    try:
        resolved = resolve_input_file(source)
    except FileNotFoundError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    run_dir = prepare_inspect_run(resolved, output_root or get_output_dir())
    typer.echo(f"已创建运行目录：{run_dir}")
    typer.echo(f"运行清单：{run_dir / 'manifest.json'}")
    typer.echo("正在抽轨…")

    try:
        extracted = extract_audio(resolved, run_dir)
    except FfmpegMissingError as exc:
        mark_step(run_dir, "extract_audio", "failed", error=str(exc))
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_FFMPEG_MISSING) from exc
    except ExtractError as exc:
        mark_step(run_dir, "extract_audio", "failed", error=str(exc))
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=EXIT_EXTRACT_FAILED) from exc

    set_artifact(run_dir, "audio", extracted.audio_path)
    mark_step(run_dir, "extract_audio", "skipped" if extracted.skipped else "done")
    if extracted.skipped:
        typer.echo(f"输入已是音频，已跳过抽轨：{extracted.audio_path}")
    else:
        typer.echo(f"已抽出音轨：{extracted.audio_path}")
    typer.echo("后续步骤（转写、建议）尚未实现。")
