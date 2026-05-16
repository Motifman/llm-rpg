"""モンスター出現/退場/攻撃/捕食/採食の formatter。

「同スポット全員に観測として届く」基本的なモンスター行動 (Phase 4 系列)。
反応系 (FLEE/CHASE/pack) は別ファイル `_spot_graph_monster_reaction_handler`
を参照。
"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._spot_graph_formatter_helpers import (
    _INCAPACITATION_SUFFIX_FOR_MONSTER_TARGET,
    _INCAPACITATION_SUFFIX_FOR_PLAYER_TARGET,
    _SpotGraphFormatterBase,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    MonsterAppearedAtSpotEvent,
    MonsterAteGroundItemEvent,
    MonsterAttackedPlayerInSpotEvent,
    MonsterLeftSpotEvent,
    MonsterPredatedMonsterInSpotEvent,
    PlayerAttackedMonsterInSpotEvent,
)


class SpotGraphMonsterHandler(_SpotGraphFormatterBase):
    """モンスター基本イベントの formatter (反応/Pack 系を除く)。"""

    def format(
        self, event: Any, recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, MonsterAppearedAtSpotEvent):
            return self._format_monster_appeared(event, recipient_player_id)
        if isinstance(event, MonsterLeftSpotEvent):
            return self._format_monster_left(event, recipient_player_id)
        if isinstance(event, MonsterAttackedPlayerInSpotEvent):
            return self._format_monster_attacked_player(event, recipient_player_id)
        if isinstance(event, PlayerAttackedMonsterInSpotEvent):
            return self._format_player_attacked_monster(event, recipient_player_id)
        if isinstance(event, MonsterAteGroundItemEvent):
            return self._format_monster_ate_ground_item(event, recipient_player_id)
        if isinstance(event, MonsterPredatedMonsterInSpotEvent):
            return self._format_monster_predated_monster(event, recipient_player_id)
        return None

    def _format_monster_appeared(
        self,
        event: MonsterAppearedAtSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """同じスポットに居るプレイヤーへ「Xが現れた」を届ける。

        recipient strategy 側で同スポット全員に配信されるため、ここでは
        除外ロジックは持たない。モンスター名は ObservationNameResolver
        経由で template.name に解決する。
        """
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.monster_id
        )
        spot_name = self._resolve_spot_name(event.spot_id)
        prose = f"{monster_name}が{spot_name}に現れた。"
        structured = {
            "type": "monster_appeared_at_spot",
            "monster_name": monster_name,
            "monster_id": event.monster_id.value,
            "spot_name": spot_name,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_monster_attacked_player(
        self,
        event: MonsterAttackedPlayerInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """モンスター攻撃の prose 生成。

        受信者ごとに 3 通りの prose に切り替える:
        - **被害者本人 (target_player_id == recipient)**:
          ・視認可なら「{monster}に襲われ {damage} のダメージを受けた」
          ・視認不可 (暗闇 + dark_vision モンスター) なら「暗闇から襲われた」
        - **被害者以外の同スポット第三者**:
          ・視認可なら「{monster}が{target_name}を攻撃した」
          ・視認不可 (観測者から monster が見えない) なら「闇の中で何かが
            動いた気がする」レベルに縮退すべき
          TODO(combat-pr-followup): 暗闇 + dark_vision モンスター × 第三者
          観測者の組み合わせで、「灰色のオオカミが勇者を攻撃した」と完全な
          情報が出てしまう。被害者には「暗闇から襲われた」と縮退するのに
          第三者だけ完全情報を得る非対称が生じる。本 PR は最小実装で常に
          名前付き prose にし、戦闘 PR 系列の次イテレーションで第三者向け
          縮退表記を追加する (被害者と同じく effective_lighting で判定)。
        """
        is_victim = event.target_player_id.value == recipient_id.value
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.attacker_monster_id
        )
        if is_victim:
            if event.target_visible:
                prose = (
                    f"{monster_name}に襲われ {event.damage} のダメージを受けた。"
                )
            else:
                prose = "暗闇から何かに襲われた。"
        else:
            target_name = self._context.name_resolver.player_name(
                PlayerId(event.target_player_id.value)
            )
            prose = f"{monster_name}が{target_name}を攻撃した。"
        if event.target_incapacitated:
            # 倒れた事実は受信者問わず追記。被害者本人に対しては「倒れた」、
            # 第三者からは「{name} が倒れた」とより明確に出したいが、最小
            # 実装では共通 suffix で済ませる。
            prose = prose + _INCAPACITATION_SUFFIX_FOR_PLAYER_TARGET
        structured = {
            "type": "monster_attacked_player",
            "attacker_monster_id": event.attacker_monster_id.value,
            "monster_name": monster_name,
            "target_player_id": event.target_player_id.value,
            "damage": event.damage,
            "target_incapacitated": event.target_incapacitated,
            "target_visible": event.target_visible,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _format_player_attacked_monster(
        self,
        event: PlayerAttackedMonsterInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """プレイヤー → モンスター攻撃の prose を組む。

        recipient_strategy 側で行為者本人は除外済みなので、ここでは常に第三者
        観測として「{actor}が{monster}を攻撃した」を出す。倒した場合は
        「倒した」suffix を追加。
        """
        actor_name = self._resolve_entity_name(event.attacker_entity_id)
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.target_monster_id
        )
        prose = f"{actor_name}が{monster_name}を攻撃した。"
        if event.target_incapacitated:
            prose = prose + _INCAPACITATION_SUFFIX_FOR_MONSTER_TARGET
        structured = {
            "type": "player_attacked_monster",
            "attacker_entity_id": event.attacker_entity_id.value,
            "actor_name": actor_name,
            "target_monster_id": event.target_monster_id.value,
            "monster_name": monster_name,
            "damage": event.damage,
            "target_incapacitated": event.target_incapacitated,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _format_monster_ate_ground_item(
        self,
        event: MonsterAteGroundItemEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """モンスター採食 prose: 「{monster_name}が{item_name}を食べた」。

        actor が monster なので self 除外は無し。同スポット全員に届く。
        """
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.monster_id
        )
        item_name = self._context.name_resolver.item_spec_name(
            event.item_spec_id.value
        )
        prose = f"{monster_name}が{item_name}を食べた。"
        structured = {
            "type": "monster_ate_ground_item",
            "monster_id": event.monster_id.value,
            "monster_name": monster_name,
            "item_instance_id": event.item_instance_id.value,
            "item_spec_id": event.item_spec_id.value,
            "item_name": item_name,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _format_monster_predated_monster(
        self,
        event: MonsterPredatedMonsterInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """モンスター捕食 prose: 致命なら「{attacker}が{prey}を仕留めた」、
        通常攻撃なら「{attacker}が{prey}に襲いかかった」。

        actor / target どちらも monster なので player の self 除外は不要。
        同スポット全員に social として届く。
        """
        attacker_name = self._context.name_resolver.monster_name_by_monster_id(
            event.attacker_monster_id
        )
        prey_name = self._context.name_resolver.monster_name_by_monster_id(
            event.target_monster_id
        )
        if event.target_incapacitated:
            prose = f"{attacker_name}が{prey_name}を仕留めた。"
        else:
            prose = f"{attacker_name}が{prey_name}に襲いかかった。"
        structured = {
            "type": "monster_predated_monster",
            "attacker_monster_id": event.attacker_monster_id.value,
            "attacker_name": attacker_name,
            "target_monster_id": event.target_monster_id.value,
            "target_name": prey_name,
            "damage": event.damage,
            "target_incapacitated": event.target_incapacitated,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _format_monster_left(
        self,
        event: MonsterLeftSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """同じスポットに居るプレイヤーへ「Xが居なくなった」を届ける。

        despawn / 死亡 / 撤去いずれの片道遷移も同じプロセでカバーする。
        死亡時など個別の文体が必要になったら専用 event に分離する方針。
        """
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.monster_id
        )
        spot_name = self._resolve_spot_name(event.spot_id)
        prose = f"{monster_name}の姿が見えなくなった。"
        structured = {
            "type": "monster_left_spot",
            "monster_name": monster_name,
            "monster_id": event.monster_id.value,
            "spot_name": spot_name,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )
