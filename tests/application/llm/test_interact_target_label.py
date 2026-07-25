"""interact の対象引数が ``target_label`` という種別中立な名前であることを保証する。

対人 interaction (docs/memory_system/interpersonal_interaction_design.md §3.3) で
interact の対象は物体だけではなくなる。``object_label`` のままだと引数名自体が
「物体しか渡せない」と広告してしまい、LLM が同席プレイヤーを対象に選べない。

この段階では**解決できるのは引き続き物体だけ**である。名前だけ先に中立化して、
対象種別の拡張を次の PR に分離する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
    INTERACT_DEFINITION,
)


class TestInteractToolSchema:
    """interact の tool schema が公開する対象引数の名前を固定する。"""

    def test_target_label_is_a_required_property(self) -> None:
        """対象は ``target_label`` という名前で必須引数として公開される。"""
        props = INTERACT_DEFINITION.parameters["properties"]
        assert "target_label" in props
        assert "target_label" in INTERACT_DEFINITION.parameters["required"]

    def test_object_label_is_gone_entirely(self) -> None:
        """旧名 ``object_label`` は schema のどこにも残っていない。

        両方を受け付ける互換層を置くと、LLM に 2 通りの書き方が見えて
        どちらが正しいのか分からなくなる。旧名は完全に消す。
        """
        props = INTERACT_DEFINITION.parameters["properties"]
        assert "object_label" not in props
        assert "object_label" not in INTERACT_DEFINITION.parameters["required"]
