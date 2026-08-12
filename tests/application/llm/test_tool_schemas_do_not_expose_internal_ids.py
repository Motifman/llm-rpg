"""LLM へ出すツール引数に内部 ID を露出していないことを総当たりで見張る。

## なぜこの試験が要るか

このリポジトリの方針は `docs/design_decisions.md` #3「揮発ラベル (S1 / I2 / P3) を
捨て、名前 + ordinal で対象指定する」である。エージェントが指すのは**世界の中で
見えている名前**で、内部 ID ではない。

- ID は揮発する。同じ ID が次 tick で別のものを指しうる
- ID はエージェントの語彙ではない。過去 turn のメモに ID を書いても意味を持たない
- ID は「表示されていないもの」を指定させる。推測を誘い、静かな失敗を作る

最後の点が #853 の実例だった。`prepare_action` は `action_id` を要求し、説明文は
「準備するアクション**ID**（操作対象に表示される協力アクション名）」と書いていた。
**表示されていないものを指定せよと言っていた**ので、エージェントは推測するしかなく、
しかも推測は `success=True` で返っていた。

方針は他のツールでは守られている。実測すると、露出中の 16 ツールのうち ID を
露出していたのは `prepare_action` だけだった。だから**この 1 件を直すだけでなく、
次に足す人が同じことをできない形**にする。

## 母集団

`get_spot_graph_specs()` = 実際に LLM へ出るツール定義。`tool_exposure` の判断より
手前の全量なので、シナリオが無効化していても対象になる。休眠文脈
(`quest` / `shop` / `trade`) はこの集合に入らないので対象外である。それらにも ID
露出があるが、配線するときに直す
(`docs/exception_boundary_design.md` §10-4 と同じ扱い)。

## 分類表の網羅はここで見ない

当初「露出中の全引数が ``ACTION_ARGUMENT_CLASSIFICATIONS`` に載っている」試験も
ここに書いたが、**母集団を間違えていた**。`get_spot_graph_specs()` には memo /
memory 系のツールが入らないので、正しく分類されている `memo_ids` を「露出して
いない残骸」と誤判定した。

網羅は `tests/application/llm/test_action_argument_history_projection.py` が
`create_world_runtime` の起動時検査を通して見ており、そちらが正しい母集団を持つ。
重複して書かない。

## 名前で指すとは

`interact.action_name` が手本。「『現在の状況』の対象行にある『使える操作』から、
``""`` で囲まれた値をそのまま 1 つ選んで渡す」。**プロンプトに出ている文字列を
そのまま渡させる**ので、推測の余地が無い。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

import pytest

from ai_rpg_world.application.llm.services.tool_catalog import get_spot_graph_specs

#: 「内部 ID を指している」と読める引数名。
_ID_SUFFIXES = ("_id", "_ids")

#: 説明文が ID を要求していると読める語。
_ID_WORDS = ("ID", "識別子")

#: ID を露出してよい引数と、その理由。
#:
#: **空である。** 例外を作るときは理由を書いて足すこと。理由が書けないなら、
#: それは名前で指せるはずである。
#:
#: `handle` 系 (memory ツール) は名前が `_id` で終わらないためここに来ない。
#: handle は「想起結果がその場で発行し、出力に表示されたもの」なので、表示された
#: 値をそのまま渡す形になっており方針と衝突しない。
_ALLOWED_ID_ARGUMENTS: Dict[str, str] = {}


def _tool_properties() -> List[Tuple[str, str, Dict[str, Any]]]:
    """(ツール名, 引数名, 引数スキーマ) を全ツール分そろえる。"""
    out: List[Tuple[str, str, Dict[str, Any]]] = []
    for definition, _ in get_spot_graph_specs():
        properties = (definition.parameters or {}).get("properties") or {}
        for name, schema in properties.items():
            out.append((definition.name, name, schema if isinstance(schema, dict) else {}))
    return out


_PROPERTIES = _tool_properties()
_DEFINITIONS = [d for d, _ in get_spot_graph_specs()]


class TestTheSweepActuallyReadsTheTools:
    """走査が空振りしていない。"""

    def test_tools_are_found(self) -> None:
        """露出ツールが 1 つ以上見つかる。

        `get_spot_graph_specs` の形が変わって 0 件になると、以下の総当たりは
        「対象 0 件で成功」になる。
        """
        assert _DEFINITIONS, "露出ツールが 1 つも見つかりません。"

    def test_properties_are_found(self) -> None:
        """引数が 1 つ以上見つかる。

        parameters の構造 (`properties` キー) が変わって空になると、名前の検査が
        全部素通りする。
        """
        assert _PROPERTIES, "ツール引数が 1 つも見つかりません。"

    def test_a_known_name_argument_is_seen(self) -> None:
        """手本である `interact.action_name` が母集団に含まれている。

        既知の正例が見えていることを確かめる。走査が別のものを見ていたら落ちる。
        """
        assert any(
            arg == "action_name" for _, arg, _ in _PROPERTIES
        ), f"action_name が見つかりません。走査できた引数: {sorted({a for _, a, _ in _PROPERTIES})}"


class TestNoToolArgumentIsAnInternalId:
    """引数名が内部 ID を指していない。"""

    @pytest.mark.parametrize(
        "tool_name,argument",
        [(t, a) for t, a, _ in _PROPERTIES],
        ids=[f"{t}.{a}" for t, a, _ in _PROPERTIES],
    )
    def test_the_argument_name_does_not_look_like_an_id(
        self, tool_name: str, argument: str
    ) -> None:
        """引数名が `_id` / `_ids` で終わらない。

        ID を渡させると、プロンプトに出ていないものを指定させることになる。
        `interact.action_name` のように、表示されている名前をそのまま渡させる。
        """
        if argument in _ALLOWED_ID_ARGUMENTS:
            return
        assert not argument.endswith(_ID_SUFFIXES), (
            f"{tool_name}.{argument} が内部 ID を要求しています。"
            " 表示されている名前で指せる形にしてください"
            " (design_decisions #3)。どうしても ID が必要なら"
            " _ALLOWED_ID_ARGUMENTS に理由を書いて足してください。"
        )


class TestNoToolDescriptionAsksForAnId:
    """説明文が ID を要求していない。"""

    @pytest.mark.parametrize(
        "tool_name,argument,schema",
        _PROPERTIES,
        ids=[f"{t}.{a}" for t, a, _ in _PROPERTIES],
    )
    def test_the_argument_description_does_not_mention_an_id(
        self, tool_name: str, argument: str, schema: Dict[str, Any]
    ) -> None:
        """引数の説明文に「ID」「識別子」が出ない。

        引数名を名前に変えても説明文が「ID を渡せ」と言い続けると、エージェントは
        表示に無いものを推測する。CLAUDE.md の「プロンプト本文にツール名を書くとき
        は必ず露出判断を通す」と同じ形で、**本文が方針を裏切る**経路を止める。
        """
        if argument in _ALLOWED_ID_ARGUMENTS:
            return
        description = str(schema.get("description", ""))
        found = [w for w in _ID_WORDS if w in description]

        assert not found, (
            f"{tool_name}.{argument} の説明文が {found} を要求しています: "
            f"{description!r}"
        )

    @pytest.mark.parametrize(
        "definition", _DEFINITIONS, ids=[d.name for d in _DEFINITIONS]
    )
    def test_the_tool_description_does_not_mention_an_id(self, definition: Any) -> None:
        """ツール本体の説明文にも「ID」「識別子」が出ない。"""
        description = str(definition.description or "")
        found = [w for w in _ID_WORDS if w in description]

        assert not found, f"{definition.name} の説明文が {found} を要求しています。"
