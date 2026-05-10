"""SpotGraphArgumentResolver の `spot_graph_attack` 解決パスを検証する。

検証範囲:
- target_label="M1" (MonsterToolRuntimeTargetDto) を `monster_id` に解決
- target_label="P1" (Player) は INVALID_TARGET_KIND で弾く
- target_label が不在のラベル ("X1") は INVALID_TARGET_LABEL で弾く
- target_label 自体が空 ("") は INVALID_TARGET_LABEL
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    MonsterToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPOT_GRAPH_ATTACK


def _make_context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "M1": MonsterToolRuntimeTargetDto(
                label="M1",
                kind="spot_graph_monster",
                display_name="灰色のオオカミ",
                monster_id=101,
            ),
            "P1": PlayerToolRuntimeTargetDto(
                label="P1",
                kind="spot_graph_player",
                display_name="勇者",
                player_id=2,
            ),
        },
    )


class TestAttackResolverSuccess:
    """正常系: M1 → monster_id 解決。"""

    def test_m1_は_monster_id_に解決される(self) -> None:
        """target_label='M1' で `monster_id=101` と表示名が返る。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            {"target_label": "M1", "inner_thought": "倒す"},
            _make_context(),
        )
        assert result is not None
        assert result["monster_id"] == 101
        assert result["target_display_name"] == "灰色のオオカミ"
        assert result["inner_thought"] == "倒す"


class TestAttackResolverErrors:
    """異常系: 不正ラベル / 不正種別 / 空ラベル。"""

    def test_player_ラベルは_invalid_target_kind(self) -> None:
        """target_label='P1' （Player）は kind 違いで弾く。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_ATTACK,
                {"target_label": "P1", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_KIND"

    def test_未知のラベルは_invalid_target_label(self) -> None:
        """存在しないラベルは label code で弾く。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_ATTACK,
                {"target_label": "X1", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"

    def test_空ラベルは_invalid_target_label(self) -> None:
        """target_label が空文字なら INVALID_TARGET_LABEL。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_ATTACK,
                {"target_label": "", "inner_thought": ""},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"
