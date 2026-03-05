"""観測配信先をイベントから解決する実装（戦略パターン）"""

from typing import Any, List, Sequence, Set

from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationRecipientResolver,
    IRecipientResolutionStrategy,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.application.observation.services.world_object_to_player_resolver import (
    WorldObjectToPlayerResolver,
)
from ai_rpg_world.application.observation.services.recipient_strategies import (
    DefaultRecipientStrategy,
)


class ObservationRecipientResolver(IObservationRecipientResolver):
    """
    ドメインイベントから観測の配信先プレイヤーID一覧を解決する。
    登録された戦略のうち、supports(event) が True の先頭戦略に委譲し、
    返却リストの重複を除去して返す。
    """

    def __init__(
        self,
        strategies: Sequence[IRecipientResolutionStrategy],
    ) -> None:
        self._strategies = list(strategies)

    def resolve(self, event: Any) -> List[PlayerId]:
        """イベント種別に応じて配信先を返す。観測対象外または未知のイベントは空リスト。"""
        for strategy in self._strategies:
            if strategy.supports(event):
                raw = strategy.resolve(event)
                return self._deduplicate(raw)
        return []

    def _deduplicate(self, player_ids: List[PlayerId]) -> List[PlayerId]:
        """順序を保ちつつ重複を除去する。"""
        seen: Set[int] = set()
        result: List[PlayerId] = []
        for pid in player_ids:
            if pid.value in seen:
                continue
            seen.add(pid.value)
            result.append(pid)
        return result


def create_observation_recipient_resolver(
    player_status_repository: PlayerStatusRepository,
    physical_map_repository: PhysicalMapRepository,
) -> IObservationRecipientResolver:
    """
    既存と同様の振る舞いになる Resolver を組み立てる。
    デフォルト戦略と WorldObjectToPlayerResolver を用いる。
    """
    world_object_resolver = WorldObjectToPlayerResolver(physical_map_repository)
    default_strategy = DefaultRecipientStrategy(
        player_status_repository=player_status_repository,
        world_object_to_player_resolver=world_object_resolver,
    )
    return ObservationRecipientResolver(strategies=[default_strategy])
