"""観測の組み立てはタイルの保存先を受け取らず、物体の解決は常に未解決になる。"""

from unittest.mock import MagicMock

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
    """タイルの保存先を渡さない場合 で resolver を組み立てられる。"""

    def test_factory_builds_without_tile_repositories(self) -> None:
        """タイルの保存先を渡さない場合 でも factory が例外を投げず resolver を返す。"""
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(spec=PlayerStatusRepository),
        )
        assert resolver is not None

    def test_factory_uses_null_object_resolver(self) -> None:
        """MonsterRecipientStrategy が NullWorldObjectToPlayerResolver を使う。"""
        resolver = create_observation_recipient_resolver(
            player_status_repository=MagicMock(spec=PlayerStatusRepository),
        )
        # 内部 strategies に MonsterRecipientStrategy が含まれ、
        # その world_object_to_player_resolver が Null 実装になっていることを確認
        strategies = resolver._strategies  # type: ignore[attr-defined]
        monster_strategies = [s for s in strategies if type(s).__name__ == "MonsterRecipientStrategy"]
        assert len(monster_strategies) == 1
        assert isinstance(
            monster_strategies[0]._world_object_to_player_resolver,  # type: ignore[attr-defined]
            NullWorldObjectToPlayerResolver,
        )
