"""観測テキスト（プローズ＋構造化）を生成するフォーマッタ実装"""

from typing import Any, Dict, Optional, TYPE_CHECKING

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.contracts.interfaces import IObservationFormatter
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.conversation_formatter import (
    ConversationObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.quest_formatter import (
    QuestObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.shop_formatter import (
    ShopObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.trade_formatter import (
    TradeObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.sns_formatter import (
    SnsObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.guild_formatter import (
    GuildObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.harvest_formatter import (
    HarvestObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.monster_formatter import (
    MonsterObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.combat_formatter import (
    CombatObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.skill_formatter import (
    SkillObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.world_formatter import (
    WorldObservationFormatter,
)
from ai_rpg_world.application.observation.services.formatters.player_formatter import (
    PlayerObservationFormatter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.pursuit.event.pursuit_events import (
    PursuitCancelledEvent,
    PursuitFailedEvent,
    PursuitStartedEvent,
    PursuitUpdatedEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.sns.repository.sns_user_repository import UserRepository
    from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
    from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
    from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
    from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
    from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
    from ai_rpg_world.domain.guild.repository.guild_repository import GuildRepository
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
    from ai_rpg_world.domain.skill.repository.skill_repository import SkillSpecRepository


class ObservationFormatter(IObservationFormatter):
    """
    イベント＋配信先を観測テキスト（プローズ文と構造化 dict）に変換する。
    仕様の「観測内容（例）」に基づく。名前解決は任意のリポジトリで行う。
    """

    def __init__(
        self,
        spot_repository: Optional["SpotRepository"] = None,
        player_profile_repository: Optional["PlayerProfileRepository"] = None,
        item_spec_repository: Optional["ItemSpecRepository"] = None,
        item_repository: Optional["ItemRepository"] = None,
        shop_repository: Optional["ShopRepository"] = None,
        guild_repository: Optional["GuildRepository"] = None,
        monster_repository: Optional["MonsterRepository"] = None,
        skill_spec_repository: Optional["SkillSpecRepository"] = None,
        sns_user_repository: Optional["UserRepository"] = None,
    ) -> None:
        self._name_resolver = ObservationNameResolver(
            spot_repository=spot_repository,
            player_profile_repository=player_profile_repository,
            item_spec_repository=item_spec_repository,
            item_repository=item_repository,
            shop_repository=shop_repository,
            guild_repository=guild_repository,
            monster_repository=monster_repository,
            skill_spec_repository=skill_spec_repository,
            sns_user_repository=sns_user_repository,
        )
        self._context = ObservationFormatterContext(
            name_resolver=self._name_resolver,
            item_repository=item_repository,
        )
        self._formatters = [
            ConversationObservationFormatter(self._context),
            QuestObservationFormatter(self._context),
            ShopObservationFormatter(self._context),
            TradeObservationFormatter(self._context),
            SnsObservationFormatter(self._context),
            GuildObservationFormatter(self._context),
            HarvestObservationFormatter(self._context),
            MonsterObservationFormatter(self._context),
            CombatObservationFormatter(self._context),
            SkillObservationFormatter(self._context),
            WorldObservationFormatter(self._context),
            PlayerObservationFormatter(self._context),
        ]

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
        attention_level: Optional[AttentionLevel] = None,
    ) -> Optional[ObservationOutput]:
        """指定プレイヤー向けの観測出力を生成。attention_level に応じてスキップする。"""
        output: Optional[ObservationOutput] = None
        for formatter in self._formatters:
            output = formatter.format(event, recipient_player_id)
            if output is not None:
                break
        if output is None:
            output = self._format_pursuit_event(event, recipient_player_id)
        return self._apply_attention_filter(output, attention_level)

    def _apply_attention_filter(
        self,
        output: Optional[ObservationOutput],
        attention_level: Optional[AttentionLevel],
    ) -> Optional[ObservationOutput]:
        if output is None:
            return None
        if attention_level is None or attention_level == AttentionLevel.FULL:
            return output
        if attention_level == AttentionLevel.FILTER_SOCIAL:
            if output.observation_category == "social":
                return None
        if attention_level == AttentionLevel.IGNORE:
            if output.observation_category != "self_only":
                return None
        return output

    def _format_pursuit_event(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, PursuitStartedEvent):
            return self._format_pursuit_started(event, recipient_player_id)
        if isinstance(event, PursuitUpdatedEvent):
            return self._format_pursuit_updated(event, recipient_player_id)
        if isinstance(event, PursuitFailedEvent):
            return self._format_pursuit_failed(event, recipient_player_id)
        if isinstance(event, PursuitCancelledEvent):
            return self._format_pursuit_cancelled(event, recipient_player_id)
        return None

    def _base_pursuit_structured(
        self,
        *,
        event_type: str,
        actor_id: Any,
        target_id: Any,
        pursuit_status_after_event: str,
        interruption_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        actor_id_value = getattr(actor_id, "value", actor_id)
        target_id_value = getattr(target_id, "value", target_id)
        structured: Dict[str, Any] = {
            "type": event_type,
            "event_type": event_type,
            "actor_id": actor_id_value,
            "target_id": target_id_value,
            "actor_world_object_id": actor_id_value,
            "target_world_object_id": target_id_value,
            "pursuit_status_after_event": pursuit_status_after_event,
        }
        if interruption_scope is not None:
            structured["interruption_scope"] = interruption_scope
        return structured

    def _serialize_pursuit_coordinate(self, coordinate: Any) -> Optional[Dict[str, int]]:
        if coordinate is None:
            return None
        return {
            "x": int(getattr(coordinate, "x", 0)),
            "y": int(getattr(coordinate, "y", 0)),
            "z": int(getattr(coordinate, "z", 0)),
        }

    def _serialize_last_known_state(self, last_known: Any) -> Optional[Dict[str, Any]]:
        if last_known is None:
            return None
        return {
            "target_id": getattr(getattr(last_known, "target_id", None), "value", None),
            "spot_id_value": getattr(getattr(last_known, "spot_id", None), "value", None),
            "coordinate": self._serialize_pursuit_coordinate(getattr(last_known, "coordinate", None)),
            "observed_at_tick": getattr(getattr(last_known, "observed_at_tick", None), "value", getattr(last_known, "observed_at_tick", None)),
        }

    def _serialize_target_snapshot(self, target_snapshot: Any) -> Optional[Dict[str, Any]]:
        if target_snapshot is None:
            return None
        return {
            "target_id": getattr(getattr(target_snapshot, "target_id", None), "value", None),
            "spot_id_value": getattr(getattr(target_snapshot, "spot_id", None), "value", None),
            "coordinate": self._serialize_pursuit_coordinate(getattr(target_snapshot, "coordinate", None)),
        }

    def _format_pursuit_started(
        self,
        event: PursuitStartedEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        prose = "対象の追跡を開始しました。"
        structured = self._base_pursuit_structured(
            event_type="pursuit_started",
            actor_id=event.actor_id,
            target_id=event.target_id,
            pursuit_status_after_event="active",
        )
        structured["last_known"] = self._serialize_last_known_state(event.last_known)
        structured["spot_id_value"] = getattr(event.last_known.spot_id, "value", event.last_known.spot_id)
        structured["target_snapshot"] = self._serialize_target_snapshot(event.target_snapshot)
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_pursuit_updated(
        self,
        event: PursuitUpdatedEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        prose = "対象の追跡状況を更新しました。"
        structured = self._base_pursuit_structured(
            event_type="pursuit_updated",
            actor_id=event.actor_id,
            target_id=event.target_id,
            pursuit_status_after_event="active",
        )
        structured["last_known"] = self._serialize_last_known_state(event.last_known)
        structured["spot_id_value"] = getattr(event.last_known.spot_id, "value", event.last_known.spot_id)
        structured["target_snapshot"] = self._serialize_target_snapshot(event.target_snapshot)
        return ObservationOutput(prose=prose, structured=structured, observation_category="self_only")

    def _format_pursuit_failed(
        self,
        event: PursuitFailedEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        prose = "追跡に失敗しました。"
        structured = self._base_pursuit_structured(
            event_type="pursuit_failed",
            actor_id=event.actor_id,
            target_id=event.target_id,
            pursuit_status_after_event="ended",
            interruption_scope="pursuit",
        )
        structured["failure_reason"] = event.failure_reason.value
        structured["last_known"] = self._serialize_last_known_state(event.last_known)
        structured["spot_id_value"] = getattr(event.last_known.spot_id, "value", event.last_known.spot_id)
        structured["target_snapshot"] = self._serialize_target_snapshot(event.target_snapshot)
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_pursuit_cancelled(
        self,
        event: PursuitCancelledEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        prose = "追跡を中断しました。"
        structured = self._base_pursuit_structured(
            event_type="pursuit_cancelled",
            actor_id=event.actor_id,
            target_id=event.target_id,
            pursuit_status_after_event="ended",
            interruption_scope="pursuit",
        )
        structured["last_known"] = self._serialize_last_known_state(event.last_known)
        structured["spot_id_value"] = getattr(event.last_known.spot_id, "value", event.last_known.spot_id)
        structured["target_snapshot"] = self._serialize_target_snapshot(event.target_snapshot)
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )
