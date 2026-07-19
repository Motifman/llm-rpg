"""SpotGraphArgumentResolver の `spot_graph_tend_to_player` 解決を検証する。

Issue #621 Phase 3b: 同 spot に倒れた仲間を介抱して revive する新 tool。

検証範囲:
- target_player_label='P2' (Player) → `target_player_id` に解決
- target_player_label='エイダ' (display_name) でも解決
- target_player_label が monster (= M1) は INVALID_TARGET_KIND
- 不在のラベルは INVALID_TARGET_LABEL
- 空ラベルは INVALID_TARGET_LABEL
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
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
)


def _make_context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "P2": PlayerToolRuntimeTargetDto(
                label="P2",
                kind="spot_graph_player",
                display_name="エイダ",
                player_id=2,
            ),
            "M1": MonsterToolRuntimeTargetDto(
                label="M1",
                kind="spot_graph_monster",
                display_name="大型カニ",
                monster_id=101,
            ),
        },
    )


class TestTendToPlayerResolverSuccess:
    def test_p2_label_target_player_id_resolved(self) -> None:
        """P2 短縮ラベルで targetplayerid に解決される。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
            {"target_player_label": "P2", "inner_thought": "助ける"},
            _make_context(),
        )
        assert result is not None
        assert result["target_player_id"] == 2
        assert result["target_display_name"] == "エイダ"
        assert result["inner_thought"] == "助ける"

    def test_display_name_resolved(self) -> None:
        """target_player_label='エイダ' でも引ける (= 旧プロンプト経路の互換)。"""
        resolver = SpotGraphArgumentResolver()
        result = resolver.resolve_args(
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
            {"target_player_label": "エイダ", "inner_thought": ""},
            _make_context(),
        )
        assert result is not None
        assert result["target_player_id"] == 2


class TestTendToPlayerResolverErrors:
    def test_monster_label_invalid_target_kind(self) -> None:
        """target_player_label='M1' (Monster) は player でないので弾く。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {"target_player_label": "M1", "inner_thought": "t"},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_KIND"

    def test_unknown_label_invalid_target_label(self) -> None:
        """未知のラベルは invalid target label。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {"target_player_label": "X99", "inner_thought": "t"},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"

    def test_empty_label_invalid_target_label(self) -> None:
        """空ラベルは invalid target label。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {"target_player_label": "", "inner_thought": "t"},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"

    def test_target_player_label_missing_invalid_target_label(self) -> None:
        """target player label 欠落は invalid target label。"""
        resolver = SpotGraphArgumentResolver()
        with pytest.raises(ToolArgumentResolutionException) as exc:
            resolver.resolve_args(
                TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                {"inner_thought": "t"},
                _make_context(),
            )
        assert exc.value.error_code == "INVALID_TARGET_LABEL"


class TestDispatch:
    def test_tend_to_player_is_dispatch_target(self) -> None:
        """resolver が新 tool を None で素通りさせていないことを保証する
        (PR #620 の attack 経路で起きた gap の同型問題を防ぐ)。"""
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            _SPOT_GRAPH_TOOLS,
        )
        assert TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER in _SPOT_GRAPH_TOOLS
