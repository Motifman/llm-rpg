from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, FrozenSet, Tuple

from ai_rpg_world.application.world_graph.movement_command_repository_provider import (
    MovementCommandRepositoryProviderPort,
)

from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionNotPassableException,
    SpotTravelAlreadyInProgressException,
    SpotTravelUnreachableException,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.service.spot_graph_navigation_service import (
    SpotGraphNavigationService,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.application.player.services.player_perception_policy import (
    PlayerPerceptionPolicy,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import CommandContext
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )


@dataclass(frozen=True)
class SpotTravelTickAdvanceDto:
    """1 ティック進行後の横断結果（観測・ログ用）。"""

    entered_spot_ids: Tuple[SpotId, ...]


class SpotGraphMovementApplicationService:
    """スポットグラフ上のプレイヤー移動（経路設定・ティック進行）。"""

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
        navigation_service: SpotGraphNavigationService | None = None,
        departed_position_store: DepartedPositionStore | None = None,
        player_perception_policy: PlayerPerceptionPolicy | None = None,
        command_scope_factory: (
            "CommandScopeFactoryPort[MovementCommandRepositoryProviderPort]" | None
        ) = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._navigation = navigation_service or SpotGraphNavigationService()
        self._departed_position_store = departed_position_store
        self._player_perception_policy = player_perception_policy
        self._command_scope_factory = command_scope_factory

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[MovementCommandRepositoryProviderPort]",
    ) -> None:
        """本番配線後の移動をcommandごとの確定境界へ載せる。"""
        self._command_scope_factory = factory

    def _is_departed(self, player_id: PlayerId) -> bool:
        return bool(
            self._player_perception_policy is not None
            and self._player_perception_policy.is_departed(player_id)
        )

    def _current_spot(
        self,
        player_id: PlayerId,
        graph: SpotGraphAggregate,
    ) -> SpotId:
        if not self._is_departed(player_id):
            return graph.get_entity_spot(self.entity_id_for_player(player_id))
        if self._departed_position_store is None:
            raise RuntimeError("departed position store is not wired")
        spot_id = self._departed_position_store.find(player_id)
        if spot_id is None:
            raise RuntimeError(f"去った主体の位置がありません: {player_id}")
        return spot_id

    @staticmethod
    def entity_id_for_player(player_id: PlayerId) -> EntityId:
        """プレイヤーとグラフ上エンティティの対応（同一の正の整数）。"""
        return EntityId.create(int(player_id))

    def move_to_sub_location(
        self,
        player_id: PlayerId,
        sub_location_id: SubLocationId | None,
    ) -> None:
        """同一スポット内のサブロケーションのみ変更する（スポット間移動中は不可）。"""
        graph = self._spot_graph_repository.find_graph()
        player = self._player_status_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found: {player_id}")
        spot_on_graph = self._current_spot(player_id, graph)
        player.ensure_spot_navigation_at_rest(spot_on_graph)
        nav = player.spot_navigation_state
        assert nav is not None
        if nav.current_spot_id != spot_on_graph:
            player.set_spot_navigation_state(
                PlayerSpotNavigationState.at_rest(spot_on_graph)
            )
        player.set_spot_sub_location(sub_location_id)
        self._player_status_repository.save(player)

    def start_travel_to_spot(
        self,
        player_id: PlayerId,
        destination_spot_id: SpotId,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> None:
        """最短経路で移動を開始する。各区間の通行条件を開始時点で検証する。"""
        if self._command_scope_factory is None:
            self._start_travel_to_spot(
                player_id,
                destination_spot_id,
                owned_item_spec_ids,
                world_flags,
                spot_graph_repository=self._spot_graph_repository,
                player_status_repository=self._player_status_repository,
            )
            return
        with self._command_scope_factory.create() as context:
            repositories = context.repositories
            self._start_travel_to_spot(
                player_id,
                destination_spot_id,
                owned_item_spec_ids,
                world_flags,
                spot_graph_repository=repositories.spot_graph,
                player_status_repository=repositories.player_statuses,
            )

    def _start_travel_to_spot(
        self,
        player_id: PlayerId,
        destination_spot_id: SpotId,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
        *,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        graph = spot_graph_repository.find_graph()
        player = player_status_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found: {player_id}")

        spot_on_graph = self._current_spot(player_id, graph)
        player.ensure_spot_navigation_at_rest(spot_on_graph)
        nav = player.spot_navigation_state
        assert nav is not None
        if nav.current_spot_id != spot_on_graph:
            player.set_spot_navigation_state(PlayerSpotNavigationState.at_rest(spot_on_graph))
            nav = player.spot_navigation_state
            assert nav is not None

        if nav.is_traveling:
            raise SpotTravelAlreadyInProgressException("既にスポット間移動中です")

        if nav.current_spot_id == destination_spot_id:
            player_status_repository.save(player)
            return

        route = self._navigation.calculate_route(
            graph, nav.current_spot_id, destination_spot_id
        )
        if not route:
            raise SpotTravelUnreachableException(
                f"到達不能: {nav.current_spot_id} → {destination_spot_id}"
            )

        leg_cids = []
        leg_ticks = []
        for i in range(len(route) - 1):
            a, b = route[i], route[i + 1]
            conn = graph.find_first_passable_connection_between(a, b)
            if conn is None:
                raise SpotTravelUnreachableException(f"接続なし: {a} → {b}")
            ok, reason = self._navigation.can_pass(conn, owned_item_spec_ids, world_flags)
            if not ok:
                raise ConnectionNotPassableException(reason or "通行できません")
            leg_cids.append(conn.connection_id)
            leg_ticks.append(conn.travel_ticks)

        new_nav = PlayerSpotNavigationState.begin_travel(
            route=tuple(route),
            leg_connection_ids=tuple(leg_cids),
            leg_travel_ticks=tuple(leg_ticks),
        )
        player.set_spot_navigation_state(new_nav)
        player_status_repository.save(player)

    def advance_spot_travel_one_tick(
        self,
        player_id: PlayerId,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> SpotTravelTickAdvanceDto | None:
        """移動中なら 1 ティック進める。グラフの move_entity を順に適用する。"""
        if self._command_scope_factory is None:
            return self._advance_spot_travel_one_tick(
                player_id,
                owned_item_spec_ids,
                world_flags,
                spot_graph_repository=self._spot_graph_repository,
                player_status_repository=self._player_status_repository,
                context=None,
            )
        with self._command_scope_factory.create() as context:
            repositories = context.repositories
            return self._advance_spot_travel_one_tick(
                player_id,
                owned_item_spec_ids,
                world_flags,
                spot_graph_repository=repositories.spot_graph,
                player_status_repository=repositories.player_statuses,
                context=context,
            )

    def _advance_spot_travel_one_tick(
        self,
        player_id: PlayerId,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
        *,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
        context: "CommandContext[MovementCommandRepositoryProviderPort] | None",
    ) -> SpotTravelTickAdvanceDto | None:
        graph = spot_graph_repository.find_graph()
        existing_events = tuple(graph.get_events())
        player = player_status_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found: {player_id}")
        nav = player.spot_navigation_state
        if nav is None or not nav.is_traveling:
            return None

        crossings, new_nav = nav.advance_one_world_tick()
        entity_id = self.entity_id_for_player(player_id)
        entered: list[SpotId] = []
        for cid, _dest in crossings:
            if self._is_departed(player_id):
                if self._departed_position_store is None:
                    raise RuntimeError("departed position store is not wired")
                if self._departed_position_store.find(player_id) is None:
                    raise RuntimeError(f"去った主体の位置がありません: {player_id}")
                connection = graph.get_connection(cid)
                can_pass, reason = self._navigation.can_pass(
                    connection,
                    owned_item_spec_ids,
                    world_flags,
                )
                if not can_pass:
                    raise ConnectionNotPassableException(reason or "通行できません")
                self._departed_position_store.move(player_id, _dest)
                entered.append(_dest)
            else:
                graph.move_entity(entity_id, cid, owned_item_spec_ids, world_flags)
                entered.append(graph.get_entity_spot(entity_id))

        player.set_spot_navigation_state(new_nav)
        new_events: tuple[DomainEvent, ...] = ()
        if context is not None:
            all_events = tuple(graph.get_events())
            new_events = all_events[len(existing_events):]
            graph.clear_events()
            for event in existing_events:
                graph.add_event(event)
        spot_graph_repository.save(graph)
        player_status_repository.save(player)
        if context is not None:
            context.collect_all(new_events)
        return SpotTravelTickAdvanceDto(entered_spot_ids=tuple(entered))

    def cancel_spot_travel(
        self,
        player_id: PlayerId,
    ) -> PlayerSpotNavigationState | None:
        """移動中なら現在地で中断し、中断前の不変stateを返す。"""
        if self._command_scope_factory is None:
            return self._cancel_spot_travel(
                player_id,
                self._player_status_repository,
            )
        with self._command_scope_factory.create() as context:
            return self._cancel_spot_travel(
                player_id,
                context.repositories.player_statuses,
            )

    @staticmethod
    def _cancel_spot_travel(
        player_id: PlayerId,
        player_status_repository: PlayerStatusRepository,
    ) -> PlayerSpotNavigationState | None:
        player = player_status_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found: {player_id}")
        nav = player.spot_navigation_state
        if nav is None or not nav.is_traveling:
            return None
        player.set_spot_navigation_state(
            PlayerSpotNavigationState.at_rest(nav.current_spot_id)
        )
        player_status_repository.save(player)
        return nav

    def restore_spot_travel_state(
        self,
        player_id: PlayerId,
        navigation_state: PlayerSpotNavigationState,
    ) -> None:
        """後続操作が失敗した中断を、別commandとして元の予約へ戻す。"""
        if self._command_scope_factory is None:
            self._restore_spot_travel_state(
                player_id,
                navigation_state,
                self._player_status_repository,
            )
            return
        with self._command_scope_factory.create() as context:
            self._restore_spot_travel_state(
                player_id,
                navigation_state,
                context.repositories.player_statuses,
            )

    @staticmethod
    def _restore_spot_travel_state(
        player_id: PlayerId,
        navigation_state: PlayerSpotNavigationState,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        player = player_status_repository.find_by_id(player_id)
        if player is None:
            raise ValueError(f"Player not found: {player_id}")
        player.set_spot_navigation_state(navigation_state)
        player_status_repository.save(player)
