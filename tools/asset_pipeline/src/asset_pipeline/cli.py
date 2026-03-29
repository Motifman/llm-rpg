"""Typer CLI: grid split and horizontal merge for sprite PNGs."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from PIL import Image

from asset_pipeline.imaging import FitPolicy, ResampleMode, resize_to_frame_with_mode

app = typer.Typer(
    name="asset-pipeline",
    help=(
        "フロントエンド用スプライト素材の前処理ツールです。\n\n"
        "・split: 1枚の画像を N 行 × N 列に切り、各セルを同じ解像度の PNG に保存します。\n"
        "・merge: 同じ解像度の PNG を左から順に横結合し、1枚のスプライトシートにします。\n\n"
        "ゲーム本体とは別の依存関係です。\n"
        "・リポジトリルートから: uv run --project tools/asset_pipeline asset-pipeline …\n"
        "・または: cd tools/asset_pipeline && uv run asset-pipeline …\n"
        "（ルートで uv sync --extra rembg とするとエラーになります。プロジェクトは tools/asset_pipeline のみです。）"
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _run_rembg_on_file(path: Path) -> None:
    """Apply background removal in-place. Requires optional [rembg] extra."""
    try:
        from rembg import remove
    except ImportError as exc:
        typer.secho(
            "rembg がインストールされていません。次を実行してください:\n"
            "  uv sync --project tools/asset_pipeline --extra rembg\n"
            "  または: cd tools/asset_pipeline && uv sync --extra rembg",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1) from exc
    data = path.read_bytes()
    out = remove(data)
    path.write_bytes(out)


@app.command("split")
def split_grid(
    input_path: Annotated[
        Path,
        typer.Argument(
            help="分割元の画像ファイル（PNG/JPEG など Pillow が読める形式）。",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    rows: Annotated[
        int,
        typer.Option(
            "--rows",
            "-r",
            help="行数（横方向の分割数ではなく、上から何段か）。",
            min=1,
        ),
    ],
    cols: Annotated[
        int,
        typer.Option(
            "--cols",
            "-c",
            help="列数（左から何列か）。",
            min=1,
        ),
    ],
    out_dir: Annotated[
        Path,
        typer.Option(
            "--out-dir",
            "-o",
            help="出力先ディレクトリ（存在しなければ作成します）。",
            file_okay=False,
            resolve_path=True,
        ),
    ],
    prefix: Annotated[
        str,
        typer.Option(
            "--prefix",
            "-p",
            help="出力ファイル名の先頭。例: hero → hero_00_00.png のように連番が付きます。",
        ),
    ] = "cell",
    width: Annotated[
        int,
        typer.Option("--width", "-W", help="各セルの出力幅（ピクセル）。", min=1),
    ] = 32,
    height: Annotated[
        int,
        typer.Option("--height", "-H", help="各セルの出力高さ（ピクセル）。", min=1),
    ] = 48,
    fit: Annotated[
        FitPolicy,
        typer.Option(
            "--fit",
            "-f",
            help=(
                "セルのアスペクト比を出力サイズに合わせる方法。"
                " contain=全体が入るよう縮小し余白は透明、"
                " cover=はみ出しを中央から切り抜き、"
                " stretch=強制伸縮。"
            ),
            case_sensitive=False,
        ),
    ] = FitPolicy.contain,
    resample: Annotated[
        ResampleMode,
        typer.Option(
            "--resample",
            help=(
                "ピクセル合成の方法。 smooth= Lanczos 等で縮小・拡大（なめらか）。"
                " majority= 各出力ピクセルに対応するソース領域内で、出現回数が最も多い色を採用"
                "（ドット絵寄りのボックス・モード）。--fit と組み合わせます。"
            ),
            case_sensitive=False,
        ),
    ] = ResampleMode.smooth,
    rembg: Annotated[
        bool,
        typer.Option(
            "--rembg",
            help=(
                "各出力 PNG に対して rembg で背景除去（アルファ）をかけます。"
                " 要: uv sync --project tools/asset_pipeline --extra rembg"
            ),
        ),
    ] = False,
    naming: Annotated[
        str,
        typer.Option(
            "--naming",
            help=(
                "ファイル名の付け方。 'rc' = {prefix}_{row}_{col}.png、"
                " 'index' = 行優先の連番 {prefix}_{i:04d}.png。"
            ),
        ),
    ] = "rc",
) -> None:
    """大きい1枚を N×M グリッドに切り、セルごとに指定サイズへ変換して保存します。

    例（リポジトリルートから）::

        uv run --project tools/asset_pipeline asset-pipeline split ./my_sheet.png -r 4 -c 4 -o ./out_cells -p hero --fit cover
        uv sync --project tools/asset_pipeline --extra rembg
        uv run --project tools/asset_pipeline asset-pipeline split sheet.png -r 3 -c 4 -o ./cells --rembg
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    naming_norm = naming.strip().lower()
    if naming_norm not in ("rc", "index"):
        typer.secho(
            "--naming には 'rc' か 'index' を指定してください。",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    src = Image.open(input_path).convert("RGBA")
    sw, sh = src.size
    cell_w = sw // cols
    cell_h = sh // rows
    if cell_w <= 0 or cell_h <= 0:
        typer.secho("画像が小さすぎて指定の行列に分割できません。", err=True, fg=typer.colors.RED)
        raise typer.Exit(code=1)

    idx = 0
    for row in range(rows):
        for col in range(cols):
            box = (col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h)
            cell = src.crop(box)
            out_img = resize_to_frame_with_mode(cell, width, height, fit, resample)

            if naming_norm == "rc":
                name = f"{prefix}_{row:02d}_{col:02d}.png"
            else:
                name = f"{prefix}_{idx:04d}.png"

            out_path = out_dir / name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_img.save(out_path)
            if rembg:
                _run_rembg_on_file(out_path)
            idx += 1

    typer.secho(
        f"完了: {rows * cols} 枚を {out_dir} に保存しました"
        f"（各 {width}×{height}、fit={fit.value}、resample={resample.value}）。",
        fg=typer.colors.GREEN,
    )


@app.command("merge")
def merge_horizontal(
    image_dir: Annotated[
        Path,
        typer.Argument(
            help="結合する PNG が入っているディレクトリ（同じ解像度であること）。",
            exists=True,
            file_okay=False,
            readable=True,
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="出力するスプライトシート PNG のパス。",
            resolve_path=True,
        ),
    ],
    pattern: Annotated[
        str,
        typer.Option(
            "--pattern",
            help="ディレクトリ内で拾う glob（例: '*.png'）。",
        ),
    ] = "*.png",
    sort_names: Annotated[
        bool,
        typer.Option(
            "--sort/--no-sort",
            help="ファイル名でソートしてから左から並べます（既定: ソートする）。",
        ),
    ] = True,
) -> None:
    """同じサイズの複数 PNG を1行に横結合し、(幅×N) × 高さ の1枚にします。

    例::

        uv run --project tools/asset_pipeline asset-pipeline merge ./frames_sorted -o ./hero_walk.png --pattern '*.png'
    """
    paths = list(image_dir.glob(pattern))
    if sort_names:
        paths.sort(key=lambda p: p.name)
    if not paths:
        typer.secho(
            f"該当ファイルがありません: {image_dir!s} / pattern={pattern!r}",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    images = [Image.open(p).convert("RGBA") for p in paths]
    w0, h0 = images[0].size
    for p, im in zip(paths, images, strict=True):
        if im.size != (w0, h0):
            typer.secho(
                f"解像度が一致しません: {p.name} は {im.size}、先頭は {w0}×{h0}。",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(code=1)

    total_w = w0 * len(images)
    sheet = Image.new("RGBA", (total_w, h0), (0, 0, 0, 0))
    for i, im in enumerate(images):
        sheet.paste(im, (i * w0, 0), im)

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)
    typer.secho(
        f"完了: {len(images)} 枚を横結合 → {output} （サイズ {total_w}×{h0}）",
        fg=typer.colors.GREEN,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
