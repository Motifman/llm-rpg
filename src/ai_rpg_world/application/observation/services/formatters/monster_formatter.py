"""モンスターイベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.monster.event.monster_events import (
    ActorStateChangedEvent,
    BehaviorStuckEvent,
    MonsterCreatedEvent,
    MonsterDamagedEvent,
    MonsterDecidedToInteractEvent,
    MonsterDecidedToMoveEvent,
    MonsterDecidedToUseSkillEvent,
    MonsterDiedEvent,
    MonsterEvadedEvent,
    MonsterFedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent,
    MonsterRespawnedEvent,
    MonsterSpawnedEvent,
    TargetLostEvent,
    TargetSpottedEvent,
)


class MonsterObservationFormatter:
    """MonsterSpawnedEvent / MonsterDamagedEvent / MonsterDiedEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, MonsterCreatedEvent):
            return self._format_monster_created(event, recipient_player_id)
        if isinstance(event, MonsterSpawnedEvent):
            return self._format_monster_spawned(event, recipient_player_id)
        if isinstance(event, MonsterRespawnedEvent):
            return self._format_monster_respawned(event, recipient_player_id)
        if isinstance(event, MonsterDamagedEvent):
            return self._format_monster_damaged(event, recipient_player_id)
        if isinstance(event, MonsterDiedEvent):
            return self._format_monster_died(event, recipient_player_id)
        if isinstance(event, MonsterEvadedEvent):
            return self._format_monster_evaded(event, recipient_player_id)
        if isinstance(event, MonsterHealedEvent):
            return self._format_monster_healed(event, recipient_player_id)
        if isinstance(event, MonsterMpRecoveredEvent):
            return self._format_monster_mp_recovered(event, recipient_player_id)
        if isinstance(event, MonsterDecidedToMoveEvent):
            return self._format_monster_decided_to_move(event, recipient_player_id)
        if isinstance(event, MonsterDecidedToUseSkillEvent):
            return self._format_monster_decided_to_use_skill(event, recipient_player_id)
        if isinstance(event, MonsterDecidedToInteractEvent):
            return self._format_monster_decided_to_interact(event, recipient_player_id)
        if isinstance(event, MonsterFedEvent):
            return self._format_monster_fed(event, recipient_player_id)
        if isinstance(event, ActorStateChangedEvent):
            return self._format_actor_state_changed(event, recipient_player_id)
        if isinstance(event, TargetSpottedEvent):
            return self._format_target_spotted(event, recipient_player_id)
        if isinstance(event, TargetLostEvent):
            return self._format_target_lost(event, recipient_player_id)
        if isinstance(event, BehaviorStuckEvent):
            return self._format_behavior_stuck(event, recipient_player_id)
        return None

    def _format_monster_created(
        self, event: MonsterCreatedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        # システム内部向け。観測は出さない。
        return None

    def _format_monster_spawned(
        self, event: MonsterSpawnedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "モンスターが現れました。"
        monster_id = getattr(event.aggregate_id, "value", event.aggregate_id) if event.aggregate_id else None
        spot_id = getattr(event.spot_id, "value", event.spot_id) if event.spot_id else None
        structured = {"type": "monster_spawned", "monster_id_value": monster_id, "spot_id_value": spot_id}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_monster_respawned(
        self, event: MonsterRespawnedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "モンスターが再出現しました。"
        structured = {"type": "monster_respawned"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_monster_damaged(
        self, event: MonsterDamagedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"モンスターに{event.damage}ダメージ。"
        structured = {"type": "monster_damaged", "damage": event.damage, "current_hp": event.current_hp}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_monster_died(
        self, event: MonsterDiedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "モンスターが倒れました。"
        if event.killer_player_id is not None and event.killer_player_id.value == recipient_id.value:
            prose = f"モンスターを倒しました（報酬: {event.gold}ゴールド、{event.exp}EXP）。"
        monster_id = getattr(event.aggregate_id, "value", event.aggregate_id) if event.aggregate_id else None
        spot_id = getattr(event.spot_id, "value", event.spot_id) if event.spot_id else None
        structured = {"type": "monster_died", "monster_id_value": monster_id, "spot_id_value": spot_id, "gold": event.gold, "exp": event.exp}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_monster_evaded(
        self, event: MonsterEvadedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "モンスターが回避しました。"
        structured = {"type": "monster_evaded"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_monster_healed(
        self, event: MonsterHealedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"モンスターが回復しました（+{event.amount}）。"
        structured = {"type": "monster_healed", "amount": event.amount, "current_hp": event.current_hp}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_monster_mp_recovered(
        self, event: MonsterMpRecoveredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_monster_decided_to_move(
        self, event: MonsterDecidedToMoveEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_monster_decided_to_use_skill(
        self, event: MonsterDecidedToUseSkillEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_monster_decided_to_interact(
        self, event: MonsterDecidedToInteractEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_monster_fed(
        self, event: MonsterFedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "モンスターが採食しました。"
        structured = {"type": "monster_fed"}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_actor_state_changed(
        self, event: ActorStateChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"モンスターの状態が{event.old_state.value}から{event.new_state.value}に変化しました。"
        structured = {"type": "monster_state_changed", "old": event.old_state.value, "new": event.new_state.value}
        return ObservationOutput(prose=prose, structured=structured, observation_category="environment")

    def _format_target_spotted(
        self, event: TargetSpottedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_target_lost(
        self, event: TargetLostEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None

    def _format_behavior_stuck(
        self, event: BehaviorStuckEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        return None
