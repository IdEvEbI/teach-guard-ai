"""教学守护 AI 助手 · 命令行入口。"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer

from teach_guard import __version__
from teach_guard.inspect_run import prepare_inspect_run

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
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            help="视频或音频文件。",
        ),
    ],
    output_root: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="产物根目录，默认当前工作目录下的 output/。",
        ),
    ] = Path("output"),
) -> None:
    """为单个视频建立运行目录与清单骨架。抽轨与转写尚未实现。"""
    run_dir = prepare_inspect_run(source, output_root)
    typer.echo(f"已创建运行目录：{run_dir}")
    typer.echo(f"运行清单：{run_dir / 'manifest.json'}")
    typer.echo("后续步骤（抽轨、转写、建议）尚未实现。")
