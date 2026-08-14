"""会議開始commandのapplication service。"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.player.services.fallen_body_registry import (
    FallenBodyRegistry,
)
from ai_rpg_world.application.player.services.player_life_query import PlayerLifeQuery
from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world_graph.enum.meeting_trigger import MeetingStartTrigger
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


logger = logging.getLogger(__name__)


class MeetingCommandService:
    """緊急招集と死体報告を、会議開始の一つの責務として扱う。"""

    def __init__(
        self,
        *,
        meeting_enabled: bool,
        game_phase_store: GamePhaseStore,
        spot_graph_repository: ISpotGraphRepository,
        player_status_repository: PlayerStatusRepository,
        player_life_query: PlayerLifeQuery,
        fallen_body_registry: FallenBodyRegistry,
        player_ids_provider: Callable[[], Iterable[PlayerId]],
        current_tick_provider: Callable[[], int],
        begin_meeting: Callable[..., Any],
    ) -> None:
        self._meeting_enabled = meeting_enabled
        self._game_phase_store = game_phase_store
        self._spot_graph_repository = spot_graph_repository
        self._player_status_repository = player_status_repository
        self._player_life_query = player_life_query
        self._fallen_body_registry = fallen_body_registry
        self._player_ids_provider = player_ids_provider
        self._current_tick_provider = current_tick_provider
        self._begin_meeting = begin_meeting

    def call_emergency_meeting(
        self,
        player_id: PlayerId,
        *,
        trigger: str = MeetingStartTrigger.EMERGENCY_BUTTON.value,
    ) -> LlmCommandResultDto:
        """緊急招集の拒否条件を確認し、全員を集めて会議を始める。"""
        if not self._meeting_enabled:
            return LlmCommandResultDto(
                success=False,
                message="ここには皆を集めて話し合う仕組みが無い。",
                error_code="MEETING_NOT_AVAILABLE",
            )
        store = self._game_phase_store
        if store.is_meeting():
            return LlmCommandResultDto(
                success=False,
                message="すでに話し合いが始まっている。",
                error_code="MEETING_ALREADY_STARTED",
            )
        if not store.has_emergency_button(player_id):
            return LlmCommandResultDto(
                success=False,
                message="緊急招集はもう使ってしまった。二度は呼べない。",
                error_code="EMERGENCY_BUTTON_SPENT",
            )
        if store.is_meeting_on_cooldown(tick=int(self._current_tick_provider())):
            return LlmCommandResultDto(
                success=False,
                message="さっき話し合いが終わったばかりだ。今は誰も応じない。",
                error_code="MEETING_ON_COOLDOWN",
            )
        if not self._is_placed_in_graph(player_id):
            return LlmCommandResultDto(
                success=False,
                message="いまは呼びかけられない。",
                error_code="INITIATOR_NOT_PLACED",
            )
        store.consume_emergency_button(player_id)
        self._gather_for_meeting(player_id)
        self._begin_meeting(
            initiator_player_id=player_id,
            trigger=trigger,
        )
        return LlmCommandResultDto(success=True, message="緊急招集をかけた。")

    def report_body(
        self,
        reporter_player_id: PlayerId,
        target_player_id: PlayerId,
    ) -> LlmCommandResultDto:
        """同じ場所の報告可能な身体を記録し、全員を集めて会議を始める。"""
        if not self._meeting_enabled:
            return LlmCommandResultDto(
                success=False,
                message="ここには皆を集めて話し合う仕組みが無い。",
                error_code="MEETING_NOT_AVAILABLE",
            )
        store = self._game_phase_store
        if store.is_meeting():
            return LlmCommandResultDto(
                success=False,
                message="すでに話し合いが始まっている。",
                error_code="MEETING_ALREADY_STARTED",
            )
        if store.is_body_reported(target_player_id):
            return LlmCommandResultDto(
                success=False,
                message="それはもう報告済みだ。",
                error_code="BODY_ALREADY_REPORTED",
            )
        graph = self._spot_graph_repository.find_graph()
        try:
            reporter_spot = graph.get_entity_spot(
                EntityId.create(int(reporter_player_id))
            )
        except Exception:
            return LlmCommandResultDto(
                success=False,
                message="その相手が見つからない。",
                error_code="TARGET_NOT_FOUND",
            )
        target_has_body = self._player_life_query.has_reportable_body(
            target_player_id
        )
        body = self._fallen_body_registry.find(target_player_id)
        if target_has_body:
            if body is None:
                raise RuntimeError(
                    "reportable body has no fallen-body record: "
                    f"player_id={int(target_player_id)}"
                )
            target_spot = body.spot_id
        else:
            try:
                target_spot = graph.get_entity_spot(
                    EntityId.create(int(target_player_id))
                )
            except Exception:
                return LlmCommandResultDto(
                    success=False,
                    message="その相手が見つからない。",
                    error_code="TARGET_NOT_FOUND",
                )
        if reporter_spot != target_spot:
            return LlmCommandResultDto(
                success=False,
                message="その相手はここには居ない。",
                error_code="TARGET_NOT_HERE",
            )
        if not target_has_body:
            return LlmCommandResultDto(
                success=False,
                message="その相手は動いている。報告することは何もない。",
                error_code="TARGET_NOT_INCAPACITATED",
            )
        store.mark_body_reported(target_player_id)
        self._gather_for_meeting(reporter_player_id)
        self._begin_meeting(
            initiator_player_id=reporter_player_id,
            trigger=MeetingStartTrigger.BODY_REPORT.value,
        )
        return LlmCommandResultDto(
            success=True,
            message="倒れている者を見つけたと知らせた。",
        )

    def _is_placed_in_graph(self, player_id: PlayerId) -> bool:
        try:
            graph = self._spot_graph_repository.find_graph()
            graph.get_entity_spot(EntityId.create(int(player_id)))
            return True
        except Exception:
            return False

    def _gather_for_meeting(self, initiator_player_id: PlayerId) -> None:
        graph = self._spot_graph_repository.find_graph()
        target_spot = graph.get_entity_spot(
            EntityId.create(int(initiator_player_id))
        )
        for player_id in self._player_ids_provider():
            if int(player_id) == int(initiator_player_id):
                continue
            if not self._player_life_query.can_vote(player_id):
                continue
            try:
                graph.teleport_entity(EntityId.create(int(player_id)), target_spot)
                self._settle_navigation_at(player_id, target_spot)
            except Exception:
                logger.warning(
                    "会議への集合に失敗した player_id=%s",
                    int(player_id),
                    exc_info=True,
                )
        self._spot_graph_repository.save(graph)

    def _settle_navigation_at(self, player_id: PlayerId, spot_id: Any) -> None:
        status = self._player_status_repository.find_by_id(player_id)
        if status is None:
            return
        status.set_spot_navigation_state(
            PlayerSpotNavigationState.at_rest(spot_id)
        )
        self._player_status_repository.save(status)


__all__ = ["MeetingCommandService"]
