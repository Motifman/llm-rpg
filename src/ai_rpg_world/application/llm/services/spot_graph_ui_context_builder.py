"""スポットグラフ用の UiContextBuilder（ラベル付与 + ToolRuntimeTarget 登録）。

SpotGraphPlayerSnapshotDto の構造化データからエフェメラルラベルを採番し、
LLM が読めるテキスト行と、ツール実行用の ToolRuntimeContextDto を同時に構築する。
"""

from __future__ import annotations

from typing import List, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    LlmUiContextDto,
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

PREFIX_CONNECTION = "S"
PREFIX_OBJECT = "OBJ"
PREFIX_SUB_LOCATION = "SL"
PREFIX_ENTITY = "E"


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

        augmented_text = current_state_text
        if extra_lines:
            augmented_text = current_state_text.rstrip() + "\n" + "\n".join(extra_lines)

        return LlmUiContextDto(
            current_state_text=augmented_text,
            tool_runtime_context=ToolRuntimeContextDto(
                targets=collector.get_targets(),
                current_spot_id=None,
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
            status = "通行可" if entry.is_passable else "通行不可"
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
            lines.append(f"  {label}: {entry.name} [{act_str}]")
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
                    location_area_id=entry.sub_location_id,
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
        lines.append("同じ場所にいる存在:")
        for entry in snap.nearby_entities:
            label = allocator.next(PREFIX_ENTITY)
            lines.append(f"  {label}: entity_id={entry.entity_id}")
            collector.add(
                label,
                ToolRuntimeTargetDto(
                    label=label,
                    kind="spot_graph_entity",
                    display_name=f"entity_{entry.entity_id}",
                    player_id=entry.entity_id,
                ),
            )
