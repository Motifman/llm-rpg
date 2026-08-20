"""プレイヤーイベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
    resolve_item_spec_id_value_for_instance,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
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


#: 隣から漏れ聞こえる言葉の長さ。誰が何の話をしているかは分かり、中身までは
#: 分からない量。
_OVERHEARD_CHARS = 20


def _overheard_fragment(content: str) -> str:
    """遠くから聞こえた言葉を、聞き取れたぶんだけにする。

    **「遠くの声が聞こえる」と言いながら全文を渡していた。** 聞こえ方は
    3 段階あるのに、近い (全文) と遠い (伏せる) の両端だけが機能していて、
    **中間が近いほうと同じ**だった。段階が意味を持っていない。

    隣の部屋の会話を一言一句知っている世界では、**移動して話を聞きに行く
    理由が薄くなる**。これは節約ではなく、世界の壊れ方の話である。
    """
    text = (content or "").strip()
    if len(text) <= _OVERHEARD_CHARS:
        return text
    return f"{text[:_OVERHEARD_CHARS]}…"


class PlayerObservationFormatter:
    """PlayerLocationChangedEvent / ItemAddedToInventoryEvent / PlayerSpokeEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def _death_semantics(self):
        return getattr(self._context, "death_semantics", None)

    def _announce_globally(self) -> bool:
        semantics = self._death_semantics()
        return True if semantics is None else bool(semantics.announce_globally)

    def _victim_learns_killer(self) -> bool:
        semantics = self._death_semantics()
        return True if semantics is None else bool(semantics.victim_learns_killer)

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
            is_departed = self._context.is_departed_after_downed(recipient_id)
            prose = (
                "死亡した後も移動できる。生きている者には姿が見えず、"
                "声も届かない。"
                if is_departed
                else "倒れて動けなくなった。"
            )
            # シナリオが匿名の通知文を宣言している世界では、直後に加害者名が
            # 届くと**匿名にした意味が消える**。実 run で衝突した
            # (「闇の中で強い衝撃を受けた。誰にやられたのか分からない。」の
            # 次の行に加害者名が並んだ)。
            learns_killer = self._victim_learns_killer()
            if killer_name and learns_killer:
                prose = f"{killer_name}があなたを倒した。"
                if is_departed:
                    prose += (
                        "死亡した後も移動できる。生きている者には姿が見えず、"
                        "声も届かない。"
                    )
            structured = {"type": "player_downed", "role": "self"}
            # 宣言は prose と structured の両方に効かせる。
            #
            # 片方だけだと、**読む側が増えたときに静かに破れる**。いまは
            # cue 抽出 (episodic_cue_rules) がこの key を読んでいないので
            # 実害は無いが、「読まれていないから残してよい」は消費者が
            # 1 つ増えた瞬間に成り立たなくなる。
            if learns_killer:
                structured["killer_player_id"] = killer_id
            return ObservationOutput(
                prose=prose,
                structured=structured,
                observation_category="self_only",
                schedules_turn=True,
                breaks_movement=True,
            )
        victim_same_spot = self._is_same_spot(recipient_id, event.aggregate_id)
        if victim_same_spot is not True:
            structured = {
                "type": "player_downed",
                "actor": self._context.name_resolver.player_name(event.aggregate_id),
                "killer_visible_to_recipient": False,
                "proximity": "remote_or_unknown",
            }
            if not self._announce_globally():
                # 隠密殺人のある世界。倒れた瞬間に全員が知るなら、死体を
                # 見つける意味も通報する意味も無い。
                return None
            return ObservationOutput(
                prose="遠くで誰かが倒れた気配がした。",
                structured=structured,
                observation_category="social",
                schedules_turn=True,
            )
        # Issue #185: 第三者観測の killer 視認チェック。
        # killer の位置が recipient と同じ spot で、実効照明が身元を見分けられる
        # ときだけ killer 名を出す。
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
                lighting = self._context.resolve_effective_lighting(recipient_spot)
                killer_visible = self._lighting_reveals_killer_to_bystander(lighting)
        actor_name = self._context.name_resolver.player_name(event.aggregate_id)
        if killer_visible and killer_name:
            prose = f"{killer_name}が{actor_name}を倒した。"
        else:
            prose = f"{actor_name}が倒れて動かなくなった。"
        if getattr(
            event,
            "declared_witness_prose_replaces_bystander_prose",
            False,
        ) and (
            killer_player_id is None
            or recipient_id.value != killer_player_id.value
        ):
            # 同じ一撃の宣言済み目撃文が第三者へ届く場合だけ、重複する汎用文を
            # 表示しない。行為者本人は目撃配信から除外されるので省かない。
            # structured は分析のため下で通常どおり組み立てる。
            prose = ""
        structured = {
            "type": "player_downed",
            "actor": actor_name,
            "killer_visible_to_recipient": killer_visible,
            "proximity": "same_spot" if victim_same_spot else "remote_or_unknown",
        }
        # prose で伏せた身元を structured から復元できる状態にしない。
        # 読む側が増えても同じ秘匿境界を保つため、視認できるときだけ ID を運ぶ。
        if killer_visible:
            structured["killer_player_id"] = killer_id
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    @staticmethod
    def _lighting_reveals_killer_to_bystander(lighting: object) -> bool:
        """第三者が加害者の顔を見分けられる明るさかを答える。

        現在の明所集合は、宣言観測の明所文選択および
        ``SpotPerceptionService.can_see_objects`` と同じだが、三つは別の問いで
        ある。一つの都合で閾値を変えるときは、残る二つも意図的に見直すこと。
        不明な値は身元を伏せる側へ倒す。
        """
        return lighting in (LightingEnum.BRIGHT, LightingEnum.DIM)

    def _format_player_revived(
        self, event: PlayerRevivedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        is_self = event.aggregate_id.value == recipient_id.value
        if is_self:
            prose = "復帰しました。"
            structured = {"type": "player_revived", "role": "self"}
            # schedules_turn 網羅性 audit (#404): 復帰直後は「行動可能」に状態
            # 遷移したばかりなので即時にターンを積む。per-agent idle timer 下で
            # 復帰観測だけ届いて idle_timeout 経過まで眠るのは silent failure。
            return ObservationOutput(
                prose=prose,
                structured=structured,
                observation_category="self_only",
                schedules_turn=True,
            )
        actor_name = self._context.name_resolver.player_name(event.aggregate_id)
        same_spot = self._is_same_spot(recipient_id, event.aggregate_id)
        if same_spot is not True:
            prose = "遠くで誰かが動けるようになった気配がした。"
            proximity = "remote_or_unknown"
        else:
            prose = f"{actor_name}が復帰しました。"
            proximity = "same_spot" if same_spot else "remote_or_unknown"
        structured = {
            "type": "player_revived",
            "actor": actor_name,
            "proximity": proximity,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _is_same_spot(
        self, recipient_id: PlayerId, actor_id: PlayerId
    ) -> Optional[bool]:
        """recipient と actor が同じ spot にいるかを返す。位置不明なら None。"""
        recipient_spot = self._context.lookup_recipient_spot(recipient_id)
        actor_spot = self._context.lookup_recipient_spot(actor_id)
        if recipient_spot is None or actor_spot is None:
            return None
        return recipient_spot == actor_spot

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
            departed_store = self._context.departed_position_store
            speaker_departed_spot = (
                departed_store.find(PlayerId.create(int(event.aggregate_id.value)))
                if departed_store is not None
                else None
            )
            listener_departed_spot = (
                departed_store.find(recipient_id)
                if departed_store is not None
                else None
            )
            try:
                speaker_spot = (
                    speaker_departed_spot
                    if speaker_departed_spot is not None
                    else graph.get_entity_spot(speaker_eid)
                )
                listener_spot = (
                    listener_departed_spot
                    if listener_departed_spot is not None
                    else graph.get_entity_spot(listener_eid)
                )
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
                        or speaker_spot != listener_spot
                    ):
                        return None
                    clarity = SoundClarityEnum.CLEAR
                else:
                    volume = speech_channel_to_sound_volume(event.channel)
                    if (
                        speaker_departed_spot is not None
                        or listener_departed_spot is not None
                    ):
                        outcome = svc.outcome_between_spots(
                            speaker_spot, listener_spot, volume, graph
                        )
                    else:
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
                        f"「{_overheard_fragment(event.content)}」"
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
                if clarity == SoundClarityEnum.MUFFLED:
                    # **聞こえた通りを残す。** 構造化側に全文を置くと、
                    # 記憶や分析にだけ完全な書き起こしが残り、prose と
                    # 食い違う (どちらが本当に聞こえたのか分からなくなる)。
                    structured["content"] = _overheard_fragment(event.content)
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
        # schedules_turn 網羅性 audit (#404): overflow は「アイテムが入らずに
        # 消失した」相当の致命イベント。捨てる/装備し直すなどの即時対応が要る
        # ので idle timer に待たせない。
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )
