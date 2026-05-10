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
    MonsterAbandonedChaseInSpotEvent,
    MonsterAppearedAtSpotEvent,
    MonsterAteGroundItemEvent,
    MonsterAttackedPlayerInSpotEvent,
    MonsterLeftSpotEvent,
    MonsterPredatedMonsterInSpotEvent,
    MonsterStartedChasingInSpotEvent,
    MonsterStartedFleeingInSpotEvent,
    PlayerAttackedMonsterInSpotEvent,
    SpotExploredEvent,
    SpotObjectInteractedEvent,
    SpotObjectInteractionFailedEvent,
    SpotPlayerPreparedActionEvent,
    SpotObjectStateChangedEvent,
    SpotPlayerStateChangedInSpotEvent,
    SpotPublicEffectObservedEvent,
    ConnectionCreatedEvent,
    ConnectionDestroyedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
    StateDeltaEntry,
)


# 攻撃で対象が「行動不能」になった際の suffix。被害者ごとに自然な日本語を
# 維持するため、player target / monster target を分けて持つ（field 自体は
# `target_incapacitated` で対称化済み）。
_INCAPACITATION_SUFFIX_FOR_PLAYER_TARGET = " 致命的なダメージで倒れた。"
_INCAPACITATION_SUFFIX_FOR_MONSTER_TARGET = " 致命傷を与えて倒した。"


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
        if isinstance(event, SpotPublicEffectObservedEvent):
            return self._format_public_effect_observed(event, recipient_player_id)
        if isinstance(event, ConnectionCreatedEvent):
            return self._format_connection_created(event, recipient_player_id)
        if isinstance(event, ConnectionDestroyedEvent):
            return self._format_connection_destroyed(event, recipient_player_id)
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
        if isinstance(event, MonsterStartedFleeingInSpotEvent):
            return self._format_monster_started_fleeing(event, recipient_player_id)
        if isinstance(event, MonsterStartedChasingInSpotEvent):
            return self._format_monster_started_chasing(event, recipient_player_id)
        if isinstance(event, MonsterAbandonedChaseInSpotEvent):
            return self._format_monster_abandoned_chase(event, recipient_player_id)
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

    def _format_public_effect_observed(
        self,
        event: SpotPublicEffectObservedEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """汎用 public effect の観測。kind で分岐してプロセを組む。"""
        # 二重ガード: actor 自身は除外
        if (
            event.actor_entity_id is not None
            and self._is_self(event.actor_entity_id, recipient_id)
        ):
            return None
        actor = (
            self._resolve_entity_name(event.actor_entity_id)
            if event.actor_entity_id is not None
            else "誰か"
        )
        delta_text = _format_delta_text(event.state_delta)
        kind = event.kind
        # kind 別のプロセ。ふさわしいものが無いときは description にフォールバック。
        if kind == AppliedEffectKind.DAMAGE:
            # 現状の APPLY_DAMAGE は acting_player を対象にする仕様のため、
            # actor == 受傷者として扱う。第三者にダメージを与える spec が
            # 入った時点で event 側に target_entity_id を追加してプロセを
            # 切り替える必要がある。
            prose = (
                f"{actor}が{event.description}"
                if event.description
                else f"{actor}がダメージを受けた"
            )
            category = "social"
        elif kind == AppliedEffectKind.STATUS_EFFECT:
            prose = (
                f"{actor}に{event.description}が現れた"
                if event.description
                else f"{actor}に状態異常が現れた"
            )
            category = "social"
        elif kind == AppliedEffectKind.SATISFY_NEED:
            prose = (
                f"{actor}が{event.description}"
                if event.description
                else f"{actor}が回復した様子だ"
            )
            category = "social"
        elif kind == AppliedEffectKind.ATMOSPHERE_UPDATE:
            # description は "スポット {id} の雰囲気が変化した" という汎用文字列
            # なので、ここで spot 名と state_delta から具体プロセを組み立てる。
            spot_name = self._resolve_spot_name(event.spot_id)
            if delta_text:
                prose = f"{spot_name}の{delta_text}"
            else:
                prose = f"{spot_name}の雰囲気が変わった"
            category = "environment"
        elif kind in (
            AppliedEffectKind.TARGET_ITEM_STATE_CHANGE,
            AppliedEffectKind.ACTING_ITEM_STATE_CHANGE,
        ):
            target = event.target_ref or "アイテム"
            if delta_text:
                prose = f"{target}の{delta_text}"
            else:
                prose = event.description or f"{target}の状態が変わった"
            category = "environment"
        # NOTE: TELEPORT は emitter 側で skip されるためこの formatter には
        # 届かない (spec が dead code のため)。entity 移動が wire された後は
        # EntityLeftSpotEvent が担う想定なので、本 formatter で TELEPORT を
        # 処理する分岐は意図的に持たない。
        else:
            # 想定外 kind: description で代替
            prose = event.description or f"{actor}に何かが起きた"
            category = "social"
        # 末尾句点
        if not prose.endswith("。"):
            prose = prose + "。"
        structured = {
            "type": "spot_public_effect_observed",
            "kind": kind.value,
            "actor_name": actor,
            "target_ref": event.target_ref,
            "state_delta": [
                {"key": d.key, "before": d.before, "after": d.after}
                for d in event.state_delta
            ],
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category=category,
            schedules_turn=True,
        )

    def _format_connection_created(
        self,
        event: ConnectionCreatedEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        from_name = self._resolve_spot_name(event.from_spot_id)
        to_name = self._resolve_spot_name(event.to_spot_id)
        prose = f"{from_name}と{to_name}を結ぶ新しい通路が現れた。"
        structured = {
            "type": "connection_created",
            "from_spot_name": from_name,
            "to_spot_name": to_name,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_connection_destroyed(
        self,
        event: ConnectionDestroyedEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        from_name = self._resolve_spot_name(event.from_spot_id)
        to_name = self._resolve_spot_name(event.to_spot_id)
        prose = f"{from_name}と{to_name}を結んでいた通路が崩れた。"
        structured = {
            "type": "connection_destroyed",
            "from_spot_name": from_name,
            "to_spot_name": to_name,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

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
          ・視認不可（暗闇 + dark_vision モンスター）なら「暗闇から襲われた」
        - **被害者以外の同スポット第三者**:
          ・視認可なら「{monster}が{target_name}を攻撃した」
          ・視認不可（観測者から monster が見えない）なら「闇の中で何かが
            動いた気がする」レベルに縮退すべき
          TODO(combat-pr-followup): 暗闇 + dark_vision モンスター × 第三者
          観測者の組み合わせで、「灰色のオオカミが勇者を攻撃した」と完全な
          情報が出てしまう。被害者には「暗闇から襲われた」と縮退するのに
          第三者だけ完全情報を得る非対称が生じる。本 PR は最小実装で常に
          名前付き prose にし、戦闘 PR 系列の次イテレーションで第三者向け
          縮退表記を追加する（被害者と同じく effective_lighting で判定）。
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

        理由 (`reason`) によって若干 prose のニュアンスを変える:
        - grace_expired / max_ticks_exceeded: 「諦めて立ち去った」
        - target_lost / search_expired: 「見失って戻っていった」
        - no_path: 「進路を阻まれて引き返した」
        """
        monster_name = self._context.name_resolver.monster_name_by_monster_id(
            event.monster_id
        )
        reason = event.reason
        if reason in ("target_lost", "search_expired"):
            prose = f"{monster_name}は獲物を見失い、追跡を諦めたようだ。"
        elif reason == "no_path":
            prose = f"{monster_name}は進路を阻まれ、追跡を諦めた。"
        else:
            # grace_expired / max_ticks_exceeded / 不明 reason の fallback
            prose = f"{monster_name}は追跡を諦めて立ち去った。"
        structured = {
            "type": "monster_abandoned_chase",
            "monster_name": monster_name,
            "monster_id": event.monster_id.value,
            "reason": reason,
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
