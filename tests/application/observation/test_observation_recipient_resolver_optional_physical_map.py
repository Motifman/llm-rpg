"""create_observation_recipient_resolver の physical_map_repository Optional 対応。

Issue #227 chore (tile-map 依存除去) PR-1:
    spot_graph 専用ランタイムでは physical_map_repository=None で
    factory を呼べる。その場合 NullWorldObjectToPlayerResolver が
    内部で利用され、解決は常に None になる。
"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.observation.services.null_world_object_to_player_resolver import (
    NullWorldObjectToPlayerResolver,
)
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)


class TestCreateObservationRecipientResolverWithoutPhysicalMap:
    """physical_map_repository=None で resolver を組み立てられる。"""

    def test_factory_accepts_none_physical_map_repository(self) -> None:
        """physical_map_repository=None でも factory が例外を投げず resolver を返す。"""
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(spec=PlayerStatusRepository),
            physical_map_repository=None,
        )
        assert resolver is not None

    def test_factory_uses_null_resolver_when_physical_map_is_none(self) -> None:
        """MonsterRecipientStrategy が NullWorldObjectToPlayerResolver を使う。"""
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(spec=PlayerStatusRepository),
            physical_map_repository=None,
        )
        # 内部 strategies に MonsterRecipientStrategy が含まれ、
        # その world_object_to_player_resolver が Null 実装になっていることを確認
        strategies = resolver._strategies  # type: ignore[attr-defined]
        monster_strategies = [
            s for s in strategies if type(s).__name__ == "MonsterRecipientStrategy"
        ]
        assert len(monster_strategies) == 1
        assert isinstance(
            monster_strategies[0]._world_object_to_player_resolver,  # type: ignore[attr-defined]
            NullWorldObjectToPlayerResolver,
        )
