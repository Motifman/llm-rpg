"""オブジェクト・接続・状態変化系イベントの formatter。

SpotObjectInteracted/Failed/StateChanged, ConnectionChanged/Created/Destroyed,
PublicEffectObserved, SpotPlayerStateChangedInSpot をまとめて扱う。
環境変化系は `observation_category="environment"`、社会的観測は `social`。
"""

import logging

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters.declaration_visibility import (
    declaration_hides_actor,
)
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
    PlayerDroppedItemEvent,
    PlayerGaveItemEvent,
    MarketBoardActivityEvent,
    MarketDeliveryLeftAtBoardEvent,
    PlayerOverflowedItemEvent,
    PlayerTradeOfferEvent,
    PlayerTradedWithMerchantEvent,
    PlayerPickedUpItemEvent,
    PlayerInteractedWithPlayerEvent,
    SpotObjectInteractedEvent,
    SpotObjectInteractionFailedEvent,
    SpotObjectStateChangedEvent,
    SpotPlayerStateChangedInSpotEvent,
    SpotPublicEffectObservedEvent,
    TimeOfDayChangedEvent,
    GamePhaseChangedEvent,
    MeetingVoteCastEvent,
    MeetingVoteResolvedEvent,
)
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
)

logger = logging.getLogger(__name__)


class SpotGraphObjectHandler(_SpotGraphFormatterBase):
    """オブジェクト/接続/状態変化系の formatter。"""

    def format(
        self, event: Any, recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, SpotObjectInteractedEvent):
            return self._format_object_interacted(event, recipient_player_id)
        if isinstance(event, PlayerInteractedWithPlayerEvent):
            return self._format_player_interacted(event, recipient_player_id)
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
        if isinstance(event, PlayerDroppedItemEvent):
            return self._format_item_dropped(event, recipient_player_id)
        if isinstance(event, PlayerPickedUpItemEvent):
            return self._format_item_picked_up(event, recipient_player_id)
        if isinstance(event, PlayerGaveItemEvent):
            return self._format_item_given(event, recipient_player_id)
        if isinstance(event, PlayerTradedWithMerchantEvent):
            return self._format_merchant_trade(event, recipient_player_id)
        if isinstance(event, PlayerTradeOfferEvent):
            return self._format_player_trade(event, recipient_player_id)
        if isinstance(event, MarketBoardActivityEvent):
            return self._format_market_activity(event, recipient_player_id)
        if isinstance(event, PlayerOverflowedItemEvent):
            return self._format_item_overflowed(event, recipient_player_id)
        if isinstance(event, MarketDeliveryLeftAtBoardEvent):
            return self._format_delivery_left_at_board(event, recipient_player_id)
        if isinstance(event, TimeOfDayChangedEvent):
            return self._format_time_of_day_changed(event, recipient_player_id)
        if isinstance(event, GamePhaseChangedEvent):
            return self._format_game_phase_changed(event, recipient_player_id)
        if isinstance(event, MeetingVoteCastEvent):
            return self._format_meeting_vote_cast(event, recipient_player_id)
        if isinstance(event, MeetingVoteResolvedEvent):
            return self._format_meeting_vote_resolved(event, recipient_player_id)
        return None

    #: 会議が始まったときに全員へ届く文。
    #:
    #: **できることが変わったことを、切り替わった瞬間に伝える。** 状態行は
    #: 「いまも会議中」を伝えるが、切り替わりは 1 度きりで、そのときに一番
    #: 強く読まれる。実 run 009 では会議中に作業を試みる者が続き、思考にも
    #: 「話し合い中だけど、私の担当の棚卸しをまず進めたい」と出ていた。
    #:
    #: 具体的なツール名は書かない。会議で出るツールは世界によって違い、
    #: 名前を書くと落とした世界で嘘になる (#892 / #920)。
    _MEETING_START_SUFFIX = "ここでできるのは、話すことと投票だけになった。"

    @staticmethod
    def _meeting_prose(table: dict, reason: str, *, fallback: str) -> str:
        """会議の理由に対応する文を返す。**未知なら静かに倒れず warning を出す。**

        ## なぜ例外にしないか (系統4)

        #1035 (屋内判定) では例外を投げる判断をした。あちらは「配信先を間違える」=
        **世界が嘘をつく**失敗だった。こちらは「言い方が漠然とする」= 世界が曖昧に
        なるだけで嘘ではない。**表示の粒度のために world を止めない。**

        代わりに warning で見えるようにし、**そもそも未知が来ないこと**を網羅テスト
        (`tests/application/observation/test_meeting_prose_covers_every_reason.py`)
        で保証する。理由の集合は `MeetingStartTrigger` / `MeetingEndReason` なので、
        テストが通れば実行時に未知は来ない。

        以前は `.get(reason, fallback)` で**何も残らなかった**ため、理由を足して表に
        書き忘れたことが誰にも見えなかった。
        """
        text = table.get(reason)
        if text is not None:
            return text
        logger.warning(
            "会議の理由に対応する観測文が無いため汎用文へ倒した: reason=%s",
            reason,
        )
        return fallback

    _MEETING_TRIGGER_PROSE = {
        "emergency_button": "{who}が緊急招集をかけた。全員が集まる。",
        "body_report": "{who}が倒れている者を見つけたと知らせた。全員が集まる。",
    }
    _MEETING_END_PROSE = {
        "vote_concluded": "話し合いが終わった。各自の持ち場に戻る。",
        "silence": "誰も口を開かなくなった。話し合いは流れた。",
        "tick_limit": "時間切れだ。話し合いは打ち切られた。",
    }

    def _format_meeting_vote_cast(
        self, event: "MeetingVoteCastEvent", recipient_id: PlayerId,
    ) -> ObservationOutput:
        """締切前の投票進捗を、投票先を伏せて届ける。"""
        remaining = int(event.remaining_voter_count)
        if remaining:
            progress = f"まだ {remaining} 人が投票していない。"
        else:
            progress = "全員が投票を済ませた。"
        return ObservationOutput(
            prose=f"{event.voter_display_name}が投票を済ませた。{progress}",
            structured={
                "type": "meeting_vote_cast",
                "voter_display_name": event.voter_display_name,
                "remaining_voter_count": remaining,
            },
            observation_category="social",
            schedules_turn=True,
        )

    def _format_meeting_vote_resolved(
        self, event: "MeetingVoteResolvedEvent", recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """投票の集計を全員に届ける。

        **追放が起きなかった場合も同じ文を出す。** 出さないと「誰も追放
        されなかった」のか「誰かが追放されたが自分は見ていなかった」のかを
        区別できない (設計 doc §6.4)。

        誰が誰に入れたかまで出すのは、投票行動そのものが次の会議の材料に
        なるため。
        """
        tally = "、".join(
            f"{name} {n} 票" for name, n in event.counts_by_display_name.items()
        )
        parts = ["投票が終わった"]
        if tally:
            parts.append(f"{tally}")
        if event.skip_count:
            parts.append(f"棄権 {event.skip_count} 票")
        head = "。".join(p for p in parts if p)
        if event.ejected_display_name:
            tail = f"{event.ejected_display_name}が追放された。"
        elif not event.counts_by_display_name and not event.skip_count:
            # **1 票も入っていないのに「割れた」と言わない。** 「割れた」は
            # 票が入って拮抗したという意味なので、読んだ側は「他の誰かは
            # 投票したが意見が分かれた」と受け取る。実際は全員が投票しな
            # かっただけで、次に取るべき手はまったく違う。
            # 実 run (station_drill_003) で実際にこの食い違いが出た。
            tail = "誰も票を投じないまま終わった。"
        elif not event.counts_by_display_name:
            # 全員が棄権した場合。棄権は保留するという意思表示であって
            # 票の不在ではない (設計 doc §2.3) が、名指しが 1 つも無い以上
            # 「割れた」でもない。
            tail = "名指しの票はなく、誰も追放されなかった。"
        else:
            top = max(event.counts_by_display_name.values())
            leaders = [
                name
                for name, count in event.counts_by_display_name.items()
                if count == top
            ]
            if len(leaders) > 1:
                tail = "最多票が同数に割れ、誰も追放されなかった。"
            elif event.skip_count >= top:
                relation = "上回り" if event.skip_count > top else "並び"
                tail = f"棄権が最多票を{relation}、誰も追放されなかった。"
            else:
                tail = "誰も追放されなかった。"
        return ObservationOutput(
            prose=f"{head}。{tail}",
            structured={
                "type": "meeting_vote_resolved",
                "ejected_display_name": event.ejected_display_name,
                "counts": dict(event.counts_by_display_name),
                "skip_count": event.skip_count,
                "ballots": dict(event.ballots_by_display_name),
            },
            observation_category="social",
            schedules_turn=True,
        )

    def _format_game_phase_changed(
        self, event: "GamePhaseChangedEvent", recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """世界のモード変化を全員に届ける。

        誰が招集したかを出すのは、**それ自体が推理の材料になる**ため。
        緊急ボタンを押した人は疑いの的にも信頼の的にもなる。

        ``schedules_turn`` と ``breaks_movement`` を立てるのは必須である。
        前者が False だと会議が始まっても誰も起きず沈黙上限で即終了し、
        後者が False だと会議中に歩き続けるプレイヤーが出る
        (設計 doc H-4 / H-2)。
        """
        who = (event.initiator_display_name or "").strip()
        if event.new_phase is GamePhase.MEETING:
            template = self._meeting_prose(
                self._MEETING_TRIGGER_PROSE,
                event.trigger,
                fallback="招集がかかった。全員が集まる。",
            )
            prose = template.format(who=who) if who else "招集がかかった。全員が集まる。"
            prose = f"{prose}{self._MEETING_START_SUFFIX}"
        else:
            prose = self._meeting_prose(
                self._MEETING_END_PROSE,
                event.trigger,
                fallback="話し合いが終わった。各自の持ち場に戻る。",
            )
        return ObservationOutput(
            prose=prose,
            structured={
                "type": "game_phase_changed",
                "old_phase": event.old_phase.value,
                "new_phase": event.new_phase.value,
                "trigger": event.trigger,
                "initiator_display_name": who,
            },
            observation_category="social",
            schedules_turn=True,
            breaks_movement=True,
        )

    def _format_time_of_day_changed(
        self, event: TimeOfDayChangedEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """昼夜のフェーズが変化したとき、全プレイヤーに「夕暮れになった」等を届ける。

        recipient strategy で全 player に配信される (本人除外なし、世界全体
        の出来事のため)。
        """
        prose = f"{event.new_display_text}になった。"
        structured = {
            "type": "time_of_day_changed",
            "old_phase_name": event.old_phase_name,
            "new_phase_name": event.new_phase_name,
            "new_display_text": event.new_display_text,
            "new_is_dark": event.new_is_dark,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
        )

    def _format_item_given(
        self, event: PlayerGaveItemEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """「ミラが流木をトマに渡した」を同室の他プレイヤー (受け手含む) に届ける。

        recipient strategy で送り手 entity_id は除外されているので、本 formatter
        が呼ばれる時点で recipient_id は送り手ではない。受け手本人 (recipient_id
        == event.recipient_entity_id) には自分宛の動作だが、prose は三人称的に
        統一する (LLM 視点で観測ログは一貫した語り口を取りたいため)。

        schedules_turn=True: 受け手は所持品が増えた時点で次の手が変わる
        (受け取った食料を食べる / 資材を火起こしに使う)。say_inline を伴わない
        give は #412 の audit 漏れで同席者を起こせておらず、渡した資材が
        idle_timeout まで使われない停滞を生んでいた。
        """
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        receiver = self._resolve_entity_name(event.recipient_entity_id)
        prose = f"{actor}が{event.item_name}を{receiver}に渡した。"
        structured = {
            "type": "player_gave_item",
            "actor": actor,
            "receiver": receiver,
            "item_name": event.item_name,
            "item_instance_id": event.item_instance_id.value,
            "item_spec_id": event.item_spec_id.value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _format_player_trade(
        self, event: PlayerTradeOfferEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """人同士の取引の動きを、立場に応じた文で届ける。

        持ちかけと成立は**中身つきで第三者にも**見せる。誰が何を欲しがって
        いるかは、その人が何をしようとしているかの手がかりで、経済の観測を
        厚くしたい Phase 2 では見せる価値が勝つ。

        辞退と期限切れは当事者だけに届ける。断りや沈黙まで公開すると観測が
        増えるわりに得るものが薄い。期限切れで target にも届けるのは、
        「自分宛ての申し出」が状況確認から黙って消えるのを避けるため。
        """
        actor = self._resolve_entity_name(event.entity_id)
        partner = self._resolve_entity_name(event.partner_entity_id)
        is_party = self._is_self(event.entity_id, recipient_id) or self._is_self(
            event.partner_entity_id, recipient_id
        )
        if event.kind in ("declined", "expired") and not is_party:
            return None
        if event.kind == "offered":
            if self._is_self(event.entity_id, recipient_id):
                return None
            prose = (
                f"{actor}が{partner}に取引を持ちかけた "
                f"({event.gives_text} ⇄ {event.asks_text})。"
            )
        elif event.kind == "accepted":
            if self._is_self(event.entity_id, recipient_id):
                return None
            prose = (
                f"{actor}と{partner}の取引が成立した "
                f"({event.gives_text} ⇄ {event.asks_text})。"
            )
        elif event.kind == "declined":
            if self._is_self(event.entity_id, recipient_id):
                return None
            prose = f"{actor}は持ちかけられた取引を断った。"
        else:  # expired
            # **立場で文が変わるので、actor / partner ではなく持ちかけた側を
            # 明示して組む。** entity_id は返事をしなかった側 (target) なので、
            # そのまま actor として書くと「持ちかけた人」が入れ替わる。
            offerer_name = (
                self._resolve_entity_name(event.offerer_entity_id)
                if event.offerer_entity_id is not None
                else partner
            )
            offerer_is_recipient = event.offerer_entity_id is not None and self._is_self(
                event.offerer_entity_id, recipient_id
            )
            if offerer_is_recipient:
                prose = f"{actor}からの返事がないまま、持ちかけた取引は流れた。"
            else:
                prose = f"{offerer_name}が持ちかけていた取引は、返事をしないまま流れた。"
        return ObservationOutput(
            prose=prose,
            structured={
                "type": "player_trade_offer",
                "kind": event.kind,
                "actor": actor,
                "partner": partner,
                "gives": event.gives_text,
                "asks": event.asks_text,
            },
            observation_category="social",
            # 持ちかけは**持ちかけられた本人の**手番だけを起こす (会話と同じ)。
            # 第三者まで起こすと、交渉のたびに同席者全員が動いて行動密度が
            # 跳ね上がり、しかも起こされた側には打つ手が無い。
            schedules_turn=(
                event.kind == "offered"
                and self._is_self(event.partner_entity_id, recipient_id)
            ),
        )

    def _format_delivery_left_at_board(
        self, event: MarketDeliveryLeftAtBoardEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """買い注文で届いた品を受け取れなかったことを、買い手へ届ける。

        **「取り落とした」とは別の文にする。** 落としたのは本人の不注意では
        なく、届いた品を受け取れなかっただけ。混ぜると、自分が何かを失敗した
        ように読める。

        gold は既に払われているので、届かないままだと**払ったのに品が無い**
        状態になる。どこにあるかを必ず伝える。

        **場所は名前で言う。** 板がどこからでも届く世界では、品が置かれるのは
        自分が一度も行っていない場所になりうる。「掲示板の足元」だけだと、板の
        在り処を知らない人には行き先が決まらない。
        """
        where = self._resolve_spot_name(event.spot_id)
        return ObservationOutput(
            prose=(
                f"買い注文の{event.item_name}が届いたが、持ちきれず"
                f"{where}の掲示板の足元に置かれた。"
                f"空きを作って拾いに行けば受け取れる。"
            ),
            structured={
                "type": "market_delivery_left_at_the_board",
                "item_name": event.item_name,
                "item_instance_id": event.item_instance_id.value,
                "item_spec_id": event.item_spec_id.value,
            },
            observation_category="social",
            # 手番は起こさない。知って、次の自分の手番で取りに行けばよい。
            schedules_turn=False,
        )

    def _format_item_overflowed(
        self, event: PlayerOverflowedItemEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """持ちきれずに落ちたことを、本人にも同席者にも届ける。

        **意図して置いたのとは別の文にする。** 地面に物が増えるのは同じでも、
        拾ってよいかの読みが変わる。置いたものは誰かのための置き方かもしれないが、
        取り落としたものは本人が拾い直したいはずで、そこを潰すと親切のつもりの
        持ち去りが増える。

        本人にも届けるのは、**採取の結果が手元に無い理由がここでしか分からない**
        ため。届かないと「拾ったのに増えていない」まま次の手を決めることになる。
        """
        actor = self._resolve_entity_name(event.entity_id)
        if self._is_self(event.entity_id, recipient_id):
            prose = (
                f"持ちきれず、{event.item_name}を足元に取り落とした。"
                f"拾い直すには先に何かを手放す必要がある。"
            )
        else:
            prose = f"{actor}が持ちきれず、{event.item_name}を取り落とした。"
        return ObservationOutput(
            prose=prose,
            structured={
                "type": "player_overflowed_item",
                "actor": actor,
                "item_name": event.item_name,
                "item_instance_id": event.item_instance_id.value,
                "item_spec_id": event.item_spec_id.value,
            },
            observation_category="social",
            # 手番は起こさない。落ちたことを知って、次の自分の手番で拾い直すか
            # 決めればよい。採取のたびに同席者全員が動くと行動密度が跳ね上がる。
            schedules_turn=False,
        )

    def _format_market_activity(
        self, event: MarketBoardActivityEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """板の上の動きを、読む人の立場に応じた文で届ける。

        値は必ず文面に出す。**値付けを見て自分の値を決める**のが市場の要で、
        いくらで出したか・いくらで売れたかが見えないと、値動きを追えない。

        値の付け直しは旧値と新値の両方を出す。「下げた」という方向が読める
        ことに意味があり、新値だけだと値が動いたのか最初からその値だったのか
        区別できない。
        """
        actor = self._resolve_entity_name(event.entity_id)
        item = event.item_name
        kind = event.kind
        is_owner = (
            event.notify_entity_id is not None
            and self._is_self(event.notify_entity_id, recipient_id)
        )

        if kind == "listed":
            if self._is_self(event.entity_id, recipient_id):
                return None
            # **売りと買いで文を分ける。** どちらも「掲示板に出した」だが、
            # 読む側にとっては真逆の機会になる (買える / 売れる)。
            prose = (
                f"{actor}が掲示板に{item}を{event.quantity}つ、"
                f"1つ{event.unit_price}Gで買うと出した。"
                if event.side == "buy"
                else f"{actor}が掲示板に{item}を{event.quantity}つ、"
                f"1つ{event.unit_price}Gで出した。"
            )
        elif kind == "repriced":
            if self._is_self(event.entity_id, recipient_id):
                return None
            direction = (
                "下げた"
                if event.old_unit_price is not None
                and event.unit_price < event.old_unit_price
                else "上げた"
            )
            prose = (
                f"{actor}が{item}の値を 1 つ {event.old_unit_price}G から "
                f"{event.unit_price}G へ{direction}。"
            )
        elif kind == "bought":
            seller = (
                self._resolve_entity_name(event.counterparty_entity_id)
                if event.counterparty_entity_id is not None
                else "誰か"
            )
            if is_owner and not self._is_at_the_board(event, recipient_id):
                # 板に居ないときは、自分の身に起きたこととして届ける。
                # 買い注文が受けられた側は「買えた」、売り注文が受けられた
                # 側は「売れた」で、立場が逆になる。
                prose = (
                    f"掲示板の買い注文に{item}が{event.quantity}つ、"
                    f"1つ{event.unit_price}Gで売られた ({actor}が売った)。"
                    if event.side == "buy"
                    else f"掲示板に出していた{item}が{event.quantity}つ、"
                    f"1つ{event.unit_price}Gで売れた ({actor}が買った)。"
                )
            else:
                if self._is_self(event.entity_id, recipient_id):
                    return None
                prose = (
                    f"{actor}が掲示板の{seller}の買い注文へ{item}を"
                    f"{event.quantity}つ、1つ{event.unit_price}Gで売った。"
                    if event.side == "buy"
                    else f"{actor}が掲示板から{seller}の{item}を{event.quantity}つ、"
                    f"1つ{event.unit_price}Gで買った。"
                )
        elif kind == "cancelled":
            if self._is_self(event.entity_id, recipient_id):
                return None
            what = "買い注文" if event.side == "buy" else "出品"
            prose = f"{actor}が{item}の{what}を取り下げた。"
        elif kind == "expired_returned":
            prose = (
                f"掲示板に出していた{item}の期限が切れ、{event.quantity}つが"
                f"手元に戻った。"
            )
        else:  # expired_awaiting
            # **状態で文を分ける。** 手元に戻ったのか、板で引き取りを待って
            # いるのかで次の一手が違う (何もしなくてよい / 空けて引き取りに行く)。
            prose = (
                f"掲示板に出していた{item}の期限が切れたが、持ち物がいっぱいで"
                f"引き取れず、{event.quantity}つは板に残っている。"
                f"空きを作ってから取り下げれば引き取れる。"
            )
        return ObservationOutput(
            prose=prose,
            structured={
                "type": "market_board_activity",
                "kind": kind,
                "side": event.side,
                "actor": actor,
                "item_name": item,
                "quantity": event.quantity,
                "unit_price": event.unit_price,
                "old_unit_price": event.old_unit_price,
            },
            observation_category="social",
            # 板の動きで手番は起こさない。知って、次の自分の手番で動けばよい。
            # 誰かの出品や値下げのたびに同席者全員が動くと、行動密度が跳ね
            # 上がる。売れた通知も同じで、起こされた側にその場でできることは
            # 無い (板から離れているのだから)。
            schedules_turn=False,
        )

    def _is_at_the_board(
        self, event: MarketBoardActivityEvent, recipient_id: PlayerId,
    ) -> bool:
        """その人が、出来事の起きた場所に居るか。

        同じ約定でも、板の前に居る人には「トムがレナのパンを買った」、離れて
        いる売り手には「自分の出していたパンが売れた」と、立場で文が変わる。
        """
        try:
            return self._context.lookup_recipient_spot(recipient_id) == event.spot_id
        except Exception:  # noqa: BLE001
            return False

    def _format_merchant_trade(
        self, event: PlayerTradedWithMerchantEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """「ミラが商人グスタフからパンを 2 つ買った」を同席の第三者に届ける。

        schedules_turn=False: 相手は NPC で起こす手番が無く、第三者にとっても
        「隣で誰かが買い物をした」は自分の次の一手を変えない。give_item を
        True にしたのは、**受け手の持ち物が増えて次の手が変わる**からで、
        こちらにはその関係が無い。

        ただし観測としては配る。誰が何を買い、何を売ったかは、その人が何を
        しようとしているかの手がかりになる (agent_design_principles の
        「他者からの可視性」)。
        """
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        if event.direction == "merchant_sell":
            prose = (
                f"{actor}が{event.merchant_name}に{event.item_name}を"
                f"{event.quantity}つ売った。"
            )
        else:
            prose = (
                f"{actor}が{event.merchant_name}から{event.item_name}を"
                f"{event.quantity}つ買った。"
            )
        structured = {
            "type": "player_traded_with_merchant",
            "actor": actor,
            "merchant_name": event.merchant_name,
            "item_name": event.item_name,
            "item_spec_id": event.item_spec_id.value,
            "quantity": event.quantity,
            "direction": event.direction,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=False,
        )

    def _format_item_dropped(
        self, event: PlayerDroppedItemEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """「ミラが流木を地面に置いた」を同室の他プレイヤーに観測として届ける。

        schedules_turn=True: 目の前に資材が現れた = 拾える状態への遷移なので、
        harvest 完了と同じ扱いで即起床させる。
        """
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        prose = f"{actor}が{event.item_name}を地面に置いた。"
        structured = {
            "type": "player_dropped_item",
            "actor": actor,
            "item_name": event.item_name,
            "item_instance_id": event.item_instance_id.value,
            "item_spec_id": event.item_spec_id.value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _format_item_picked_up(
        self, event: PlayerPickedUpItemEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """「トマが流木を拾い上げた」を同室の他プレイヤーに観測として届ける。

        schedules_turn=True: 狙っていた地面の資材が消えた = 計画の前提が崩れた
        ので、harvest 中断と同じ扱いで即起床させ別の手を選ばせる。
        """
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        prose = f"{actor}が{event.item_name}を拾い上げた。"
        structured = {
            "type": "player_picked_up_item",
            "actor": actor,
            "item_name": event.item_name,
            "item_instance_id": event.item_instance_id.value,
            "item_spec_id": event.item_spec_id.value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _format_object_interacted(
        self, event: SpotObjectInteractedEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        obj_name = self._resolve_object_name(event.spot_id, event.object_id)
        prose, witness_source = self._format_object_interacted_prose(
            event, actor=actor, obj_name=obj_name,
        )
        structured = {
            "type": "spot_object_interacted",
            "actor": actor,
            "object_name": obj_name,
            "action_name": event.action_name,
            "action_display_label": event.action_display_label,
            "witness_observation_message": event.witness_observation_message,
            "witness_observation_source": witness_source,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            schedules_turn=True,
        )

    def _format_player_interacted(
        self, event: "PlayerInteractedWithPlayerEvent", recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        """対人行為の目撃 / 被害の観測を作る。

        行為者本人には返さない (本人は tool 結果で結果を受け取っている)。
        **対象本人には返す** — 自分が何をされたのかは、第三者の目撃より先に
        知る必要がある。倒れている間の出来事でも、起きたときに何が起きたのか
        を読めなければ、持ち物が減った理由が永久に分からない。
        """
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        target = self._resolve_entity_name(event.target_entity_id)
        is_target = self._is_self(event.target_entity_id, recipient_id)
        message = (event.witness_observation_message or "").strip()
        label = (event.action_display_label or "").strip()
        if message:
            prose, source = self._render_player_witness_message(
                message, actor=actor, target=target, action_display_label=label
            ), "scenario"
        elif label:
            prose, source = (
                f"{actor}が{target}に「{label}」を行った。", "display_label",
            )
        else:
            prose, source = f"{actor}が{target}に何かをした。", "legacy"
        if is_target:
            target_message = (
                getattr(event, "target_observation_message", "") or ""
            ).strip()
            if target_message:
                # 対象専用の文面がある場合はそちらを使う。秘匿行為で
                # 「誰にやられたか」を伏せるために、目撃者向けとは別に
                # 書けるようにしてある (可視性の 3 軸目)。
                prose, source = self._render_player_witness_message(
                    target_message,
                    actor=actor,
                    target=target,
                    action_display_label=label,
                ), "scenario_target"
            else:
                # 対象本人には「誰かが自分に何かをした」と分かる形で届ける。
                prose = f"{prose} (あなたが対象だった)"
        structured = {
            "type": "player_interacted_with_player",
            "target": target,
            "action_name": event.action_name,
            "action_display_label": event.action_display_label,
            "is_target": is_target,
            "witness_observation_source": source,
        }
        if is_target or not declaration_hides_actor(message):
            structured["actor"] = actor
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
            # 被害者も目撃者も起きる。起きないと「持ち物が消えた」ことに
            # 反応する機会そのものが無い。
            schedules_turn=True,
        )

    @staticmethod
    def _render_player_witness_message(
        message: str, *, actor: str, target: str, action_display_label: str,
    ) -> str:
        """対人行為の目撃者文面に placeholder を展開する。"""
        if "{" not in message:
            return message
        try:
            return message.format(
                actor=actor,
                target=target,
                target_name=target,
                action=action_display_label,
                action_display_label=action_display_label,
            )
        except (KeyError, IndexError, ValueError):
            # 未知の placeholder は作家の書き間違い。展開せず素の文面を返す
            # (観測そのものを落とすより、崩れた文面でも届く方が良い)。
            return message

    def _format_object_interacted_prose(
        self, event: SpotObjectInteractedEvent, *, actor: str, obj_name: str,
    ) -> tuple[str, str]:
        """成功時の目撃者 prose を scenario 宣言 → 表示ラベル → 従来文の順で作る。"""
        message = (event.witness_observation_message or "").strip()
        action_display_label = (event.action_display_label or "").strip()
        if message:
            return (
                self._render_witness_observation_message(
                    message,
                    actor=actor,
                    obj_name=obj_name,
                    action_display_label=action_display_label,
                ),
                "scenario",
            )
        if action_display_label:
            return f"{actor}が「{action_display_label}」を行った。", "display_label"
        return f"{actor}が{obj_name}を操作した。", "legacy"

    def _render_witness_observation_message(
        self, message: str, *, actor: str, obj_name: str, action_display_label: str,
    ) -> str:
        """scenario 宣言の目撃者文面に最小限の placeholder を展開する。"""
        if "{" not in message:
            return message
        try:
            return message.format(
                actor=actor,
                object=obj_name,
                object_name=obj_name,
                action=action_display_label,
                action_display_label=action_display_label,
            )
        except (KeyError, IndexError, ValueError):
            # 作家ミスで観測自体を落とすより、未展開の文面を出して trace 側から
            # 気づける状態を優先する。scenario loader 側では型だけ fail-fast する。
            return message

    def _format_interaction_failed(
        self, event: SpotObjectInteractionFailedEvent, recipient_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        # アクター本人にはツール結果として失敗が返るため、観測は他者にのみ。
        if self._is_self(event.entity_id, recipient_id):
            return None
        actor = self._resolve_entity_name(event.entity_id)
        obj_name = self._resolve_object_name(event.spot_id, event.object_id)
        # #356 後続: prose の優先順位
        # 1. シナリオ宣言 override (`observation_message`) があればそのまま
        # 2. 例外 reason (`failure_reason`) があれば自動構築
        # 3. どちらも無ければ silent (他者の学習材料にならない)
        override = event.observation_message or ""
        reason = getattr(event, "failure_reason", None) or ""
        if override:
            prose = override
        elif reason:
            # **識別子ではなくラベルを出す。** action_name は engine の語彙で、
            # 偽装版では `..._pretend` がそのまま漏れる (実 run で確認)。
            # 宣言の無い旧シナリオ向けに action_name へ落とす。
            shown = getattr(event, "display_label", "") or event.action_name
            prose = f"{actor}が{obj_name}の「{shown}」を試みたが、{reason}"
        else:
            return None
        structured = {
            "type": "spot_object_interaction_failed",
            "actor": actor,
            "object_name": obj_name,
            "action_name": event.action_name,
            "message": prose,
            "failure_reason": reason,
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
        # 著者が narrative を提供したときだけ observation を出す。無ければ
        # silent (= 内部用語 "available", "lit" 等が LLM に漏れない)。
        # interaction 由来の state 変化は SHOW_MESSAGE effect で別途
        # narrative を出している前提、reactive_binding は narrative_on_true /
        # narrative_on_false で宣言する前提 (#356 後続 finding)。
        narrative = getattr(event, "narrative", None)
        if not narrative:
            return None
        obj_name = self._resolve_object_name(event.spot_id, event.object_id)
        delta = (
            event.state_delta
            if event.state_delta
            else _derive_delta(event.old_state, event.new_state)
        )
        structured = {
            "type": "spot_object_state_changed",
            "object_name": obj_name,
            "state_delta": [
                {"key": d.key, "before": d.before, "after": d.after}
                for d in delta
            ],
        }
        return ObservationOutput(
            prose=narrative,
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
