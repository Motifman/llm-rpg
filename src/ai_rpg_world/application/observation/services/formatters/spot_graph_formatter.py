"""スポットグラフ固有イベント用の観測 formatter。

方針: 自分の行動結果はツール結果で返すため、行為者本人には観測を生成しない。
他プレイヤーには social カテゴリで配信し、環境変化は environment で全員に配信する。
"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionStateChangedEvent,
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
    SpotExploredEvent,
    SpotObjectInteractedEvent,
    SpotObjectInteractionFailedEvent,
    SpotPlayerPreparedActionEvent,
    SpotObjectStateChangedEvent,
    SpotPlayerStateChangedInSpotEvent,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    StateDeltaEntry,
)


class SpotGraphObservationFormatter:
    """SpotGraph ドメインイベントを他プレイヤー向け観測に変換する。

    行為者本人は常に None（ツール結果で十分）。
    ConnectionStateChangedEvent / SpotObjectStateChangedEvent は行為者不明の
    環境変化として全受信者に配信する。
    """

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, EntityEnteredSpotEvent):
            return self._format_entity_entered(event, recipient_player_id)
        if isinstance(event, EntityLeftSpotEvent):
            return self._format_entity_left(event, recipient_player_id)
        if isinstance(event, SpotObjectInteractedEvent):
            return self._format_object_interacted(event, recipient_player_id)
        if isinstance(event, SpotObjectInteractionFailedEvent):
            return self._format_interaction_failed(event, recipient_player_id)
        if isinstance(event, SpotPlayerPreparedActionEvent):
            return self._format_prepared_action(event, recipient_player_id)
        if isinstance(event, SpotExploredEvent):
            return self._format_explored(event, recipient_player_id)
        if isinstance(event, ConnectionStateChangedEvent):
            return self._format_connection_changed(event, recipient_player_id)
        if isinstance(event, SpotObjectStateChangedEvent):
            return self._format_object_state_changed(event, recipient_player_id)
        if isinstance(event, SpotPlayerStateChangedInSpotEvent):
            return self._format_player_state_changed_in_spot(event, recipient_player_id)
        return None

    def _is_self(self, entity_id: Any, recipient_id: PlayerId) -> bool:
        return entity_id.value == recipient_id.value

    def _resolve_entity_name(self, entity_id: Any) -> str:
        return self._context.name_resolver.player_name(PlayerId(entity_id.value))

    def _resolve_spot_name(self, spot_id: Any) -> str:
        repo = self._context.spot_graph_repository
        if repo is None:
            return "不明なスポット"
        try:
            graph = repo.find_graph()
            return graph.get_spot(spot_id).name
        except Exception:
            return "不明なスポット"

    def _resolve_object_name(self, spot_id: Any, object_id: Any) -> str:
        repo = self._context.spot_graph_repository
        if repo is None:
            return "何か"
        try:
            graph = repo.find_graph()
            spot = graph.get_spot(spot_id)
            if spot.interior is not None:
                obj = spot.interior.get_object(object_id)
                if obj is not None:
                    return obj.name
        except Exception:
            pass
        return "何か"

    def _format_entity_entered(
        self, event: EntityEnteredSpotEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        spot = self._resolve_spot_name(event.spot_id)
        prose = f"{actor}が{spot}にやってきた。"
        structured = {
            "type": "entity_entered_spot",
            "actor": actor,
            "spot_name": spot,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_entity_left(
        self, event: EntityLeftSpotEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        prose = f"{actor}がこのスポットを去った。"
        structured = {
            "type": "entity_left_spot",
            "actor": actor,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_object_interacted(
        self, event: SpotObjectInteractedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        obj_name = self._resolve_object_name(event.spot_id, event.object_id)
        prose = f"{actor}が{obj_name}を操作した。"
        structured = {
            "type": "spot_object_interacted",
            "actor": actor,
            "object_name": obj_name,
            "action_name": event.action_name,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_prepared_action(
        self, event: SpotPlayerPreparedActionEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        # アクター本人は自身の prepare 操作結果をツール側で受け取るため除外。
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        prose = event.observation_message
        structured = {
            "type": "spot_player_prepared_action",
            "actor": actor,
            "action_id": event.action_id,
            "group_id": event.group_id,
            "message": event.observation_message,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_interaction_failed(
        self, event: SpotObjectInteractionFailedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        # アクター本人にはツール結果として失敗が返るため、観測は他者にのみ。
        if self._is_self(event.entity_id, recipient_id):
            return None
        # actor / obj_name は構造化データのコンテキスト情報として保存。
        # prose 自体はシナリオ作家が書いた observation_message をそのまま
        # 使う（テンプレ置換はせず、命名済み主語をシナリオに任せる方針）。
        # 将来テンプレ機能を入れるならここで .format(actor=..., object=...)
        # に拡張するだけで済む。
        actor = self._resolve_entity_name(event.entity_id)
        obj_name = self._resolve_object_name(event.spot_id, event.object_id)
        prose = event.observation_message
        structured = {
            "type": "spot_object_interaction_failed",
            "actor": actor,
            "object_name": obj_name,
            "action_name": event.action_name,
            "message": event.observation_message,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_explored(
        self, event: SpotExploredEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        prose = f"{actor}が周囲を探索している。"
        structured = {
            "type": "spot_explored",
            "actor": actor,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_connection_changed(
        self, event: ConnectionStateChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        repo = self._context.spot_graph_repository
        conn_name = "通路"
        if repo is not None:
            try:
                graph = repo.find_graph()
                conn = graph.get_connection(event.connection_id)
                if conn.name.strip():
                    conn_name = conn.name
            except Exception:
                pass

        if event.traversable:
            prose = f"{conn_name}が通行可能になった。"
        else:
            prose = f"{conn_name}が通行不能になった。"
        structured = {
            "type": "connection_state_changed",
            "connection_name": conn_name,
            "traversable": event.traversable,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_object_state_changed(
        self, event: SpotObjectStateChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        # Phase 4-E: actor を念のため二重ガード（recipient strategy 側でも除外済み）。
        if (
            event.actor_entity_id is not None
            and self._is_self(event.actor_entity_id, recipient_id)
        ):
            return None
        obj_name = self._resolve_object_name(event.spot_id, event.object_id)
        delta = (
            event.state_delta
            if event.state_delta
            else _derive_delta(event.old_state, event.new_state)
        )
        delta_text = _format_delta_text(delta)
        if delta_text:
            prose = f"{obj_name}の{delta_text}。"
        else:
            prose = f"{obj_name}の状態が変化した。"
        structured = {
            "type": "spot_object_state_changed",
            "object_name": obj_name,
            "state_delta": [
                {"key": d.key, "before": d.before, "after": d.after}
                for d in delta
            ],
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_player_state_changed_in_spot(
        self,
        event: SpotPlayerStateChangedInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        # 行為者本人は除外（recipient strategy で既に除外済みだが二重ガード）。
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        delta_text = _format_delta_text(event.state_delta)
        # シナリオが observation_message を明示していればそれを優先。
        if event.observation_message:
            prose = event.observation_message
        elif delta_text:
            prose = f"{actor}の{delta_text}。"
        else:
            prose = f"{actor}の様子が変わった。"
        structured = {
            "type": "spot_player_state_changed",
            "actor_name": actor,
            "state_delta": [
                {"key": d.key, "before": d.before, "after": d.after}
                for d in event.state_delta
            ],
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )


def _derive_delta(old_state: dict, new_state: dict):
    """formatter 側のフォールバック: event に state_delta が無いとき
    old_state / new_state を比較して StateDeltaEntry tuple を作る。
    """
    keys = set(old_state.keys()) | set(new_state.keys())
    out = []
    _SENTINEL = object()
    for key in sorted(keys, key=str):
        b = old_state.get(key, _SENTINEL)
        a = new_state.get(key, _SENTINEL)
        if b == a:
            continue
        out.append(
            StateDeltaEntry(
                key=str(key),
                before=None if b is _SENTINEL else b,
                after=None if a is _SENTINEL else a,
            )
        )
    return tuple(out)


def _format_delta_text(delta) -> str:
    """StateDeltaEntry tuple を観測テキスト用の短い日本語に変換する。"""
    if not delta:
        return ""
    fragments = []
    for d in delta:
        if d.before is None and d.after is not None:
            fragments.append(f"{d.key}が{d.after}になった")
        elif d.after is None and d.before is not None:
            fragments.append(f"{d.key}が消えた")
        else:
            fragments.append(f"{d.key}が{d.before}から{d.after}に変わった")
    return "、".join(fragments)
