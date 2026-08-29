"""会議開始commandのapplication service。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from ai_rpg_world.application.common.command_scope_factory import (
    CommandScopeFactoryPort,
)
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.player.services.fallen_body_registry import (
    FallenBodyRegistry,
)
from ai_rpg_world.application.player.services.player_life_query import PlayerLifeQuery
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.application.world_graph.meeting_command_repository_provider import (
    MeetingCommandRepositoryProviderPort,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.enum.meeting_trigger import MeetingStartTrigger
from ai_rpg_world.domain.world_graph.enum.meeting_trigger import MeetingEndReason
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    GamePhaseChangedEvent,
    MeetingVoteCastEvent,
    MeetingVoteResolvedEvent,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_phase_state import (
    GamePhaseState,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.service.vote_tally import resolve_vote


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeetingOngoingCondition:
    """会議開始時に参照する進行中条件のapplication向け宣言。"""

    flag: str
    blocks_emergency_button: bool
    on_meeting_start: tuple[InteractionEffect, ...] = ()


@dataclass(frozen=True)
class MeetingResolutionNotice:
    """commit後に全員へ届ける、会議による異常解決の通知。"""

    flag: str
    messages: tuple[str, ...]


class MeetingCommandService:
    """緊急招集と死体報告を一つの確定境界で開始する。"""

    def __init__(
        self,
        *,
        meeting_enabled: bool,
        game_phase_store: GamePhaseStore,
        player_life_query: PlayerLifeQuery,
        fallen_body_registry: FallenBodyRegistry,
        player_ids_provider: Callable[[], Iterable[PlayerId]],
        current_tick_provider: Callable[[], int],
        player_name_provider: Callable[[PlayerId], str],
        command_scope_factory: CommandScopeFactoryPort[
            MeetingCommandRepositoryProviderPort
        ],
        meeting_committed_observer: Callable[[GamePhaseState], None],
        world_flag_state: MutableWorldFlagState,
        effect_service: WorldGraphEffectService,
        ongoing_conditions: Iterable[MeetingOngoingCondition],
        condition_resolution_observer: Callable[
            [MeetingResolutionNotice], None
        ],
        player_outcome_registry: PlayerOutcomeRegistry,
        meeting_ended_observer: Callable[
            [GamePhaseState, GamePhaseState, str], None
        ],
    ) -> None:
        self._meeting_enabled = meeting_enabled
        self._game_phase_store = game_phase_store
        self._player_life_query = player_life_query
        self._fallen_body_registry = fallen_body_registry
        self._player_ids_provider = player_ids_provider
        self._current_tick_provider = current_tick_provider
        self._player_name_provider = player_name_provider
        self._command_scope_factory = command_scope_factory
        self._meeting_committed_observer = meeting_committed_observer
        self._world_flag_state = world_flag_state
        self._effect_service = effect_service
        self._ongoing_conditions = tuple(ongoing_conditions)
        self._condition_resolution_observer = condition_resolution_observer
        self._player_outcome_registry = player_outcome_registry
        self._meeting_ended_observer = meeting_ended_observer

    def cast_vote(
        self,
        voter_player_id: PlayerId,
        target_player_id: Optional[PlayerId] = None,
    ) -> LlmCommandResultDto:
        """一票と、最後の票なら集計・追放・会議終了を一括確定する。"""
        if not self._meeting_enabled:
            return LlmCommandResultDto(
                success=False,
                message="ここには皆を集めて話し合う仕組みが無い。",
                error_code="MEETING_NOT_AVAILABLE",
            )
        ended: tuple[GamePhaseState, GamePhaseState, str] | None = None
        with self._command_scope_factory.create() as context:
            store = self._game_phase_store
            if not store.is_meeting():
                result = LlmCommandResultDto(
                    success=False,
                    message="いまは話し合いの最中ではない。",
                    error_code="NOT_IN_MEETING",
                )
            elif store.has_voted(voter_player_id):
                result = LlmCommandResultDto(
                    success=False,
                    message="もう投票した。二度は変えられない。",
                    error_code="ALREADY_VOTED",
                )
            else:
                repositories = context.repositories
                store.cast_vote(voter_player_id, target_player_id)
                eligible = self._eligible_voters(repositories)
                graph = repositories.spot_graph.find_graph()
                context.collect(
                    MeetingVoteCastEvent.create(
                        aggregate_id=graph.graph_id,
                        aggregate_type="SpotGraphAggregate",
                        voter_player_id=voter_player_id,
                        voter_display_name=self._player_name_provider(voter_player_id),
                        remaining_voter_count=sum(
                            1 for player_id in eligible if not store.has_voted(player_id)
                        ),
                    )
                )
                if all(store.has_voted(player_id) for player_id in eligible):
                    ended = self._resolve_and_end_in_scope(
                        repositories=repositories,
                        collect_event=context.collect,
                        reason=MeetingEndReason.VOTE_CONCLUDED.value,
                    )
                result = LlmCommandResultDto(success=True, message="投票した。")
        if ended is not None:
            self._observe_committed_end(*ended)
        return result

    def resolve_and_end(
        self,
        *,
        reason: str = MeetingEndReason.VOTE_CONCLUDED.value,
    ) -> GamePhaseState:
        """現在票を集計し、追放を反映して会議を終了する。"""
        with self._command_scope_factory.create() as context:
            ended = self._resolve_and_end_in_scope(
                repositories=context.repositories,
                collect_event=context.collect,
                reason=reason,
            )
        self._observe_committed_end(*ended)
        return ended[1]

    def end_meeting(
        self,
        *,
        reason: str = MeetingEndReason.VOTE_CONCLUDED.value,
    ) -> GamePhaseState:
        """集計を行わずに会議だけを同じ確定境界で終了する。"""
        with self._command_scope_factory.create() as context:
            graph = context.repositories.spot_graph.find_graph()
            meeting_state, state = self._end_meeting_in_scope(
                graph_id=graph.graph_id,
                collect_event=context.collect,
                reason=reason,
            )
        self._observe_committed_end(meeting_state, state, reason)
        return state

    def _resolve_and_end_in_scope(
        self,
        *,
        repositories: MeetingCommandRepositoryProviderPort,
        collect_event: Callable[[object], None],
        reason: str,
    ) -> tuple[GamePhaseState, GamePhaseState, str]:
        store = self._game_phase_store
        ballots = {
            PlayerId(voter): (None if target is None else PlayerId(target))
            for voter, target in store.ballots.items()
        }
        vote_result = resolve_vote(ballots)
        graph = repositories.spot_graph.find_graph()
        ejected_player_id: PlayerId | None = None
        if (
            vote_result.ejected_player_id is not None
            and self._player_outcome_registry.set_outcome(
                vote_result.ejected_player_id,
                PlayerOutcomeEnum.EJECTED,
                notify_callbacks=False,
            )
        ):
            ejected_player_id = vote_result.ejected_player_id
            graph.unplace_entity(EntityId.create(int(vote_result.ejected_player_id)))
            repositories.spot_graph.save(graph)
        collect_event(
            MeetingVoteResolvedEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                ejected_display_name=(
                    self._player_name_provider(vote_result.ejected_player_id)
                    if vote_result.ejected_player_id is not None
                    else ""
                ),
                ejected_player_id=ejected_player_id,
                counts_by_display_name={
                    self._player_name_provider(player_id): count
                    for player_id, count in vote_result.counts.items()
                },
                skip_count=vote_result.skip_count,
                ballots_by_display_name={
                    self._player_name_provider(voter): (
                        self._player_name_provider(target) if target is not None else ""
                    )
                    for voter, target in vote_result.ballots.items()
                },
            )
        )
        meeting_state, state = self._end_meeting_in_scope(
            graph_id=graph.graph_id,
            collect_event=collect_event,
            reason=reason,
        )
        return meeting_state, state, reason

    def _end_meeting_in_scope(
        self,
        *,
        graph_id: SpotGraphId,
        collect_event: Callable[[object], None],
        reason: str,
    ) -> tuple[GamePhaseState, GamePhaseState]:
        meeting_state = self._game_phase_store.current
        state = self._game_phase_store.end_meeting(
            tick=int(self._current_tick_provider()), reason=reason
        )
        self._fallen_body_registry.clear()
        collect_event(
            GamePhaseChangedEvent.create(
                aggregate_id=graph_id,
                aggregate_type="SpotGraphAggregate",
                old_phase=meeting_state.phase,
                new_phase=state.phase,
                trigger=reason,
                initiator_display_name="",
            )
        )
        return meeting_state, state

    def _eligible_voters(
        self, repositories: MeetingCommandRepositoryProviderPort
    ) -> tuple[PlayerId, ...]:
        with self._player_life_query.using_player_status_repository(
            repositories.player_statuses
        ):
            return tuple(
                player_id
                for player_id in self._player_ids_provider()
                if self._player_life_query.can_vote(player_id)
            )

    def _observe_committed_end(
        self,
        meeting_state: GamePhaseState,
        state: GamePhaseState,
        reason: str,
    ) -> None:
        try:
            self._meeting_ended_observer(meeting_state, state, reason)
        except Exception:
            logger.warning(
                "会議終了後のtrace記録に失敗しました。確定状態は維持します。",
                exc_info=True,
            )

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
        started_state: GamePhaseState | None = None
        resolution_notices: tuple[MeetingResolutionNotice, ...] = ()
        with self._command_scope_factory.create() as context:
            repositories = context.repositories
            store = self._game_phase_store
            if store.is_meeting():
                result = LlmCommandResultDto(
                    success=False,
                    message="すでに話し合いが始まっている。",
                    error_code="MEETING_ALREADY_STARTED",
                )
            elif self._has_active_emergency_button_blocker():
                result = LlmCommandResultDto(
                    success=False,
                    message=(
                        "異常が続いている間は緊急招集できない。"
                        "異常を解消するか、倒れている者を見つけたなら、"
                        "その場で報告できる。"
                    ),
                    error_code="EMERGENCY_BUTTON_BLOCKED_BY_ONGOING_CONDITION",
                )
            elif not store.has_emergency_button(player_id):
                result = LlmCommandResultDto(
                    success=False,
                    message="緊急招集はもう使ってしまった。二度は呼べない。",
                    error_code="EMERGENCY_BUTTON_SPENT",
                )
            elif store.is_meeting_on_cooldown(
                tick=int(self._current_tick_provider())
            ):
                result = LlmCommandResultDto(
                    success=False,
                    message="さっき話し合いが終わったばかりだ。今は誰も応じない。",
                    error_code="MEETING_ON_COOLDOWN",
                )
            elif not self._is_placed_in_graph(
                player_id,
                repositories.spot_graph,
            ):
                result = LlmCommandResultDto(
                    success=False,
                    message="いまは呼びかけられない。",
                    error_code="INITIATOR_NOT_PLACED",
                )
            else:
                store.consume_emergency_button(player_id)
                graph = self._gather_for_meeting(player_id, repositories)
                started_state, resolution_notices = self._begin_meeting(
                    initiator_player_id=player_id,
                    trigger=trigger,
                    graph_id=graph.graph_id,
                    collect_event=context.collect,
                )
                result = LlmCommandResultDto(
                    success=True,
                    message="緊急招集をかけた。",
                )
        if started_state is not None:
            self._observe_committed_meeting(started_state)
            self._observe_committed_resolutions(resolution_notices)
        return result

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
        started_state: GamePhaseState | None = None
        resolution_notices: tuple[MeetingResolutionNotice, ...] = ()
        with self._command_scope_factory.create() as context:
            repositories = context.repositories
            store = self._game_phase_store
            if store.is_meeting():
                result = LlmCommandResultDto(
                    success=False,
                    message="すでに話し合いが始まっている。",
                    error_code="MEETING_ALREADY_STARTED",
                )
            elif store.is_body_reported(target_player_id):
                result = LlmCommandResultDto(
                    success=False,
                    message="それはもう報告済みだ。",
                    error_code="BODY_ALREADY_REPORTED",
                )
            else:
                result, started_state, resolution_notices = self._report_body_in_scope(
                    reporter_player_id,
                    target_player_id,
                    repositories,
                    context.collect,
                )
        if started_state is not None:
            self._observe_committed_meeting(started_state)
            self._observe_committed_resolutions(resolution_notices)
        return result

    def _observe_committed_meeting(self, state: GamePhaseState) -> None:
        """確定後traceの故障を、成功済みcommandの失敗へ見せない。"""
        try:
            self._meeting_committed_observer(state)
        except Exception:
            logger.warning(
                "会議開始後のtrace記録に失敗しました。会議の確定状態は維持します。",
                exc_info=True,
            )

    def _observe_committed_resolutions(
        self,
        notices: tuple[MeetingResolutionNotice, ...],
    ) -> None:
        """異常解決の通知失敗を、確定済み会議の失敗へ見せない。"""
        for notice in notices:
            try:
                self._condition_resolution_observer(notice)
            except Exception:
                logger.warning(
                    "会議開始後の異常解決通知に失敗しました。確定状態は維持します。",
                    exc_info=True,
                )

    def _has_active_emergency_button_blocker(self) -> bool:
        active_flags = self._world_flag_state.as_frozen_set()
        return any(
            condition.blocks_emergency_button
            and condition.flag in active_flags
            for condition in self._ongoing_conditions
        )

    def _report_body_in_scope(
        self,
        reporter_player_id: PlayerId,
        target_player_id: PlayerId,
        repositories: MeetingCommandRepositoryProviderPort,
        collect_event: Callable[[GamePhaseChangedEvent], None],
    ) -> tuple[
        LlmCommandResultDto,
        GamePhaseState | None,
        tuple[MeetingResolutionNotice, ...],
    ]:
        graph = repositories.spot_graph.find_graph()
        try:
            reporter_spot = graph.get_entity_spot(
                EntityId.create(int(reporter_player_id))
            )
        except Exception:
            return (
                LlmCommandResultDto(
                    success=False,
                    message="その相手が見つからない。",
                    error_code="TARGET_NOT_FOUND",
                ),
                None,
                (),
            )
        with self._player_life_query.using_player_status_repository(
            repositories.player_statuses
        ):
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
                return (
                    LlmCommandResultDto(
                        success=False,
                        message="その相手が見つからない。",
                        error_code="TARGET_NOT_FOUND",
                    ),
                    None,
                    (),
                )
        if reporter_spot != target_spot:
            return (
                LlmCommandResultDto(
                    success=False,
                    message="その相手はここには居ない。",
                    error_code="TARGET_NOT_HERE",
                ),
                None,
                (),
            )
        if not target_has_body:
            return (
                LlmCommandResultDto(
                    success=False,
                    message="その相手は動いている。報告することは何もない。",
                    error_code="TARGET_NOT_INCAPACITATED",
                ),
                None,
                (),
            )
        self._game_phase_store.mark_body_reported(target_player_id)
        graph = self._gather_for_meeting(
            reporter_player_id,
            repositories,
        )
        state, resolution_notices = self._begin_meeting(
            initiator_player_id=reporter_player_id,
            trigger=MeetingStartTrigger.BODY_REPORT.value,
            graph_id=graph.graph_id,
            collect_event=collect_event,
        )
        return (
            LlmCommandResultDto(
                success=True,
                message="倒れている者を見つけたと知らせた。",
            ),
            state,
            resolution_notices,
        )

    def _begin_meeting(
        self,
        *,
        initiator_player_id: PlayerId,
        trigger: str,
        graph_id: SpotGraphId,
        collect_event: Callable[[GamePhaseChangedEvent], None],
    ) -> tuple[GamePhaseState, tuple[MeetingResolutionNotice, ...]]:
        old_phase = self._game_phase_store.current.phase
        state = self._game_phase_store.begin_meeting(
            tick=int(self._current_tick_provider()),
            trigger=trigger,
            initiator_player_id=int(initiator_player_id),
        )
        resolution_notices = self._resolve_ongoing_conditions()
        try:
            initiator_name = self._player_name_provider(initiator_player_id)
        except Exception:
            initiator_name = ""
        collect_event(
            GamePhaseChangedEvent.create(
                aggregate_id=graph_id,
                aggregate_type="SpotGraphAggregate",
                old_phase=old_phase,
                new_phase=state.phase,
                trigger=trigger,
                initiator_display_name=initiator_name,
            )
        )
        return state, resolution_notices

    def _resolve_ongoing_conditions(
        self,
    ) -> tuple[MeetingResolutionNotice, ...]:
        """成立中かつ会議効果を宣言した異常だけをscope内で解決する。"""
        active_flags = self._world_flag_state.as_frozen_set()
        notices: list[MeetingResolutionNotice] = []
        for condition in self._ongoing_conditions:
            if condition.flag not in active_flags or not condition.on_meeting_start:
                continue
            result = self._effect_service.apply_effects(
                interior=SpotInterior.empty(),
                acting_object=None,
                effects=condition.on_meeting_start,
                world_flags=self._world_flag_state.as_frozen_set(),
            )
            self._world_flag_state.replace_from_interaction(
                result.new_flags,
                context=WorldFlagMutationContext(
                    source=WorldFlagMutationSource.MEETING_RESOLUTION,
                    actor_player_id=None,
                ),
            )
            notices.append(
                MeetingResolutionNotice(
                    flag=condition.flag,
                    messages=tuple(result.messages),
                )
            )
        return tuple(notices)

    @staticmethod
    def _is_placed_in_graph(
        player_id: PlayerId,
        repository: ISpotGraphRepository,
    ) -> bool:
        try:
            graph = repository.find_graph()
            graph.get_entity_spot(EntityId.create(int(player_id)))
            return True
        except Exception:
            return False

    def _gather_for_meeting(
        self,
        initiator_player_id: PlayerId,
        repositories: MeetingCommandRepositoryProviderPort,
    ) -> SpotGraphAggregate:
        graph = repositories.spot_graph.find_graph()
        target_spot = graph.get_entity_spot(
            EntityId.create(int(initiator_player_id))
        )
        with self._player_life_query.using_player_status_repository(
            repositories.player_statuses
        ):
            for player_id in self._player_ids_provider():
                if int(player_id) == int(initiator_player_id):
                    continue
                if not self._player_life_query.can_vote(player_id):
                    continue
                try:
                    graph.teleport_entity(EntityId.create(int(player_id)), target_spot)
                except Exception:
                    logger.warning(
                        "会議への集合に失敗した player_id=%s",
                        int(player_id),
                        exc_info=True,
                    )
                    continue
                # repository保存失敗を個別playerの集合失敗へ潰さない。graphだけを
                # teleport済みにすると、次tickで古い経路が再開して世界が壊れる。
                self._settle_navigation_at(player_id, target_spot, repositories)
        repositories.spot_graph.save(graph)
        return graph

    @staticmethod
    def _settle_navigation_at(
        player_id: PlayerId,
        spot_id: SpotId,
        repositories: MeetingCommandRepositoryProviderPort,
    ) -> None:
        status = repositories.player_statuses.find_by_id(player_id)
        if status is None:
            return
        status.set_spot_navigation_state(PlayerSpotNavigationState.at_rest(spot_id))
        repositories.player_statuses.save(status)


__all__ = [
    "MeetingCommandService",
    "MeetingOngoingCondition",
    "MeetingResolutionNotice",
]
