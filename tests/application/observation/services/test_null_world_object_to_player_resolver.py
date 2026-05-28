"""NullWorldObjectToPlayerResolver の振る舞いテスト。

Issue #227 chore (tile-map 依存除去) PR-1:
    PhysicalMapRepository を持たない spot_graph 専用ランタイムで使う
    NoOp resolver。任意の WorldObjectId に対して常に None を返すことを保証する。
"""

import pytest

from ai_rpg_world.application.observation.services.null_world_object_to_player_resolver import (
    NullWorldObjectToPlayerResolver,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestNullWorldObjectToPlayerResolver:
    """NullWorldObjectToPlayerResolver は常に None を返す。"""

    def test_resolve_player_id_returns_none_for_any_object_id(self) -> None:
        """任意の WorldObjectId に対して None を返す。"""
        resolver = NullWorldObjectToPlayerResolver()
        result = resolver.resolve_player_id(WorldObjectId(42))
        assert result is None

    def test_resolve_player_id_returns_none_for_different_ids(self) -> None:
        """異なる ID を順に渡しても常に None を返す (state を持たない)。"""
        resolver = NullWorldObjectToPlayerResolver()
        for oid in (1, 2, 999, 42):
            assert resolver.resolve_player_id(WorldObjectId(oid)) is None
