"""エンティティ移動・探索・prepared action の formatter。

SpotGraph の event のうち「プレイヤー本人の移動/操作」に相当する物を扱う。
共通: 行為者本人は除外 (ツール結果で代替)、同スポット他プレイヤーには
social として届ける。
"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._spot_graph_formatter_helpers import (
    _SpotGraphFormatterBase,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
    SpotExploredEvent,
    SpotPlayerPreparedActionEvent,
)


class SpotGraphMovementHandler(_SpotGraphFormatterBase):
    """移動系イベントの formatter。"""

    def format(
        self, event: Any, recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, EntityEnteredSpotEvent):
            return self._format_entity_entered(event, recipient_player_id)
        if isinstance(event, EntityLeftSpotEvent):
            return self._format_entity_left(event, recipient_player_id)
        if isinstance(event, SpotExploredEvent):
            return self._format_explored(event, recipient_player_id)
        if isinstance(event, SpotPlayerPreparedActionEvent):
            return self._format_prepared_action(event, recipient_player_id)
        return None

    def _format_entity_entered(
        self, event: EntityEnteredSpotEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        spot = self._resolve_spot_name(event.spot_id)
        # Issue #311 後続: 進入元情報を prose に含めると目撃者にとって自然な
        # 観測になり、追跡行動 (= 「あちらから来た = どこへ向かう方向か」) の
        # 手がかりにできる。``from_spot_id`` が None (= scenario 開始時の
        # 初期配置) は従来通り「やってきた」のみ。
        connection_name: Optional[str] = None
        from_spot_name: Optional[str] = None
        from_spot_id_value: Optional[int] = None
        if event.from_spot_id is not None:
            from_spot_name = self._resolve_spot_name(event.from_spot_id)
            from_spot_id_value = event.from_spot_id.value
            connection_name = self._resolve_connection_name(
                event.from_spot_id, event.spot_id,
            )
        prose = self._compose_entered_prose(
            actor=actor,
            spot_name=spot,
            from_spot_name=from_spot_name,
            connection_name=connection_name,
        )
        structured: dict[str, Any] = {
            "type": "entity_entered_spot",
            "actor": actor,
            "spot_name": spot,
            "spot_id_value": event.spot_id.value,
        }
        if from_spot_name is not None:
            structured["from_spot_name"] = from_spot_name
        if from_spot_id_value is not None:
            structured["from_spot_id_value"] = from_spot_id_value
        if connection_name is not None:
            structured["connection_name"] = connection_name
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social",
        )

    def _format_entity_left(
        self, event: EntityLeftSpotEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        # Issue #311 後続: 行き先 + 通った接続を prose に含めることで、目撃者は
        # 「カイトが書架A の方向へ歩いて行った」と方向を視認できる人間的な観測
        # になる。``to_spot_id`` は ``EntityLeftSpotEvent`` 必須フィールド。
        to_spot_name = self._resolve_spot_name(event.to_spot_id)
        connection_name = self._resolve_connection_name(
            event.spot_id, event.to_spot_id,
        )
        prose = self._compose_left_prose(
            actor=actor,
            to_spot_name=to_spot_name,
            connection_name=connection_name,
        )
        structured: dict[str, Any] = {
            "type": "entity_left_spot",
            "actor": actor,
            "to_spot_name": to_spot_name,
            "to_spot_id_value": event.to_spot_id.value,
        }
        if connection_name is not None:
            structured["connection_name"] = connection_name
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social",
        )

    @staticmethod
    def _compose_entered_prose(
        *,
        actor: str,
        spot_name: str,
        from_spot_name: Optional[str],
        connection_name: Optional[str],
    ) -> str:
        """進入観測の prose を組み立てる (フォールバックを段階化)。"""
        # 接続名と進入元の両方が解決できる場合は最も情報量の多い文を返す
        if from_spot_name and connection_name:
            return (
                f"{actor}が「{from_spot_name}」から〈{connection_name}〉を通って"
                f"{spot_name}にやってきた。"
            )
        if from_spot_name:
            return f"{actor}が「{from_spot_name}」から{spot_name}にやってきた。"
        # from_spot_id が None (= 初期配置) のときは従来通り
        return f"{actor}が{spot_name}にやってきた。"

    @staticmethod
    def _compose_left_prose(
        *,
        actor: str,
        to_spot_name: str,
        connection_name: Optional[str],
    ) -> str:
        """退出観測の prose を組み立てる (接続名が解決できないケースも考慮)。"""
        # 行き先が「不明なスポット」のときは方向が分からない (= 接続情報の取得
        # 失敗) ので、従来文言にフォールバック。
        if not to_spot_name or to_spot_name == "不明なスポット":
            return f"{actor}がこのスポットを去った。"
        if connection_name:
            return (
                f"{actor}が〈{connection_name}〉を抜けて"
                f"「{to_spot_name}」へ去っていった。"
            )
        return f"{actor}が「{to_spot_name}」へ去っていった。"

    def _resolve_connection_name(
        self, from_spot_id: Any, to_spot_id: Any,
    ) -> Optional[str]:
        """``from_spot_id`` → ``to_spot_id`` の接続の通り名を返す (見つからなければ None)。

        通行可否を問わず最初に見つかった接続を返す: イベント発生時は当該接続が
        実際に通過可能だったはずだが、後続の event chain で塞がっている可能性は
        ある。観測 prose は「人間が見てそのまま語る」目的なので、当時の通行可否は
        無視して名前だけ取れれば十分。
        """
        repo = self._context.spot_graph_repository
        if repo is None:
            return None
        try:
            graph = repo.find_graph()
            for conn in graph.iter_outgoing_connections_from(from_spot_id):
                if conn.to_spot_id == to_spot_id:
                    name = (conn.name or "").strip()
                    return name or None
        except Exception:
            return None
        return None

    def _format_explored(
        self, event: SpotExploredEvent, recipient_id: PlayerId,
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
            prose=prose, structured=structured, observation_category="social",
        )

    def _format_prepared_action(
        self, event: SpotPlayerPreparedActionEvent, recipient_id: PlayerId,
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
            prose=prose, structured=structured, observation_category="social",
        )
