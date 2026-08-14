"""追跡下のファイルに競合マーカーが残っていないことを見張る。

## なぜ要るか

PR #1123 を main へ取り込むとき、``docs/design_decisions.md`` は #1122 の
判断 #95 と #1123 の判断 #96 が**どちらも末尾へ追記した**ことで競合した。
番号の衝突ではなく位置の衝突だったので、両方を残して並べ直した。

そのとき基底マーカーの 1 行が本文に残ったまま main へ入った。

    ||||||| a4f5706c

解消スクリプトが ``<<<<<<<`` と ``=======`` と ``>>>>>>>`` の 3 つしか見て
いなかった。git の diff3 形式には**基底側を示す 4 つ目のマーカー**があり、
``<<<<<<<`` と ``=======`` の間に入る。3 つだけ検査すると、この 1 行は
「片側のブロックの中身」として素通りする。

文書に紛れた 1 行はテストも型検査も通ってしまう。**読んだ人間が気づくまで
残り続ける**ので、構造で止める。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: 検査するマーカー。リテラルを直接書くと、この試験ファイル自身が
#: 検査に引っかかる。実行時に組み立てて自己一致を避ける。
_MARKER_LENGTH = 7
_MARKER_HEADS = ("<", "|", "=", ">")

#: 中身が本文でないファイル。読み込めても検査の意味がない。
_SKIPPED_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".woff2"}
)


def _tracked_files() -> list[Path]:
    """git が追跡しているファイルだけを見る。

    ``var/runs`` の実験成果物や ``.venv`` を歩かないために ``git ls-files``
    を使う。追跡外に残ったマーカーは main を汚さないので対象にしない。
    """
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=_REPO_ROOT,
        capture_output=True,
        check=True,
    )
    names = result.stdout.decode("utf-8").split("\0")
    return [_REPO_ROOT / name for name in names if name]


def _offending_lines(text: str) -> list[str]:
    """行頭がマーカーで始まる行を返す。"""
    markers = tuple(head * _MARKER_LENGTH for head in _MARKER_HEADS)
    return [line for line in text.split("\n") if line.startswith(markers)]


class TestTrackedFilesCarryNoConflictMarkers:
    """追跡下のファイルに、解消し損ねた競合マーカーが残らないことを保証する。"""

    def test_no_tracked_file_starts_a_line_with_a_conflict_marker(self) -> None:
        """追跡下のどのファイルも、行頭が 4 種の競合マーカーで始まる行を持たない。

        4 種とは ``<`` / ``|`` / ``=`` / ``>`` を 7 個並べたもので、``|`` は
        diff3 形式の基底側マーカー。これを検査に含めないと、実際に main へ
        入った 1 行を見逃す。
        """
        found: dict[str, list[str]] = {}
        for path in _tracked_files():
            if path.suffix.lower() in _SKIPPED_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
                continue
            lines = _offending_lines(text)
            if lines:
                found[str(path.relative_to(_REPO_ROOT))] = lines
        assert not found, f"競合マーカーが残っています: {found}"

    @pytest.mark.parametrize("head", _MARKER_HEADS)
    def test_the_detector_catches_every_marker_kind(self, head: str) -> None:
        """検出器は 4 種のマーカーそれぞれを 1 つでも取りこぼさない。

        本体の試験は「見つからない」ことを主張するので、検出器が壊れていても
        緑のまま通る。4 種を個別に食わせて、検出器自体が生きていることを縛る。
        """
        sample = "本文\n" + head * _MARKER_LENGTH + " something\n本文\n"

        assert _offending_lines(sample) == [head * _MARKER_LENGTH + " something"]
