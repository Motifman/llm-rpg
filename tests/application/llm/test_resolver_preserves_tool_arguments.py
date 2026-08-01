"""resolver が、モデルの渡した引数を落とさないことを保証する。

## 実 run で見つかった取りこぼし

station_drill_004 で、キーパーが当番表への書き込みを 4 回試して 4 回とも
こう拒否された。

    何を書くか text パラメータで指定してください。

**モデルは 4 回とも text を渡していた。**

    {"target_label": "当番表", "action_name": "write_note",
     "parameters": {"text": "連絡通路と物資庫の照明、修理でき次第頼む。…"}}

実験経路 (presentation の dispatch → resolver → executor) では
`_resolve_interact` が `object_id` / `action_name` だけを組んだ新しい dict を
返すので、**`parameters` がそこで消えていた**。エンジンは「渡されていない」
と言い、モデルは渡している。**正しくやったのに責められる**形。

## 同じ失敗が 2 度目

`_with_inner_thought` の docstring 自身が、`say_inline` でまったく同じことが
起きたと記録している (「resolver 通過後の args から抜け落ちて executor に
届かず 100% silent failure していた」)。passthrough を手で列挙する形なので、
新しい引数が増えるたびに同じ穴が開く。

だから 1 行足すだけでなく、**tool schema が宣言した引数は resolver 通過後も
残る**ことを機械的に確かめる。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (  # noqa: E501
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    get_spot_graph_specs,
)


from ai_rpg_world.application.llm.contracts.dtos import (
    WorldObjectToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)


def _object_context() -> ToolRuntimeContextDto:
    """当番表を 1 つだけ解決できる最小の文脈。"""
    return ToolRuntimeContextDto(
        targets={
            "OBJ1": WorldObjectToolRuntimeTargetDto(
                label="OBJ1",
                kind="spot_graph_object",
                display_name="当番表",
                world_object_id=7,
            )
        }
    )


def _resolve_interact(**extra):
    args = {
        "target_label": "当番表",
        "action_name": "write_note",
        "inner_thought": "書き残しておく",
        **extra,
    }
    return SpotGraphArgumentResolver().resolve_args(
        "interact", args, _object_context()
    )


class TestInteractionParametersSurvive:
    """自由入力が resolver を通り抜ける。"""

    def test_parameters_are_not_dropped(self) -> None:
        """`parameters` が消えない。

        ここが落ちると、モデルが text を渡しても「渡していない」と拒否
        される。**正しくやったのに責められる**ので、モデルは何度でも同じ
        手を繰り返す (実 run で 4 連続)。
        """
        resolved = _resolve_interact(parameters={"text": "見回り済み"})

        assert resolved.get("parameters") == {"text": "見回り済み"}

    def test_an_absent_parameters_key_stays_absent(self) -> None:
        """渡していなければ勝手に作らない。

        空 dict を足すと「指定した」と誤判定されうる。
        """
        resolved = _resolve_interact()

        assert not resolved.get("parameters")

    def test_the_canonical_keys_are_still_produced(self) -> None:
        """従来の解決結果は変わらない。

        passthrough を足したせいで canonical 側が崩れていないかを見る。
        """
        resolved = _resolve_interact(parameters={"text": "x"})

        assert resolved["object_id"] == 7
        assert resolved["action_name"] == "write_note"


class TestNoDeclaredArgumentIsSilentlyDropped:
    """tool schema が宣言した引数は、resolver 通過後も残る。

    passthrough を手で列挙する形なので、新しい引数が増えるたびに同じ穴が
    開く。`say_inline` で 1 度、`parameters` で 2 度目。3 度目を機械的に
    止める。
    """

    #: resolver が別の名前に変換するので、そのままの名前では残らない引数。
    #: **変換されること自体が仕事**なので、消えて正しい。
    _CANONICALISED = {"target_label"}

    def test_every_interact_argument_survives(self) -> None:
        """interact の宣言引数がすべて残る (変換されるものを除く)。

        落ちたら、増やした引数を `_with_inner_thought` の passthrough に
        足すか、変換されるものとして `_CANONICALISED` に足す。**どちらか
        を選ぶ**ことを強制するのが目的。
        """
        definition = next(d for d, _ in get_spot_graph_specs() if d.name == "interact")
        declared = set(definition.parameters["properties"])

        sample = {
            "target_label": "当番表",
            "action_name": "write_note",
            "inner_thought": "書き残す",
            "say_inline": "書いておくよ",
            "parameters": {"text": "見回り済み"},
        }
        # schema にあるが sample に無いものは、空でない値を仮に入れる。
        for key in declared - set(sample):
            sample[key] = "x"

        resolved = SpotGraphArgumentResolver().resolve_args(
            "interact", sample, _object_context()
        )

        dropped = sorted(declared - set(resolved) - self._CANONICALISED)
        assert not dropped, f"resolver が落とした引数: {dropped}"

    @pytest.mark.parametrize("tool_name", ["vote", "report_body", "tend_to_player"])
    def test_say_inline_survives_for_player_targeting_tools(self, tool_name) -> None:
        """対人系でも say_inline が残る。

        say_inline はこの取りこぼしで 1 度 100% 失敗している。別 resolver に
        同じ穴が開いていないかを見る。
        """

        ctx = ToolRuntimeContextDto(
            targets={
                "P1": PlayerToolRuntimeTargetDto(
                    label="P1",
                    kind="spot_graph_player",
                    display_name="モリ",
                    player_id=1,
                )
            }
        )

        resolved = SpotGraphArgumentResolver().resolve_args(
            tool_name,
            {
                "target_player_label": "モリ",
                "inner_thought": "声をかける",
                "say_inline": "そこに居るのか",
            },
            ctx,
        )

        assert resolved.get("say_inline") == "そこに居るのか"


class TestEveryExposedToolHasArgumentResolution:
    """露出している spot tool は、すべて引数解決に到達する。

    ## 分岐だけ書いて許可リストを忘れていた

    `resolve_args` は入口で `_SPOT_GRAPH_TOOLS` を見る。`vote` と
    `report_body` は dispatch 分岐を書いたのに**この集合に足し忘れて**いて、
    None を返していた。presentation 経路では `RESOLVER_DISPATCH_MISSING`
    (「設計バグ」) になり、**投票も死体の報告も必ず失敗する**。

    どの run でも誰も投票しなかったので一度も発火せず、4 本走らせても
    気付けなかった。「使われていない機能は壊れていても分からない」形。

    露出と解決は別々の場所に書くので、片方だけ足すのがいつでも起こりうる。
    """

    def test_every_label_taking_tool_reaches_resolution(self) -> None:
        """ラベル引数を取る tool は、すべて解決に到達する。

        ラベル (`OBJ1` / 表示名) は**そのターン限りの識別子**で、resolver
        しか実 ID に変換できない。到達しなければラベルのまま executor に
        届き、その呼び出しは必ず失敗する。

        落ちたら、足した tool を `_SPOT_GRAPH_TOOLS` と dispatch 分岐の
        **両方**に足す。片方だけだと本番経路で必ず失敗する。

        ラベルを取らない tool (`prepare_action` など) は resolver を通さない
        配線なので対象外。引数が足りずに例外を投げるのは正常 (解決には
        到達している)。
        """
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (  # noqa: E501
            ToolArgumentResolutionException,
        )

        ctx = _object_context()
        generic = {
            "inner_thought": "x",
            "target_label": "当番表",
            "action_name": "read_board",
        }

        unresolved = []
        for definition, _ in get_spot_graph_specs():
            if definition.name == "speak":
                continue  # speech は別経路 (spot_graph resolver の担当外)
            takes_label = any(
                k.endswith("_label") for k in definition.parameters["properties"]
            )
            if not takes_label:
                continue
            try:
                resolved = SpotGraphArgumentResolver().resolve_args(
                    definition.name, dict(generic), ctx
                )
            except ToolArgumentResolutionException:
                continue  # 解決には到達している
            if resolved is None:
                unresolved.append(definition.name)

        assert not unresolved, (
            f"引数解決に到達しない tool: {unresolved}。"
            "_SPOT_GRAPH_TOOLS と dispatch 分岐の両方に足してください"
        )
