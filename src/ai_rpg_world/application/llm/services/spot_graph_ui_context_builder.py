"""スポットグラフ用の UiContextBuilder（ラベル付与 + ToolRuntimeTarget 登録）。

SpotGraphPlayerSnapshotDto の構造化データからエフェメラルラベルを採番し、
LLM が読めるテキスト行と、ツール実行用の ToolRuntimeContextDto を同時に構築する。
"""

from __future__ import annotations

from typing import List, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    LlmUiContextDto,
    MonsterToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmUiContextBuilder
from ai_rpg_world.application.llm.services._label_allocator import LabelAllocator
from ai_rpg_world.application.llm.services._runtime_target_collector import RuntimeTargetCollector
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphPlayerSnapshotDto,
)

from ai_rpg_world.application.world_graph.spot_graph_monster_view import (
    HEALTH_BUCKET_JP,
)


PREFIX_CONNECTION = "S"
PREFIX_OBJECT = "OBJ"
PREFIX_SUB_LOCATION = "SL"
PREFIX_ENTITY = "P"
PREFIX_INVENTORY = "I"
PREFIX_MONSTER = "M"
# 地面アイテム (drop された / 初期配置) のラベル prefix。
# pickup tool が "G1" のような形で対象を指せるようにする。
PREFIX_GROUND_ITEM = "G"


def _current_sub_location_id_from_snapshot(
    snap: SpotGraphPlayerSnapshotDto,
) -> Optional[int]:
    """sub_locations のうち is_current の最初の sub_location_id を返す。

    ドメイン上は is_current は高々 1 件の想定。複数 True の場合は **先頭を採用**（仕様固定。バリデーションは別途検討）。
    """
    for entry in snap.sub_locations:
        if entry.is_current:
            return entry.sub_location_id
    return None


class SpotGraphUiContextBuilder(ILlmUiContextBuilder):
    """スポットグラフのスナップショットにラベルを付与する UiContextBuilder。"""

    def build(
        self,
        current_state_text: str,
        current_state: Optional[PlayerCurrentStateDto],
    ) -> LlmUiContextDto:
        if current_state is None or current_state.spot_graph_snapshot is None:
            return LlmUiContextDto(
                current_state_text=current_state_text,
                tool_runtime_context=ToolRuntimeContextDto.empty(),
            )

        snap = current_state.spot_graph_snapshot
        allocator = LabelAllocator()
        collector = RuntimeTargetCollector()
        extra_lines: List[str] = []

        self._build_connection_section(snap, allocator, collector, extra_lines)
        self._build_object_section(snap, allocator, collector, extra_lines)
        self._build_sub_location_section(snap, allocator, collector, extra_lines)
        self._build_entity_section(snap, allocator, collector, extra_lines)
        self._build_monster_section(snap, allocator, collector, extra_lines)
        self._build_inventory_section(snap, allocator, collector, extra_lines)
        self._build_ground_items_section(snap, allocator, collector, extra_lines)
        self._build_needs_section(snap, extra_lines)

        augmented_text = current_state_text
        if extra_lines:
            augmented_text = current_state_text.rstrip() + "\n" + "\n".join(extra_lines)

        return LlmUiContextDto(
            current_state_text=augmented_text,
            tool_runtime_context=ToolRuntimeContextDto(
                targets=collector.get_targets(),
                current_spot_id=snap.current_spot_id,
                current_sub_location_id=_current_sub_location_id_from_snapshot(snap),
            ),
        )

    def _build_connection_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        if not snap.connections:
            return
        lines.append("接続先ラベル:")
        for entry in snap.connections:
            label = allocator.next(PREFIX_CONNECTION)
            if entry.is_passable:
                status = "通行可"
            elif entry.passage_condition_text:
                status = f"通行不可 — {entry.passage_condition_text}"
            else:
                status = "通行不可"
            lines.append(
                f"  {label}: {entry.connection_name} → {entry.destination_spot_name}（{status}）"
            )
            collector.add(
                label,
                DestinationToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_destination",
                    display_name=entry.destination_spot_name,
                    spot_id=entry.destination_spot_id,
                    destination_type="spot",
                ),
            )

    def _build_object_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        if not snap.objects:
            return
        lines.append("オブジェクトラベル:")
        for entry in snap.objects:
            label = allocator.next(PREFIX_OBJECT)
            interaction_parts: list[str] = []
            action_names: list[str] = []
            for inter in entry.interactions:
                interaction_parts.append(
                    f"{inter.display_label}(action_name=\"{inter.action_name}\")"
                )
                action_names.append(inter.action_name)
            act_str = " / ".join(interaction_parts) if interaction_parts else "—"
            desc_part = f" — {entry.description}" if entry.description else ""
            lines.append(f"  {label}: {entry.name}{desc_part} [{act_str}]")
            collector.add(
                label,
                ToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_object",
                    display_name=entry.name,
                    world_object_id=entry.object_id,
                    available_interactions=tuple(action_names),
                ),
            )

    def _build_sub_location_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        visible_subs = [s for s in snap.sub_locations if not s.is_hidden]
        if not visible_subs:
            return
        lines.append("サブロケーションラベル:")
        for entry in visible_subs:
            label = allocator.next(PREFIX_SUB_LOCATION)
            here = "（現在ここ）" if entry.is_current else ""
            lines.append(f"  {label}: {entry.name}{here}")
            collector.add(
                label,
                ToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_sub_location",
                    display_name=entry.name,
                    sub_location_id=entry.sub_location_id,
                ),
            )

    def _build_entity_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        if not snap.nearby_entities:
            return
        lines.append("同じ場所にいるプレイヤー:")
        for entry in snap.nearby_entities:
            label = allocator.next(PREFIX_ENTITY)
            name = entry.display_name or f"プレイヤー({entry.entity_id})"
            lines.append(f"  {label}: {name}")
            collector.add(
                label,
                PlayerToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_player",
                    display_name=name,
                    player_id=entry.entity_id,
                ),
            )

    def _build_monster_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        """同スポットに居るモンスター個体に M1, M2, ... を割り当てる。

        ラベルは揮発（既存パターン踏襲）。LLM がターンを跨いで個体を追跡したい
        場合は description / 名前から再特定する想定で、ここでは安定ハンドルを
        用意しない。戦闘ツールが導入された時に再評価する。

        死体は生存個体と同じ section に並べるが、表記とラベル説明文を分ける。
        現状では戦闘ツールがまだ無いため `available_interactions` は空。次の
        戦闘 PR で attack 等が実装された時点で埋める。
        """
        if not snap.monsters_at_spot:
            return
        lines.append("同じ場所に居るモンスター:")
        for entry in snap.monsters_at_spot:
            label = allocator.next(PREFIX_MONSTER)
            if entry.is_dead:
                desc = "死骸"
            else:
                health_label = HEALTH_BUCKET_JP.get(
                    entry.health_bucket, entry.health_bucket
                )
                desc = f"{entry.behavior_label}・{health_label}"
            lines.append(f"  {label}: {entry.display_name}（{desc}）")
            collector.add(
                label,
                MonsterToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_monster",
                    display_name=entry.display_name,
                    monster_id=entry.monster_id,
                ),
            )

    @staticmethod
    def _build_needs_section(
        snap: SpotGraphPlayerSnapshotDto,
        lines: List[str],
    ) -> None:
        if not snap.need_lines:
            return
        lines.append("身体の状態:")
        for line in snap.need_lines:
            lines.append(f"  {line}")

    def _build_inventory_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        if not snap.inventory_items:
            return
        lines.append("所持アイテム:")
        for entry in snap.inventory_items:
            label = allocator.next(PREFIX_INVENTORY)
            qty = f" x{entry.quantity}" if entry.quantity > 1 else ""
            lines.append(f"  {label}: {entry.name}{qty}")
            # 後方互換: 既存 use_item は target.item_instance_id に item_spec_id を
            # 入れる慣習 (名前と内容が乖離しているが、リスクを取らないため触らない)。
            # 新しい drop_item / pickup_item は専用フィールド (real_item_instance_id /
            # inventory_slot_id) を見るので、ここで両方埋める。
            collector.add(
                label,
                InventoryToolRuntimeTargetDto(
                    label=label,
                    kind="inventory_item",
                    display_name=entry.name,
                    item_instance_id=entry.item_spec_id,
                    real_item_instance_id=(
                        entry.item_instance_id if entry.item_instance_id >= 0 else None
                    ),
                    inventory_slot_id=(
                        entry.slot_id if entry.slot_id >= 0 else None
                    ),
                ),
            )

    def _build_ground_items_section(
        self,
        snap: SpotGraphPlayerSnapshotDto,
        allocator: LabelAllocator,
        collector: RuntimeTargetCollector,
        lines: List[str],
    ) -> None:
        """現在地に落ちているアイテムを G1, G2, ... ラベル付きで列挙する。

        pickup tool が target を一意に指せるよう、item_instance_id を
        InventoryToolRuntimeTargetDto.real_item_instance_id に格納する。
        """
        if not snap.ground_items:
            return
        lines.append("地面に落ちているもの:")
        for entry in snap.ground_items:
            label = allocator.next(PREFIX_GROUND_ITEM)
            lines.append(f"  {label}: {entry.name}")
            collector.add(
                label,
                InventoryToolRuntimeTargetDto(
                    label=label,
                    kind="ground_item",
                    display_name=entry.name,
                    real_item_instance_id=entry.item_instance_id,
                ),
            )
