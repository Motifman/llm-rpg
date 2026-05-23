"""オブジェクト・接続・状態変化系イベントの formatter。

SpotObjectInteracted/Failed/StateChanged, ConnectionChanged/Created/Destroyed,
PublicEffectObserved, SpotPlayerStateChangedInSpot をまとめて扱う。
環境変化系は `observation_category="environment"`、社会的観測は `social`。
"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._spot_graph_formatter_helpers import (
    _SpotGraphFormatterBase,
    _derive_delta,
    _format_delta_text,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionCreatedEvent,
    ConnectionDestroyedEvent,
    ConnectionStateChangedEvent,
    SpotObjectInteractedEvent,
    SpotObjectInteractionFailedEvent,
    SpotObjectStateChangedEvent,
    SpotPlayerStateChangedInSpotEvent,
    SpotPublicEffectObservedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
)


class SpotGraphObjectHandler(_SpotGraphFormatterBase):
    """オブジェクト/接続/状態変化系の formatter。"""

    def format(
        self, event: Any, recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, SpotObjectInteractedEvent):
            return self._format_object_interacted(event, recipient_player_id)
        if isinstance(event, SpotObjectInteractionFailedEvent):
            return self._format_interaction_failed(event, recipient_player_id)
        if isinstance(event, ConnectionStateChangedEvent):
            return self._format_connection_changed(event, recipient_player_id)
        if isinstance(event, SpotObjectStateChangedEvent):
            return self._format_object_state_changed(event, recipient_player_id)
        if isinstance(event, SpotPublicEffectObservedEvent):
            return self._format_public_effect_observed(event, recipient_player_id)
        if isinstance(event, ConnectionCreatedEvent):
            return self._format_connection_created(event, recipient_player_id)
        if isinstance(event, ConnectionDestroyedEvent):
            return self._format_connection_destroyed(event, recipient_player_id)
        if isinstance(event, SpotPlayerStateChangedInSpotEvent):
            return self._format_player_state_changed_in_spot(
                event, recipient_player_id,
            )
        return None

    def _format_object_interacted(
        self, event: SpotObjectInteractedEvent, recipient_id: PlayerId,
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
            prose=prose, structured=structured, observation_category="social",
        )

    def _format_interaction_failed(
        self, event: SpotObjectInteractionFailedEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        # アクター本人にはツール結果として失敗が返るため、観測は他者にのみ。
        if self._is_self(event.entity_id, recipient_id):
            return None
        # actor / obj_name は構造化データのコンテキスト情報として保存。
        # prose 自体はシナリオ作家が書いた observation_message をそのまま
        # 使う (テンプレ置換はせず、命名済み主語をシナリオに任せる方針)。
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
            prose=prose, structured=structured, observation_category="social",
        )

    def _format_connection_changed(
        self, event: ConnectionStateChangedEvent, recipient_id: PlayerId,
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

        # Issue #184 (軸 3): 観測者の位置で prose を分岐する。
        # - 両端 spot に居れば「直接観測」: 状態変化を素朴に prose 化
        # - 隣接 spot に居れば「間接観測 (音)」: 通行可否ではなく音だけ
        # - それ以外: recipient_strategy 側で配信を弾いている想定だが、
        #   防御的に直接観測の prose にフォールバック
        recipient_spot = self._context.lookup_recipient_spot(recipient_id)
        is_direct = recipient_spot in (event.from_spot_id, event.to_spot_id)
        is_neighbor = (
            recipient_spot is not None and not is_direct
        )
        if is_neighbor:
            # 音だけ。「通行可能/不能」のような確定的な状態判断は本人が
            # 隣接 spot からでは知り得ないので、観測としては「音がした」止まり。
            prose = f"遠くで{conn_name}が動く音がした。"
            recipient_position = "adjacent"
        else:
            # 直接観測 (両端 spot 内、または位置不明な fallback)。
            # 因果は同 spot で interaction event を別途観測した recipient が
            # 自力で組み立てる。formatter は事実のみを描く (PR #182 の方針)。
            if event.traversable:
                prose = f"{conn_name}が通行可能になった。"
            else:
                prose = f"{conn_name}が通行不能になった。"
            recipient_position = (
                "at_from"
                if recipient_spot == event.from_spot_id
                else "at_to"
                if recipient_spot == event.to_spot_id
                else "unknown"
            )
        structured = {
            "type": "connection_state_changed",
            "connection_name": conn_name,
            "traversable": event.traversable,
            "cause": event.cause.value,
            "recipient_position": recipient_position,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )

    def _format_object_state_changed(
        self, event: SpotObjectStateChangedEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        # Phase 4-E: actor を念のため二重ガード (recipient strategy 側でも除外済み)。
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

    def _format_player_state_changed_in_spot(
        self,
        event: SpotPlayerStateChangedInSpotEvent,
        recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        # 行為者本人は除外 (recipient strategy で既に除外済みだが二重ガード)。
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
