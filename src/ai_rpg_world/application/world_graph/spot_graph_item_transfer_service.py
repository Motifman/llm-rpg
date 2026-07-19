"""スポットグラフ世界における drop / pickup の最小サービス。

タイルマップ時代の ItemDroppedFromInventoryDropHandler は ``physical_map``
依存で world_runtime / spot-graph 世界では発火しない (world_runtime
で ``physical_map_repository=None`` を渡している)。spot-graph 世界では
SpotInterior.ground_items にアイテムを置き、SpotInterior 経路で
プレイヤーが拾い直せる必要がある。

本サービスはそのための機械的動作 (インベントリ↔地面の状態遷移) と、
witness 最小版 (drop / pickup の事実を同スポットの他プレイヤーに観測として
配信する PlayerDroppedItemEvent / PlayerPickedUpItemEvent の発火) を担う。
LLM ツール配線は別経路で行う (本サービスは tool 経路にも runtime 直接呼び
出し経路にも共通で使われる)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from ai_rpg_world.application.common.events.domain_event_collector import (
    DomainEventCollector,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.exception.player_exceptions import (
    ItemNotInSlotException,
)
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerDroppedItemEvent,
    PlayerGaveItemEvent,
    PlayerPickedUpItemEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem

_logger = logging.getLogger(__name__)


class ItemTransferException(Exception):
    """drop/pickup/give の境界条件違反 (プレイヤー未配置・地面に存在しない 等)。

    LLM 面向けに error_code + 日本語 message を持つ子 class に分岐すべきだが、
    まだ子 class が用意されていない「稀な整合性違反」 (repository lookup 失敗
    など) は base のまま raise される。executor 側で fallback として
    ``ITEM_TRANSFER_FAILED`` にマップする。
    """

    #: LLM が受け取る error_code。子 class で override する。
    error_code: str = "ITEM_TRANSFER_FAILED"


class TargetIsSelfError(ItemTransferException):
    """give_item で自分自身を対象に指定した。

    LLM 向けの日本語 message を default で持つ (引数無しで raise 可)。
    """

    error_code = "GIVE_ITEM_TARGET_IS_SELF"

    def __init__(self, message: str = "自分自身にアイテムを渡すことはできません。別の相手を指定してください。") -> None:
        super().__init__(message)


class TargetNotInSameSpotError(ItemTransferException):
    """give_item の相手が別 spot にいる。

    ## message 二重管理の設計判断 (PR-α review MEDIUM 2)

    - **domain 層 (本 class)**: 汎用日本語 default message を持つ。名前を
      lookup する dependency を持たないため相手名/現在地名は default
      ("相手" / "現在地") のまま raise される
    - **executor 層 (spot_graph_tool_executor._give_item)**: catch 時に
      resolver が args に埋めた ``target_display_name`` を使って
      LLM-facing message を再構築する

    「exception の kwargs が使われず default 固定」だと duplication だが、
    domain 層で raise-site から名前を渡す経路が現状無いための割り切り。
    将来 transfer_service が player_name_resolver を注入されるようになれば、
    kwargs 経路が実 message 生成に使われるようになり duplication が解消する
    (LLM-facing の "最終形" は常に executor 側が作る前提)。
    """

    error_code = "GIVE_ITEM_TARGET_NOT_IN_SAME_SPOT"

    def __init__(
        self,
        *,
        target_name: str = "相手",
        sender_spot_name: str = "現在地",
    ) -> None:
        msg = (
            f"{target_name} は同じ場所にいません (あなたの現在地: {sender_spot_name})。"
            f"travel_to で移動してから再度渡してください。"
        )
        super().__init__(msg)
        self.target_name = target_name
        self.sender_spot_name = sender_spot_name


class SlotIsEmptyError(ItemTransferException):
    """drop_item / give_item で指定した inventory スロットが空だった。

    LLM が「持っていないアイテムのスロット番号」を指定した典型ケース。
    resolver の label→slot 変換が古い状態を参照した場合や、LLM が hallucinate
    した slot 番号でも起きる。message で inspect_target による inventory 再確認
    を促す。

    ``slot_id`` を kwargs で受けて message に埋めるので、executor 側で
    再構築しなくても LLM が「どの slot が空だったか」を読める。
    """

    error_code = "ITEM_TRANSFER_SLOT_IS_EMPTY"

    def __init__(self, *, slot_id: int) -> None:
        msg = (
            f"スロット {slot_id} には何も入っていません。"
            f"inspect_target で自分のインベントリを確認してから、"
            f"アイテムが実際に入っているスロット番号を指定してください。"
        )
        super().__init__(msg)
        self.slot_id = slot_id


class GroundItemGoneError(ItemTransferException):
    """pickup_item で拾おうとした地面アイテムが既に無かった。

    同 tick で複数プレイヤーが同じ地面アイテムに手を伸ばして片方が先に成功
    した場合や、observation が古くて既に他者が拾い終えている場合に起きる。
    LLM が同じ pickup を繰り返さないよう、他プレイヤーによる先取りの可能性と
    別行動 (explore で周囲を見直す / 目的を切り替える) を message で示唆する。
    """

    error_code = "PICKUP_ITEM_GROUND_ITEM_GONE"

    def __init__(self, *, item_name: str = "そのアイテム") -> None:
        msg = (
            f"{item_name} はもう地面にありません。"
            f"他のプレイヤーが先に拾ったか、あなたの観測が古い可能性があります。"
            f"explore で周囲を見直すか、別の目的に切り替えてください。"
        )
        super().__init__(msg)
        self.item_name = item_name


class PickupSelfInventoryFullError(ItemTransferException):
    """pickup_item で自分のインベントリが満杯だった。

    もともと ``PlayerInventoryAggregate.acquire_item`` は満杯時に silent に
    overflow event を出すだけで raise しない設計だったが、その結果
    「pickup した気になっているが実際は取れていない」silent failure が
    残っていた (地面からも消えて手元にも無い状態は防げているが、LLM は
    成功と誤認する)。PR-ε で service 側に事前ガードを追加し、明示的に
    この exception を raise する。

    LLM に対しては「先に何か drop して空きを作ってから再度 pickup」の
    次アクションを message で示唆する。
    """

    error_code = "PICKUP_ITEM_SELF_INVENTORY_FULL"

    def __init__(self, *, item_name: str = "そのアイテム") -> None:
        msg = (
            f"自分のインベントリが満杯で {item_name} を拾えません。"
            f"drop_item で不要なアイテムを 1 つ手放して空きを作ってから、"
            f"再度 pickup してください。"
        )
        super().__init__(msg)
        self.item_name = item_name


class TargetInventoryFullError(ItemTransferException):
    """give_item の相手のインベントリが満杯で受け取れない。

    message 二重管理の設計は ``TargetNotInSameSpotError`` と同方針
    (domain 層 default + executor 層で名前を差し込んで再構築)。
    """

    error_code = "GIVE_ITEM_TARGET_INVENTORY_FULL"

    def __init__(
        self,
        *,
        target_name: str = "相手",
        item_name: str = "そのアイテム",
    ) -> None:
        msg = (
            f"{target_name} のインベントリが満杯で {item_name} を受け取れません。"
            f"{target_name} が別のアイテムを drop するのを待つか、"
            f"別の相手に渡してください。"
        )
        super().__init__(msg)
        self.target_name = target_name
        self.item_name = item_name


@dataclass(frozen=True)
class ItemTransferResult:
    """drop/pickup の結果。messages はランナー/UI 用、instance_id は監査用。"""

    messages: tuple[str, ...]
    item_instance_id: ItemInstanceId
    spot_id: SpotId


class SpotGraphItemTransferService:
    """spot-graph 世界での drop / pickup を扱うアプリサービス。

    Phase 2 (witness 最小版): drop / pickup が成功したら同室の他プレイヤー向けに
    PlayerDroppedItemEvent / PlayerPickedUpItemEvent を発火する。観測パイプライン
    の recipient strategy が「同スポット・行為者除外」で配信する。
    event_publisher が None の構成では event を発火せず、機械的な状態遷移だけ
    行う (テスト・最小構成での後方互換)。
    """

    def __init__(
        self,
        *,
        spot_graph_repository: ISpotGraphRepository,
        player_inventory_repository: PlayerInventoryRepository,
        spot_interior_repository: ISpotInteriorRepository,
        item_repository: ItemRepository,
        event_publisher: Optional[object] = None,
    ) -> None:
        # spot-graph 世界では「プレイヤーがどこに居るか」は
        # PlayerStatusAggregate ではなく SpotGraphAggregate.get_entity_spot で
        # 解決する (status 側の current_spot_id は tile-map 由来で、
        # spot-graph runtime では更新されない)。
        self._spot_graph_repository = spot_graph_repository
        self._player_inventory_repository = player_inventory_repository
        self._spot_interior_repository = spot_interior_repository
        self._item_repository = item_repository
        # event_publisher は publish_all([event]) を持つ duck-typed オブジェクト。
        # 注入されない構成では event を発火せず、機械的な状態遷移だけ行う。
        self._event_publisher = event_publisher

    def set_event_publisher(self, event_publisher: Optional[object]) -> None:
        """event_publisher を後付けで注入する (二段構築用)。

        通常は constructor で渡すのが望ましいが、world_runtime のように
        publisher が runtime 本体に依存して構築順序的に後になるケースで使う。
        """
        self._event_publisher = event_publisher

    def drop_item(
        self,
        player_id: PlayerId,
        slot_id: SlotId,
        *,
        witness_policy: WitnessPolicy = WitnessPolicy.SAME_SPOT,
    ) -> ItemTransferResult:
        """指定スロットのアイテムをプレイヤーの現在地に落とす。

        ItemDroppedFromInventoryEvent は発火させない (tile-map handler が
        食ってしまうため)。代わりに本サービスが直接 SpotInterior に
        書き込む。

        witness_policy=ACTOR_ONLY を渡すと PlayerDroppedItemEvent に同 policy
        が乗り、recipient strategy が空集合を返す (誰も観測しない)。「こっそり
        落とす」を実現するための経路。default は SAME_SPOT で B-2a 互換。
        """
        inventory = self._player_inventory_repository.find_by_id(player_id)
        if inventory is None:
            raise ItemTransferException(
                f"inventory not found for player {player_id.value}"
            )

        item_instance_id = inventory.get_item_instance_id_by_slot(slot_id)
        if item_instance_id is None:
            # PR-ε: 空スロット指定は LLM 側の頻発ミス。汎用
            # ItemNotInSlotException では error_code / message が LLM に
            # 届かないので、drop / pickup 用の日本語 message + error_code
            # を持つ SlotIsEmptyError に差し替える。
            raise SlotIsEmptyError(slot_id=slot_id.value)

        spot_id = self._resolve_current_spot(player_id)
        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        if interior is None:
            raise ItemTransferException(
                f"spot interior not found for spot {spot_id.value}"
            )

        item_aggregate = self._item_repository.find_by_id(item_instance_id)
        if item_aggregate is None:
            raise ItemTransferException(
                f"item aggregate not found for instance {item_instance_id.value}"
            )
        item_spec_id = item_aggregate.item_spec.item_spec_id

        # event を発火させない remove_item_for_storage を使う。
        # (drop_item() は ItemDroppedFromInventoryEvent を発火するが、現状
        # その listener は tile-map 専用なので拾わせない。)
        inventory.remove_item_for_storage(item_instance_id)
        self._player_inventory_repository.save(inventory)

        ground_item = GroundItem(
            item_instance_id=item_instance_id,
            item_spec_id=item_spec_id,
        )
        new_interior = interior.with_ground_item(ground_item)
        self._spot_interior_repository.save(spot_id, new_interior)

        # 表示名は inventory remove 前に確定させる必要があるが、ItemAggregate は
        # まだ item_repository に残っているのでここで OK。
        item_name = self._item_name_or_id(item_instance_id)

        # witness 最小版: 同室の他プレイヤーに観測として届ける。
        # 行為者本人には messages を ItemTransferResult で返し、観測ストリームには
        # 流さない (recipient strategy 側で actor exclusion される)。
        # Stage 2: その場 publish ではなく collector 経由でオペレーション境界で
        # 1 度 dispatch する (収集の一元化)。
        self._flush_events(
            (
                PlayerDroppedItemEvent.create(
                    aggregate_id=self._spot_graph_repository.find_graph().graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(int(player_id)),
                    spot_id=spot_id,
                    item_instance_id=item_instance_id,
                    item_spec_id=item_spec_id,
                    item_name=item_name,
                    witness_policy=witness_policy,
                ),
            )
        )

        return ItemTransferResult(
            messages=(f"{item_name}を地面に置いた。",),
            item_instance_id=item_instance_id,
            spot_id=spot_id,
        )

    def pickup_item(
        self,
        player_id: PlayerId,
        item_instance_id: ItemInstanceId,
        *,
        witness_policy: WitnessPolicy = WitnessPolicy.SAME_SPOT,
    ) -> ItemTransferResult:
        """プレイヤーの現在地から指定アイテムを拾う。

        witness_policy=ACTOR_ONLY で「こっそり拾う」を表現できる (drop と
        対称)。
        """
        spot_id = self._resolve_current_spot(player_id)
        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        if interior is None:
            raise ItemTransferException(
                f"spot interior not found for spot {spot_id.value}"
            )

        ground_item = interior.find_ground_item(item_instance_id)
        # 満杯チェック / 失敗 message で使うため、item_name を 1 度だけ引く。
        item_name = self._item_name_or_id(item_instance_id)
        if ground_item is None:
            # PR-ε: 「他プレイヤーが同 tick で先に拾った」「observation が
            # 古くて既に消えている」の典型ケース。LLM 向けに「先取り可能性」
            # と「別行動への切替」を message で伝える専用 exception。
            raise GroundItemGoneError(item_name=item_name)

        inventory = self._player_inventory_repository.find_by_id(player_id)
        if inventory is None:
            raise ItemTransferException(
                f"inventory not found for player {player_id.value}"
            )

        # PR-ε: 事前ガードで pickup 時のインベントリ満杯を surface する。
        # ``acquire_item`` は満杯だと overflow event を出すだけで silent に
        # 成功扱いになる (地面のアイテムは残るが LLM は「拾った」と誤認
        # しうる)。専用 exception で「drop で空きを作る」次アクションを促す。
        if inventory.is_inventory_full():
            raise PickupSelfInventoryFullError(item_name=item_name)

        # 事前ガードで満杯を弾いたので、ここに来た時点で必ず空きスロットが
        # ある。acquire_item は overflow event を発火しない。
        inventory.acquire_item(
            item_instance_id,
            item_spec_id_value=ground_item.item_spec_id.value,
        )
        self._player_inventory_repository.save(inventory)

        new_interior = interior.without_ground_item(item_instance_id)
        self._spot_interior_repository.save(spot_id, new_interior)

        # item_name は事前ガード用に既に引いてある (このメソッド頭で lookup 済み)。

        # witness 最小版: 同室の他プレイヤーに観測として届ける。
        self._flush_events(
            (
                PlayerPickedUpItemEvent.create(
                    aggregate_id=self._spot_graph_repository.find_graph().graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(int(player_id)),
                    spot_id=spot_id,
                    item_instance_id=item_instance_id,
                    item_spec_id=ground_item.item_spec_id,
                    item_name=item_name,
                    witness_policy=witness_policy,
                ),
            )
        )

        return ItemTransferResult(
            messages=(f"{item_name}を拾い上げた。",),
            item_instance_id=item_instance_id,
            spot_id=spot_id,
        )

    def give_item(
        self,
        from_player_id: PlayerId,
        to_player_id: PlayerId,
        slot_id: SlotId,
    ) -> ItemTransferResult:
        """同じスポットに居る相手プレイヤーへアイテムを直接渡す。

        drop → pickup を 1 アクションに圧縮した経路。同室にいる事を spot-graph
        側で確認し、両者のインベントリ間で instance を直接移す。受取り側の
        インベントリが満杯なら overflow event が発生し giver 側の所持は維持
        されるよう defensive に書く。

        観測 (witness) は PlayerGaveItemEvent を発火し、同スポットの第三者
        (送り手・受け手以外) に「Xが流木をYに渡した」prose を届ける。送り手
        本人にはツール結果として messages が返る。受け手は宛先になっているので
        本イベントの recipient strategy で別途配信される (送り手は除外)。
        """
        if from_player_id.value == to_player_id.value:
            # PR-α (Y_after_pr639_640 後続): domain-specific exception を投げる
            # ことで executor 側で error_code + LLM 向け日本語 message を
            # 適切にマップできる。
            raise TargetIsSelfError()

        from_inv = self._player_inventory_repository.find_by_id(from_player_id)
        if from_inv is None:
            raise ItemTransferException(
                f"inventory not found for sender {from_player_id.value}"
            )
        to_inv = self._player_inventory_repository.find_by_id(to_player_id)
        if to_inv is None:
            raise ItemTransferException(
                f"inventory not found for recipient {to_player_id.value}"
            )

        item_instance_id = from_inv.get_item_instance_id_by_slot(slot_id)
        if item_instance_id is None:
            # PR-ε: drop_item と同じ空スロット errror。LLM 向け error_code +
            # 日本語 message を持つ SlotIsEmptyError に統一する。
            raise SlotIsEmptyError(slot_id=slot_id.value)

        # 両者が同スポットに居ることを確認する。spot_graph_repository は spot
        # の本人位置を解決する単一の真実源 (status.current_spot_id は tile-map
        # 由来で更新されない)。
        from_spot = self._resolve_current_spot(from_player_id)
        to_spot = self._resolve_current_spot(to_player_id)
        if from_spot != to_spot:
            # PR-α: 相手が別 spot にいる → LLM 向けに travel_to を示唆する
            # message を持つ domain exception。target_name / sender_spot_name
            # は transfer_service では引けないので、executor 側で catch して
            # 再構築するのが本筋。ここでは exception クラスの default
            # (「相手」「現在地」) で raise しておき、executor が args から
            # 実名で置換する。
            raise TargetNotInSameSpotError()

        item_aggregate = self._item_repository.find_by_id(item_instance_id)
        if item_aggregate is None:
            raise ItemTransferException(
                f"item aggregate not found for instance {item_instance_id.value}"
            )
        item_spec_id = item_aggregate.item_spec.item_spec_id
        item_name = self._item_name_or_id(item_instance_id)

        # 事前に受け手の空きを確認する。受け手が満杯の状態で送り手から先に
        # 抜くと、acquire_item は overflow event を発行するだけで instance を
        # 受け手に入れず、結果として item が両者のスロットから消えた
        # orphan 状態 (item_repository には残るが、誰も所持しない) になる。
        # この silent failure を防ぐためのガード。
        if to_inv.is_inventory_full():
            # PR-α: item_name は取れる (逆に target_name は取れない)。ここで
            # default 相手名で raise し、executor が args["target_display_name"]
            # で置換する。
            raise TargetInventoryFullError(item_name=item_name)

        # 送り手のインベントリから抜く。tile-map 用 event は発火させたくない
        # ので remove_item_for_storage を使う (drop と同じ理由)。
        from_inv.remove_item_for_storage(item_instance_id)
        self._player_inventory_repository.save(from_inv)

        # 受け手のインベントリへ追加。上の事前ガードにより満杯ではないため、
        # overflow event は発火せず必ず空きスロットに入る。
        to_inv.acquire_item(item_instance_id, item_spec_id_value=item_spec_id.value)
        self._player_inventory_repository.save(to_inv)

        # witness 配信: 同室の第三者と受取り側に「Xが流木をYに渡した」を届ける。
        # recipient strategy で送り手 entity_id は除外される。
        self._flush_events(
            (
                PlayerGaveItemEvent.create(
                    aggregate_id=self._spot_graph_repository.find_graph().graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(int(from_player_id)),
                    recipient_entity_id=EntityId.create(int(to_player_id)),
                    spot_id=from_spot,
                    item_instance_id=item_instance_id,
                    item_spec_id=item_spec_id,
                    item_name=item_name,
                ),
            )
        )

        return ItemTransferResult(
            messages=(f"{item_name}を渡した。",),
            item_instance_id=item_instance_id,
            spot_id=from_spot,
        )

    def list_ground_items_at_player_spot(
        self, player_id: PlayerId
    ) -> tuple[GroundItem, ...]:
        """プレイヤーが今いるスポットの地面アイテム一覧。

        UI / ランナー / 将来の LLM tool が「拾える物」を列挙するために使う。
        """
        spot_id = self._resolve_current_spot(player_id)
        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        if interior is None:
            return ()
        return interior.ground_items

    def _flush_events(self, events: Iterable[DomainEvent]) -> None:
        """収集したイベントを DomainEventCollector 経由で境界 dispatch する。

        collector を通すことで event_id ベースの operation-local dedup と、
        event_id 欠落の fail-fast (`DomainEventCollector.add`) を経由させる。

        item_transfer のイベント (drop/pickup/give) は棚卸し上すべて相② (観測のみ、
        同期 side handler なし) なので、現状の best-effort 方針を保つ:
        publisher 未注入なら no-op、publisher 例外は握って本体オペレーションを
        倒さない。publisher は publish_all(events) を持つ duck-typed object (本番では
        PipelineEventPublisher) を想定。

        相① を含むサービス (needs_decay / revive / consumable) の移行では、この境界で
        相ごとの dispatcher に振り分ける契約 (stage1_contract.md §4) へ拡張する。

        注: 旧 _publish_event は publisher=None なら即 return したが、本メソッドは
        publisher の有無に関わらず collector の fail-fast (event_id 検証) を先に通す。
        現行の公開 API 経由では常に valid な BaseDomainEvent を渡すので挙動は同じ。
        """
        collector = DomainEventCollector()
        collector.add_all(events)
        drained = collector.drain()
        if self._event_publisher is None or not drained:
            return
        try:
            self._event_publisher.publish_all(drained)
        except Exception:  # noqa: BLE001 — publisher 側の失敗で本体を倒さない
            _logger.exception("failed to publish item transfer events")

    def _resolve_current_spot(self, player_id: PlayerId) -> SpotId:
        graph = self._spot_graph_repository.find_graph()
        if graph is None:
            raise ItemTransferException("spot graph not found")
        try:
            return graph.get_entity_spot(EntityId.create(int(player_id)))
        except Exception as e:
            raise ItemTransferException(
                f"player {player_id.value} is not placed at any spot: {e}"
            ) from e

    def _item_name_or_id(self, item_instance_id: ItemInstanceId) -> str:
        agg = self._item_repository.find_by_id(item_instance_id)
        if agg is None:
            return f"アイテム#{item_instance_id.value}"
        return agg.item_spec.name


__all__ = [
    "SpotGraphItemTransferService",
    "ItemTransferException",
    "ItemTransferResult",
]
