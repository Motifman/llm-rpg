"""プレイヤーイベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
    resolve_item_spec_id_value_for_instance,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.event.status_events import (
    PlayerDownedEvent,
    PlayerLocationChangedEvent,
    PlayerLevelUpEvent,
    PlayerGoldEarnedEvent,
    PlayerGoldPaidEvent,
    PlayerRevivedEvent,
)
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.inventory_events import (
    ItemAddedToInventoryEvent,
    ItemDroppedFromInventoryEvent,
    ItemEquippedEvent,
    ItemUnequippedEvent,
    InventorySlotOverflowEvent,
)


class PlayerObservationFormatter:
    """PlayerLocationChangedEvent / ItemAddedToInventoryEvent / PlayerSpokeEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, PlayerLocationChangedEvent):
            return self._format_player_location_changed(event, recipient_player_id)
        if isinstance(event, PlayerDownedEvent):
            return self._format_player_downed(event, recipient_player_id)
        if isinstance(event, PlayerRevivedEvent):
            return self._format_player_revived(event, recipient_player_id)
        if isinstance(event, PlayerLevelUpEvent):
            return self._format_player_level_up(event, recipient_player_id)
        if isinstance(event, PlayerGoldEarnedEvent):
            return self._format_player_gold_earned(event, recipient_player_id)
        if isinstance(event, PlayerGoldPaidEvent):
            return self._format_player_gold_paid(event, recipient_player_id)
        if isinstance(event, ItemAddedToInventoryEvent):
            return self._format_item_added_to_inventory(event, recipient_player_id)
        if isinstance(event, ItemDroppedFromInventoryEvent):
            return self._format_item_dropped(event, recipient_player_id)
        if isinstance(event, ItemEquippedEvent):
            return self._format_item_equipped(event, recipient_player_id)
        if isinstance(event, ItemUnequippedEvent):
            return self._format_item_unequipped(event, recipient_player_id)
        if isinstance(event, InventorySlotOverflowEvent):
            return self._format_inventory_slot_overflow(event, recipient_player_id)
        if isinstance(event, PlayerSpokeEvent):
            return self._format_player_spoke(event, recipient_player_id)
        return None

    def _format_player_location_changed(
        self, event: PlayerLocationChangedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        spot_name = self._context.name_resolver.spot_name(event.new_spot_id)
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = f"現在地: {spot_name}"
            structured = {
                "type": "current_location",
                "spot_name": spot_name,
                "spot_id_value": event.new_spot_id.value,
                "role": "self",
            }
            return ObservationOutput(
                prose=prose, structured=structured, observation_category="self_only"
            )
        actor_name = self._context.name_resolver.player_name(event.aggregate_id)
        prose = f"{actor_name}がこのスポットにやってきました。"
        structured = {
            "type": "player_entered_spot",
            "actor": actor_name,
            "spot_name": spot_name,
            "spot_id_value": event.new_spot_id.value,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_player_downed(
        self, event: PlayerDownedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        killer_player_id = getattr(event, "killer_player_id", None)
        killer_name = (
            self._context.name_resolver.player_name(killer_player_id)
            if killer_player_id is not None
            else None
        )
        killer_id = (
            getattr(killer_player_id, "value", None)
            if killer_player_id is not None
            else None
        )
        if is_self:
            # 本人視点では誰に倒されたかは当然分かる。
            prose = "戦闘不能になりました。"
            if killer_name:
                prose = f"{killer_name}に倒されました。"
            structured = {"type": "player_downed", "role": "self", "killer_player_id": killer_id}
            return ObservationOutput(
                prose=prose,
                structured=structured,
                observation_category="self_only",
                schedules_turn=True,
                breaks_movement=True,
            )
        # Issue #185: 第三者観測の killer 視認チェック。
        # killer の位置が recipient と同じ spot のときだけ killer 名を出す。
        # 別 spot に killer がいるケースで killer 名を出すと、観測者が本来
        # 知り得ない「誰が倒したか」を漏らす経路になる。
        # 位置不明 (graph 未注入 / lookup 失敗) は安全側に倒し、killer 名を出さない。
        killer_visible = False
        if killer_player_id is not None:
            recipient_spot = self._context.lookup_recipient_spot(recipient_id)
            killer_spot = self._context.lookup_recipient_spot(killer_player_id)
            if (
                recipient_spot is not None
                and killer_spot is not None
                and recipient_spot == killer_spot
            ):
                killer_visible = True
        actor_name = self._context.name_resolver.player_name(event.aggregate_id)
        if killer_visible and killer_name:
            prose = f"{actor_name}が{killer_name}に倒されました。"
        else:
            prose = f"{actor_name}が戦闘不能になりました。"
        structured = {
            "type": "player_downed",
            "actor": actor_name,
            # killer 情報は structured には残す (機械可読、解析用)。
            # prose で出すかどうかは観測可能性で判定する (上述)。
            "killer_player_id": killer_id,
            "killer_visible_to_recipient": killer_visible,
        }
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_player_revived(
        self, event: PlayerRevivedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = "復帰しました。"
            structured = {"type": "player_revived", "role": "self"}
            return ObservationOutput(
                prose=prose, structured=structured, observation_category="self_only"
            )
        actor_name = self._context.name_resolver.player_name(event.aggregate_id)
        prose = f"{actor_name}が復帰しました。"
        structured = {"type": "player_revived", "actor": actor_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="social"
        )

    def _format_player_level_up(
        self, event: PlayerLevelUpEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"レベルが上がりました（{event.old_level} → {event.new_level}）。"
        structured = {"type": "level_up", "old_level": event.old_level, "new_level": event.new_level}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_player_gold_earned(
        self, event: PlayerGoldEarnedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.earned_amount}ゴールドを獲得しました。"
        structured = {"type": "gold_earned", "amount": event.earned_amount}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_player_gold_paid(
        self, event: PlayerGoldPaidEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = f"{event.paid_amount}ゴールドを支払いました。"
        structured = {"type": "gold_paid", "amount": event.paid_amount}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
            breaks_movement=False,
        )

    def _format_player_spoke(
        self, event: PlayerSpokeEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        # Issue #188 第5回実験で観測された「自己三人称ループ」の修正。
        # 話者本人は自分の speech_say の結果を ``action_result_store`` 経由で
        # **一人称ベースの行動 summary** として既に受け取っており、追加で
        # 「{自分の display_name} が『X』と言った」という三人称 observation を
        # 渡すと、Gemma 等の小さい LLM が「自分を三人称で語る主体」と誤認識
        # し、自分や相手を「Bさん」のように呼ぶループに陥る経路になっていた
        # (R1_default LOSE の主因)。
        # ``speech_recipient_strategy.py`` の設計コメントでも「自分が言った
        # 内容を観測として持つかは formatter 側で制御可」と委ねられており、
        # formatter が「持たせない」と判断するのが正しい責務分担。
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            return None

        speaker_name = self._context.name_resolver.player_name(event.aggregate_id)
        if event.channel == SpeechChannel.WHISPER:
            verb = "囁いた"
        elif event.channel == SpeechChannel.SAY:
            verb = "言った"
        else:
            verb = "叫んだ"
        structured_base = {
            "type": "player_spoke",
            "speaker": speaker_name,
            "speaker_player_id": event.aggregate_id.value,
            "channel": event.channel.value,
            "content": event.content,
            "role": "other",
        }
        category = "social"

        repo = self._context.spot_graph_repository
        svc = self._context.sound_propagation_service
        if repo is not None and svc is not None:
            from ai_rpg_world.application.world_graph.speech_channel_mapping import (
                speech_channel_to_sound_volume,
            )
            from ai_rpg_world.domain.world_graph.enum.sound_clarity import SoundClarityEnum
            from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
                EntityNotInGraphException,
            )
            from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

            graph = repo.find_graph()
            speaker_eid = EntityId.create(int(event.aggregate_id.value))
            listener_eid = EntityId.create(int(recipient_id.value))
            try:
                graph.get_entity_spot(speaker_eid)
            except EntityNotInGraphException:
                pass
            else:
                # is_self は上で早期 return 済みなので、ここに来るのは
                # 「話者ではない recipient」のケースのみ。
                source_connection_name: Optional[str] = None
                source_adjacent_spot_name: Optional[str] = None
                if event.channel == SpeechChannel.WHISPER:
                    # 囁き: 宛先 (target_player_id) と recipient が一致する
                    # ときだけ届ける。他は同 spot にいても観測しない。
                    if (
                        event.target_player_id is None
                        or event.target_player_id.value != recipient_id.value
                    ):
                        return None
                    clarity = SoundClarityEnum.CLEAR
                else:
                    volume = speech_channel_to_sound_volume(event.channel)
                    outcome = svc.outcome_for_listener(
                        speaker_eid, listener_eid, volume, graph
                    )
                    if outcome is None:
                        return None
                    clarity = outcome.clarity
                    source_connection_name = outcome.source_connection_name
                    # 方向元のスポット名を spot_graph から直接解決する。
                    # name_resolver は tile-map 用 spot_repository に依存しており、
                    # spot_graph 世界では fallback ラベルになってしまうため、
                    # graph の SpotNode.name を使う。
                    if outcome.source_adjacent_spot_id is not None:
                        try:
                            source_adjacent_spot_name = graph.get_spot(
                                outcome.source_adjacent_spot_id
                            ).name
                        except Exception:
                            source_adjacent_spot_name = None

                # Issue #269: MUFFLED/FAINT で「どの接続から聞こえたか」を prose
                # に含める (CLEAR は同 spot なので方向情報は冗長)。
                direction_clause = ""
                if (
                    clarity != SoundClarityEnum.CLEAR
                    and source_connection_name
                ):
                    direction_clause = (
                        f"〈{source_connection_name}〉の向こうから、"
                    )
                if clarity == SoundClarityEnum.CLEAR:
                    prose = f"{speaker_name}が{verb}: 「{event.content}」"
                elif clarity == SoundClarityEnum.MUFFLED:
                    prose = (
                        f"{direction_clause}{speaker_name}の遠くの声が聞こえる: "
                        f"「{event.content}」"
                    )
                else:
                    prose = (
                        f"{direction_clause}{speaker_name}の声がかすかに聞こえるが、"
                        f"内容ははっきりしない。"
                    )

                structured = dict(structured_base)
                structured["sound_clarity"] = clarity.value
                if source_connection_name is not None:
                    structured["source_connection_name"] = source_connection_name
                if source_adjacent_spot_name is not None:
                    structured["source_adjacent_spot_name"] = source_adjacent_spot_name
                if clarity == SoundClarityEnum.FAINT:
                    # FAINT は内容を秘匿する (聞き取れていない)。話者本人は
                    # この経路に来ないので is_self ガードは不要。
                    structured["content"] = ""
                return ObservationOutput(
                    prose=prose,
                    structured=structured,
                    observation_category=category,
                    # is_self は上で早期 return 済みなので、ここに来るのは他者
                    # の speech を聞いたケースのみ。相手の発話を受けたら自分の
                    # ターンを再スケジュールする (返答や反応のため)。
                    schedules_turn=True,
                )

        prose = f"{speaker_name}が{verb}: 「{event.content}」"
        return ObservationOutput(
            prose=prose,
            structured=structured_base,
            observation_category=category,
            # 同上: 他者発話を聞いた recipient のターンを積む
            schedules_turn=True,
        )

    def _format_item_added_to_inventory(
        self, event: ItemAddedToInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        agg = None
        if self._context.item_repository:
            agg = self._context.item_repository.find_by_id(event.item_instance_id)
        qty = agg.quantity if agg is not None else 1
        if qty != 1:
            prose = f"{item_name}を{qty}個入手しました。"
        else:
            prose = f"{item_name}を入手しました。"
        structured = {"type": "item_added_to_inventory", "item_name": item_name}
        spec_val = event.item_spec_id_value
        if spec_val is None:
            spec_val = resolve_item_spec_id_value_for_instance(
                self._context.item_repository, event.item_instance_id
            )
        if spec_val is not None:
            structured["item_spec_id_value"] = spec_val
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_item_dropped(
        self, event: ItemDroppedFromInventoryEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        prose = f"{item_name}を捨てました。"
        structured = {"type": "item_dropped", "item_name": item_name}
        spec_val = resolve_item_spec_id_value_for_instance(
            self._context.item_repository, event.item_instance_id
        )
        if spec_val is not None:
            structured["item_spec_id_value"] = spec_val
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )

    def _format_item_equipped(
        self, event: ItemEquippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        prose = f"{item_name}を装備しました。"
        structured = {"type": "item_equipped", "item_name": item_name}
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )

    def _format_item_unequipped(
        self, event: ItemUnequippedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        prose = f"{item_name}を外しました。"
        structured = {"type": "item_unequipped", "item_name": item_name}
        spec_val = resolve_item_spec_id_value_for_instance(
            self._context.item_repository, event.item_instance_id
        )
        if spec_val is not None:
            structured["item_spec_id_value"] = spec_val
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )

    def _format_inventory_slot_overflow(
        self, event: InventorySlotOverflowEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(
            event.overflowed_item_instance_id
        )
        prose = f"インベントリが満杯で{item_name}が溢れました。"
        structured = {"type": "inventory_overflow", "item_name": item_name}
        spec_val = resolve_item_spec_id_value_for_instance(
            self._context.item_repository, event.overflowed_item_instance_id
        )
        if spec_val is not None:
            structured["item_spec_id_value"] = spec_val
        return ObservationOutput(
            prose=prose, structured=structured, observation_category="self_only"
        )
