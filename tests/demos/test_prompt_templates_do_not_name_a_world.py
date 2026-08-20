"""プロンプトのテンプレートが、特定の世界の固有名詞を含まないことを見張る。

## なぜこの試験が要るか

長期記憶 (L5) を作らせるテンプレートに、漂流島シナリオ時代の文言が残っていた。

    "world_view": "この島について 2-3 文で (narrative voice)"

市場町の run で **long summary 9 件すべてに「島」が出現**し、その出力は
【自己像と世界観】として**毎ターンのプロンプトに注入**されていた。エージェントは
市場町にいながら「ここは島だ」と読まされ続けたことになる。

シナリオにも system prompt にも「島」は 1 件も無いので、**世界を汚染している
のはテンプレートだけ**。しかも long summary が発火する長い run でしか現れない
ため、これまで見えていなかった。

## この試験が保証しないこと

**網羅ではない。** ここで見るのは既知の固有名詞の一覧で、新しいシナリオの固有名詞は
自動では増えない。「テンプレートに世界の名前を書かない」という規則そのものを
機械で証明することはできない。**過去に一度混入した語が戻ってこないことだけ**を
保証する仕掛けとして置く。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Iterator, Tuple

import pytest

_PROMPT_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src" / "ai_rpg_world" / "application" / "llm"
)

#: 過去にテンプレートへ混入した / しやすい、特定の世界に属する語。
#: **網羅ではない** (上の docstring 参照)。
_WORLD_SPECIFIC_WORDS = ("島", "遭難", "漂流", "無人島", "救助隊")

#: プロンプト本文を持つ定数の名前に共通する部分。
_PROMPT_NAME_HINTS = ("PROMPT", "TEMPLATE", "INSTRUCTION")


def _prompt_constants() -> Iterator[Tuple[Path, str, str]]:
    """`application/llm` 配下の、プロンプト本文とみられる定数を列挙する。"""
    for path in sorted(_PROMPT_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - 構文エラーは別の試験の責務
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not isinstance(node.value, ast.Constant):
                continue
            if not isinstance(node.value.value, str):
                continue
            for target in node.targets:
                name = getattr(target, "id", "")
                if any(hint in name.upper() for hint in _PROMPT_NAME_HINTS):
                    yield path, name, node.value.value


class TestNoTemplateNamesAParticularWorld:
    """どのプロンプト定数にも、特定の世界の固有名詞が入っていない。"""

    def test_the_scan_actually_finds_prompts(self) -> None:
        """まず、走査対象の定数が存在する (**空を全数一致と読まない**)。

        この対照が無いと、走査の条件が壊れて 0 件になったときに、下の検査が
        「どこにも混入していない」と嘘をつく。
        """
        assert len(list(_prompt_constants())) >= 3

    @pytest.mark.parametrize("word", _WORLD_SPECIFIC_WORDS)
    def test_no_prompt_constant_mentions_it(self, word: str) -> None:
        """特定の世界の語が、プロンプト本文に現れない。

        テンプレートは全シナリオで共有される。**そこに書かれた世界は、
        別の世界の run でも読まされる。**
        """
        offenders = [
            f"{path.name}:{name}"
            for path, name, text in _prompt_constants()
            if word in text
        ]

        assert offenders == []
