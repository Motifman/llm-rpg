"""モンスター反応・Pack 連動の formatter (Phase 4a / 4-O 系列)。

扱う event:
- MonsterStartedFleeingInSpotEvent       (FLEE 開始)
- MonsterStartedChasingInSpotEvent       (CHASE 開始)
- MonsterAbandonedChaseInSpotEvent       (CHASE 諦め)
- MonsterFeltTemperatureDiscomfortInSpotEvent  (温度不快)
- MonsterRespondedToPackHelpInSpotEvent  (pack 援護)
- MonsterFollowedPackFleeInSpotEvent     (pack 群れ逃走)
- MonsterAlertedByPackInSpotEvent        (pack 警戒共有)
"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._spot_graph_formatter_helpers import (
    _SpotGraphFormatterBase,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAbandonedChaseInSpotEvent,
    MonsterAlertedByPackInSpotEvent,
    MonsterFeltTemperatureDiscomfortInSpotEvent,
    MonsterFollowedPackFleeInSpotEvent,
    MonsterRespondedToPackHelpInSpotEvent,
    MonsterStartedChasingInSpotEvent,
    MonsterStartedFleeingInSpotEvent,
)


class SpotGraphMonsterReactionHandler(_SpotGraphFormatterBase):
    """モンスター反応・Pack 連動イベントの formatter。"""

    def format(
        self, event: Any, recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, MonsterStartedFleeingInSpotEvent):
            return self._format_monster_started_fleeing(event, recipient_player_id)
        if isinstance(event, MonsterStartedChasingInSpotEvent):
            return self._format_monster_started_chasing(event, recipient_player_id)
        if isinstance(event, MonsterAbandonedChaseInSpotEvent):
            return self._format_monster_abandoned_chase(event, recipient_player_id)
        if isinstance(event, MonsterFeltTemperatureDiscomfortInSpotEvent):
            return self._format_monster_felt_temperature_discomfort(
                event, recipient_player_id,
            )
        if isinstance(event, MonsterRespondedToPackHelpInSpotEvent):
            return self._format_monster_responded_to_pack_help(
                event, recipient_player_id,
            )
        if isinstance(event, MonsterFollowedPackFleeInSpotEvent):
            return self._format_monster_followed_pack_flee(
                event, recipient_player_id,
            )
        if isinstance(event, MonsterAlertedByPackInSpotEvent):
            return self._format_monster_alerted_by_pack(
                event, recipient_player_id,
            )
        return None

    def _format_monster_started_fleeing(
        self,
        event: MonsterStartedFleeingInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """モンスターが FLEE 状態に遷移した瞬間 (Phase 4a)。

        同 spot 全員に「相手が慌てて逃げ出した」を届ける。後続の
        MonsterLeft/Appeared と組み合わせて「殴られて逃げ出した」prose を
        構築する。
        """
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.monster_id
        )
        prose = f"{monster_name}が怯えて逃げ出した。"
        structured = {
            "type": "monster_started_fleeing",
            "monster_name": monster_name,
            "monster_id": event.monster_id.value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_monster_started_chasing(
        self,
        event: MonsterStartedChasingInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """モンスターが CHASE 状態に遷移した瞬間 (Phase 4a)。

        観測者が **target 本人** ならより緊張感のある prose に切り替える。
        target が他 monster の場合や第三者観測者は中立 prose。
        """
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.monster_id
        )
        is_target = (
            event.target_player_id is not None
            and event.target_player_id.value == recipient_id.value
        )
        if is_target:
            prose = f"{monster_name}があなたを睨み、追跡を始めた。"
        elif event.target_player_id is not None:
            target_name = self._resolve_entity_name(event.target_player_id)
            prose = f"{monster_name}が{target_name}を狙って追跡を始めた。"
        elif event.target_monster_id is not None:
            target_name = self._context.name_resolver.monster_name_by_monster_id(
                event.target_monster_id
            )
            prose = f"{monster_name}が{target_name}を狙って追跡を始めた。"
        else:
            # target id 両方 None は不整合だが防御
            prose = f"{monster_name}が何かを追い始めた。"
        structured = {
            "type": "monster_started_chasing",
            "monster_name": monster_name,
            "monster_id": event.monster_id.value,
            "target_player_id": (
                event.target_player_id.value
                if event.target_player_id is not None else None
            ),
            "target_monster_id": (
                event.target_monster_id.value
                if event.target_monster_id is not None else None
            ),
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_monster_abandoned_chase(
        self,
        event: MonsterAbandonedChaseInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """モンスターが CHASE を諦めて IDLE に戻った瞬間 (Phase 4a/4b)。

        Issue #185: 観測者は「モンスターが追跡をやめた」事実は見えるが、
        その内部理由 (target_lost / no_path / grace_expired 等) は普通は
        推測できない。reason を prose に焼き込むと、観測者が本来知り得ない
        情報を漏らす経路になるため、prose は単一の事実描写に統一し、
        reason は ``structured`` に残して機械可読の補助情報とする。
        観測者の位置が advanced して「進路の障害物が見える」「相手が捜索
        範囲外に出るのを見届けた」などの判定ができるようになったら、
        位置 / 状況ベースで prose を分岐させる (軸 3 の自然な拡張)。
        """
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.monster_id
        )
        prose = f"{monster_name}は追跡を諦めて立ち去った。"
        structured = {
            "type": "monster_abandoned_chase",
            "monster_name": monster_name,
            "monster_id": event.monster_id.value,
            "reason": event.reason,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_monster_felt_temperature_discomfort(
        self,
        event: MonsterFeltTemperatureDiscomfortInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """温度不快ダメージ観測 (Phase 4-O B)。

        kind に応じて寒さ / 暑さの prose を切り替える。第三者視点で
        「monster が environment から圧を受けている」を観測させる。
        """
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.monster_id
        )
        if event.kind == "too_cold":
            prose = f"{monster_name}は寒さに身を震わせている。"
        elif event.kind == "too_hot":
            prose = f"{monster_name}は暑さで弱っている。"
        else:
            prose = f"{monster_name}は環境に苦しんでいる。"
        structured = {
            "type": "monster_felt_temperature_discomfort",
            "monster_name": monster_name,
            "monster_id": event.monster_id.value,
            "kind": event.kind,
            "damage_dealt": event.damage_dealt,
        }
        # `schedules_turn=False`: 温度不快は継続的な環境圧で毎 tick 発火する。
        # turn を毎回トリガーすると LLM コストが線形に膨らむ (例: 100 tick
        # 滞在 = 100 回 turn 誘発)。観測ログには残すが LLM ターンは誘発
        # しない設計。FLEE/CHASE 等の急激な状態変化と異なり、温度ダメージ
        # は数 tick まとめて反応すれば十分。
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=False,
        )

    def _format_monster_responded_to_pack_help(
        self,
        event: MonsterRespondedToPackHelpInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """pack 援護応答 prose (Phase 4-O C)。

        target が観測者本人かで切り替え。第三者には「{responder} が
        {victim} の援護に駆け付ける」中立 prose。
        """
        responder_name = self._context.name_resolver.monster_name_by_monster_id(
            event.responder_monster_id
        )
        victim_name = self._context.name_resolver.monster_name_by_monster_id(
            event.victim_monster_id
        )
        is_target_self = (
            event.target_player_id is not None
            and event.target_player_id.value == recipient_id.value
        )
        if is_target_self:
            prose = (
                f"{responder_name}が{victim_name}の救援に駆け付けた。"
                "あなたを睨んでいる。"
            )
        else:
            prose = f"{responder_name}が{victim_name}の救援に駆け付けた。"
        structured = {
            "type": "monster_responded_to_pack_help",
            "responder_name": responder_name,
            "responder_id": event.responder_monster_id.value,
            "victim_name": victim_name,
            "victim_id": event.victim_monster_id.value,
            "target_player_id": (
                event.target_player_id.value
                if event.target_player_id is not None else None
            ),
            "target_monster_id": (
                event.target_monster_id.value
                if event.target_monster_id is not None else None
            ),
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_monster_followed_pack_flee(
        self,
        event: MonsterFollowedPackFleeInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """pack 群れ逃走 prose (Phase 4-O C #2)。

        leader 名と follower 名を含む「リーダーに続いて逃げ出した」prose。
        leader 自身の FLEE 開始は別途 `MonsterStartedFleeingInSpotEvent`
        で「{leader} が怯えて逃げ出した」と観測される。
        """
        follower_name = self._context.name_resolver.monster_name_by_monster_id(
            event.follower_monster_id
        )
        leader_name = self._context.name_resolver.monster_name_by_monster_id(
            event.leader_monster_id
        )
        prose = f"{follower_name}も{leader_name}に続いて逃げ出した。"
        structured = {
            "type": "monster_followed_pack_flee",
            "follower_name": follower_name,
            "follower_id": event.follower_monster_id.value,
            "leader_name": leader_name,
            "leader_id": event.leader_monster_id.value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_monster_alerted_by_pack(
        self,
        event: MonsterAlertedByPackInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """pack 警戒共有 prose (Phase 4-O C #3)。

        target が観測者本人かで切り替え:
        - 本人: 「気配を察した」+「あなたを警戒している」
        - 第三者: 「{scout} の警戒を察して {responder} も追跡を始めた」
        """
        responder_name = self._context.name_resolver.monster_name_by_monster_id(
            event.responder_monster_id
        )
        scout_name = self._context.name_resolver.monster_name_by_monster_id(
            event.scout_monster_id
        )
        is_target_self = (
            event.target_player_id is not None
            and event.target_player_id.value == recipient_id.value
        )
        if is_target_self:
            prose = (
                f"{responder_name}が{scout_name}の警戒を察し、"
                "あなたの方を睨み始めた。"
            )
        else:
            prose = (
                f"{responder_name}が{scout_name}の警戒を察して"
                "追跡を始めた。"
            )
        structured = {
            "type": "monster_alerted_by_pack",
            "responder_name": responder_name,
            "responder_id": event.responder_monster_id.value,
            "scout_name": scout_name,
            "scout_id": event.scout_monster_id.value,
            "target_player_id": (
                event.target_player_id.value
                if event.target_player_id is not None else None
            ),
            "target_monster_id": (
                event.target_monster_id.value
                if event.target_monster_id is not None else None
            ),
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )
